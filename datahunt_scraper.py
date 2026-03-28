#!/usr/bin/env python3
"""
DataHunt IL - Real Job Scraper
Scrapes Israeli and international job boards for entry-level data roles in Tel Aviv metro area.
"""

import sys, io, os
import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
from urllib.parse import quote_plus
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# Windows: force stdout to UTF-8 so Hebrew/emoji print without errors
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── English roles (used for LinkedIn + as seed for Israeli sites) ─────────────
ROLES = [
    "Data Analyst",
    "BI Analyst",
    "BI Developer",
    "Junior Data Scientist",
    "AI Analyst",
    "Business Analyst",
    "Analytics Engineer",
]

# ── Hebrew roles (used on Drushim / AllJobs) ──────────────────────────────────
ROLES_HEBREW = [
    "אנליסט דאטה",
    "אנליסט נתונים",
    "מנתח נתונים",
    "דאטה אנליסט",
    "BI אנליסט",
    "אנליסט BI",
    "מפתח BI",
    "אנליסט עסקי",
    "מהנדס אנליטיקה",
    "דאטה סיינטיסט",
    "מדען נתונים",
    "אנליסט AI",
]

LOCATIONS   = ["Tel Aviv", "Ramat Gan", "Givatayim", "Petah Tikva", "Herzliya", "Bnei Brak"]
COMPANY_BLACKLIST = ["experis"]   # agencies / irrelevant companies to skip
MAX_EXPERIENCE = 2
_DATA_DIR      = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE     = os.path.join(_DATA_DIR, "datahunt_cache.json")
OUTPUT_FILE    = os.path.join(_DATA_DIR, "datahunt_results.html")
JOBS_FILE      = os.path.join(_DATA_DIR, "jobs_data.json")
PROGRESS_FILE  = os.path.join(_DATA_DIR, "scan_progress.json")
CONFIG_FILE    = os.path.join(_DATA_DIR, "user_config.json")

# Override ROLES from user config if present
try:
    with open(CONFIG_FILE, encoding="utf-8") as _cf:
        _cfg = json.load(_cf)
    if _cfg.get("roles"):
        ROLES = _cfg["roles"]
        print(f"Using custom roles from config: {ROLES}")
except Exception:
    pass  # use defaults
os.makedirs(_DATA_DIR, exist_ok=True)

def _write_progress(pct, stage, found=0):
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as _f:
            json.dump({"pct": pct, "stage": stage, "found": found}, _f)
    except Exception:
        pass

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Load cache
try:
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)
except Exception:
    cache = {"seen_urls": [], "last_run": None}

results = []


# ── Hebrew numeric words → integer years ─────────────────────────────────────

_HEB_NUMS = {
    "שנה": 1, "שנה אחת": 1,
    "שנתיים": 2, "שתי שנים": 2,
    "שלוש שנים": 3, "שלש שנים": 3,
    "ארבע שנים": 4,
    "חמש שנים": 5,
    "שש שנים": 6,
    "שבע שנים": 7,
    "שמונה שנים": 8,
    "תשע שנים": 9,
    "עשר שנים": 10,
}

def _heb_years(text):
    """Return minimum years required from a Hebrew experience string, or None."""
    t = text.strip()
    # Range: "שנה-שנתיים" / "שנה עד שנתיים" → min is lower bound
    for sep in ["-", "–", " עד ", " - "]:
        if sep in t:
            parts = t.split(sep, 1)
            lo = _heb_years(parts[0].strip())
            if lo is not None:
                return lo
    # "לפחות X" / "מינימום X" / "לא פחות מ X" → X
    for prefix in ["לפחות ", "מינימום ", "לא פחות מ", "לא פחות מ-", "מעל "]:
        if t.startswith(prefix):
            return _heb_years(t[len(prefix):].strip())
    # Direct word match
    for word, val in sorted(_HEB_NUMS.items(), key=lambda x: -len(x[0])):
        if word in t:
            return val
    # Digit fallback "3 שנים"
    m = re.search(r"(\d+)\s*שנ", t)
    if m:
        return int(m.group(1))
    return None


# ── Relevance & entry-level filters ──────────────────────────────────────────

def is_entry_level(title, experience_hint=""):
    """Return False if title or experience hint indicates more than MAX_EXPERIENCE years."""
    title_lower = title.lower()
    hint_lower  = experience_hint.lower() if experience_hint else ""
    combined    = title_lower + " " + hint_lower

    if any(w in title_lower for w in ["senior", "sr.", "lead", "manager", "principal", "head of", "director", "בכיר", "מנהל"]):
        return False

    # ── Numeric patterns (English + mixed Hebrew) ──
    # "3+ years", "3-5 years", "3 שנים"
    for pattern in [r"(\d+)\+?\s*(?:years?|yrs?)", r"(\d+)-\d+\s*(?:years?|yrs?)", r"(\d+)\s*שנ"]:
        for match in re.findall(pattern, combined):
            mn = int(match[0]) if isinstance(match, tuple) else int(match)
            if mn > MAX_EXPERIENCE:
                return False

    # ── Hebrew word patterns ──
    years = _heb_years(combined)
    if years is not None and years > MAX_EXPERIENCE:
        return False

    return True


DATA_TITLE_WHITELIST = [
    "data", "bi ", "bi-", "business intelligence", "analytics",
    "machine learning", "business analyst", "ai analyst",
    "research analyst", "insight", "reporting analyst",
    # Hebrew equivalents
    "דאטה", "נתונים", "אנליסט", "אנליטיקה", "בינה עסקית",
]

DATA_TITLE_BLACKLIST = [
    "backend", "frontend", "front-end", "full stack", "fullstack", "full-stack",
    "software engineer", "software developer", "kernel", "devops",
    "legal engineer", "billing analyst", "grc analyst", "salesforce",
    "support engineer", "support technician", "control and monitoring",
    "program developer", "occ monitoring",
    "qa engineer", "quality assurance engineer",
    "machine learning research", "applied ai scientist",
    "emerge developer", "strategy analyst", "geo analyst",
    # Qlik-only roles (user has Qlik exp but wants to exclude Qlik-specialist jobs)
    "qlik developer", "qlik analyst", "qlik engineer", "qlik specialist",
    "qlik sense developer", "qlik view developer", "qlikview developer",
    "qliksense developer", "מפתח qlik", "אנליסט qlik",
]


def is_data_relevant(title):
    t = title.lower()
    # Custom roles always pass — user explicitly requested them
    if any(role.lower() in t for role in ROLES):
        return True
    if not any(kw in t for kw in DATA_TITLE_WHITELIST):
        return False
    if any(kw in t for kw in DATA_TITLE_BLACKLIST):
        return False
    return True


# ── Resume-based relevance scoring ───────────────────────────────────────────
# Tuned to Guy Amos: Power BI, Tableau, SQL, Python, BI Developer/Analyst roles

def score_job(job):
    """Return 0-100 relevance score for this job against Guy's resume.

    Components:
      Role fit   (0-52)  — job title match to Guy's target roles
      Tech bonus (0-28)  — Power BI / SQL / Python / Tableau in title or exp
      Location   (-10 to +10) — proximity to Ramat Gan
      Exp fit    (0-10)  — experience level match
    Penalties: startup/fast-paced company, far location.
    """
    title    = job.get("title", "").lower()
    exp_lbl  = job.get("experience_required", "").lower()
    company  = job.get("company", "").lower()
    location = job.get("location", "").lower()
    haystack = title + " " + exp_lbl

    # ── Role fit ──────────────────────────────────────────────────────────────
    role_pts = 0
    if "data analyst" in title or "analyst data" in title:
        role_pts = 52   # top preference
    elif any(t in title for t in ["bi developer", "business intelligence developer"]):
        role_pts = 48
    elif any(t in title for t in ["bi analyst", "business intelligence analyst"]):
        role_pts = 46
    elif "power bi" in title or "powerbi" in title:
        role_pts = 44
    elif "analytics engineer" in title:
        role_pts = 42
    elif "reporting analyst" in title or "report analyst" in title:
        role_pts = 36
    elif "ai analyst" in title:
        role_pts = 32
    elif "business analyst" in title:
        role_pts = 22
    elif "data engineer" in title:
        role_pts = 18
    elif "data scientist" in title:
        role_pts = 12
    elif "analyst" in title:
        role_pts = 20

    # Dashboard bonus — matches Guy's core experience
    if "dashboard" in title:
        role_pts = min(role_pts + 5, 52)

    # ── Tech bonus (capped at 28) ─────────────────────────────────────────────
    tech = 0
    if "power bi" in haystack or "powerbi" in haystack: tech += 20
    if "sql"      in haystack:                           tech += 12  # SQL > Python
    if "python"   in haystack:                           tech += 7
    if "tableau"  in haystack:                           tech += 6   # ok but not expert
    if any(t in haystack for t in ["dbt", "looker"]):   tech += 4
    # ETL/DWH penalty — Guy has Power Query only, not SSIS/heavy ETL
    if any(t in haystack for t in ["ssis", "etl", "dwh", "data warehouse"]):
        tech -= 6
    # Python automation bonus
    if "python" in haystack and any(w in haystack for w in
            ["automat", "workflow", "script", "pipeline", "orchestrat"]):
        tech += 5
    tech = min(tech, 28)

    # ── Location score ────────────────────────────────────────────────────────
    _CLOSE = ["ramat gan", "tel aviv", "givatayim", "bnei brak", "bney brak",
              "רמת גן", "תל אביב", "גבעתיים", "בני ברק"]
    _OK    = ["petah tikva", "herzliya", "holon", "rishon", "rehovot",
              "ramat hasharon", "bat yam", "azrieli",
              "פתח תקווה", "הרצליה", "חולון", "ראשון", "רחובות", "בת ים"]
    _FAR   = ["haifa", "jerusalem", "beer sheva", "beersheba", "eilat",
              "חיפה", "ירושלים", "באר שבע", "אילת"]

    if any(c in location for c in _CLOSE):
        loc_pts = 10
    elif any(c in location for c in _OK):
        loc_pts = 4
    elif any(c in location for c in _FAR):
        loc_pts = -10
    else:
        loc_pts = 2   # "Israel" or unknown — neutral

    # ── Experience fit ────────────────────────────────────────────────────────
    if any(k in exp_lbl for k in ["entry level", "0-1", "0-2"]):
        exp_pts = 10
    elif any(k in exp_lbl for k in ["1-2", "1+ yrs", "1 yr"]):
        exp_pts = 8
    elif any(k in exp_lbl for k in ["2 yrs", "2-3", "2+ yrs"]):
        exp_pts = 5
    else:
        exp_pts = 2   # unknown

    total = role_pts + tech + loc_pts + exp_pts
    return max(0, min(total, 100))


# ── Cross-site deduplication ─────────────────────────────────────────────────

def _norm(s):
    """Lowercase, strip Hebrew vowel marks, collapse whitespace, strip punctuation."""
    s = s.lower().strip()
    # Remove common punctuation / job-title noise
    s = re.sub(r"[/\\|,.\-–()'\"]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_hebrew(s):
    return any('\u05d0' <= c <= '\u05ea' for c in s)


def _title_match(t, et):
    return (t == et) or (len(t) > 8 and t in et) or (len(et) > 8 and et in t)


def _company_match(c, ec):
    return (c == ec) or (len(c) > 4 and c in ec) or (len(ec) > 4 and ec in c)


def is_cross_site_duplicate(job, existing_jobs):
    """Return True if a job with the same title (and company, when comparable) already
    exists from a different source.

    Rules:
    - Title must substantially overlap (one contains the other after normalisation).
    - Company is only checked if both are in the same script (both Latin or both Hebrew)
      AND neither is a generic placeholder like 'unknown'.
    - If companies are in different scripts (e.g. LinkedIn has English name, Drushim has
      Hebrew name for the same firm) we skip the company check and trust title alone.
    """
    t = _norm(job.get("title", ""))
    c = _norm(job.get("company", ""))

    if not t:
        return False

    UNKNOWN = {"unknown", ""}

    for ex in existing_jobs:
        et = _norm(ex.get("title", ""))
        ec = _norm(ex.get("company", ""))

        # Same source → handled by URL cache
        if ex.get("source") == job.get("source"):
            continue

        # Title must substantially overlap
        if not _title_match(t, et):
            continue

        # Company check
        if c not in UNKNOWN and ec not in UNKNOWN:
            same_script = (_is_hebrew(c) == _is_hebrew(ec))
            if same_script:
                # Same script — must match
                if not _company_match(c, ec):
                    continue
            else:
                # Different scripts (e.g. LinkedIn=English, Drushim=Hebrew) — we
                # cannot compare the names, so require a very tight title match only
                # when the title is generic (short). For specific titles (>15 chars)
                # the title match alone is enough evidence; for generic short titles
                # (e.g. "Data Analyst") it is too risky — skip dedup.
                if len(t) <= 15:
                    continue  # too generic a title to dedup without matching company

        return True

    return False


def is_duplicate_in_store(job, existing_jobs):
    """Stricter duplicate check used when persisting to jobs_data.json.
    Same-source jobs are deduplicated by title+company (not just URL),
    catching re-posted listings that appear with new URLs on later scrapes.
    Cross-source logic is identical to is_cross_site_duplicate().
    """
    t   = _norm(job.get("title",   ""))
    c   = _norm(job.get("company", ""))
    src = (job.get("source") or "").lower()

    if not t:
        return False

    UNKNOWN = {"unknown", ""}

    for ex in existing_jobs:
        et   = _norm(ex.get("title",   ""))
        ec   = _norm(ex.get("company", ""))
        esrc = (ex.get("source") or "").lower()

        if not _title_match(t, et):
            continue

        if src == esrc:
            # Same source: require title + company match to avoid blocking
            # different roles at the same company
            if c in UNKNOWN or ec in UNKNOWN:
                return True   # can't distinguish by company — trust title
            if _company_match(c, ec):
                return True
        else:
            # Different source: same cross-site logic
            if c not in UNKNOWN and ec not in UNKNOWN:
                same_script = (_is_hebrew(c) == _is_hebrew(ec))
                if same_script:
                    if not _company_match(c, ec):
                        continue
                else:
                    if len(t) <= 15:
                        continue
            return True

    return False


# ── Experience label ──────────────────────────────────────────────────────────

def extract_experience(title, snippet=""):
    """Return a human-readable experience label.
    Handles English numeric patterns AND Hebrew word patterns.
    """
    text = (title + " " + snippet).lower()

    # Junior / entry-level markers (English + Hebrew)
    if re.search(
        r"\b(junior|entry.?level|intern|graduate|student|0-2|"
        r"ג'וניור|מתחיל|סטודנט|מתמחה|ללא ניסיון)\b", text
    ):
        return "Entry Level"

    # ── English numeric patterns ──────────────────────────────────────────

    # X-Y years  e.g. "1-2 years"
    m = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?|שנ)", text)
    if m:
        return f"{m.group(1)}-{m.group(2)} yrs"

    # X+ years
    m = re.search(r"(\d+)\+\s*(?:years?|yrs?|שנ)", text)
    if m:
        return f"{m.group(1)}+ yrs"

    # up to X years
    m = re.search(r"(?:up to|maximum|max)\s*(\d+)\s*(?:years?|yrs?)", text)
    if m:
        return f"0-{m.group(1)} yrs"

    # X years (plain)
    m = re.search(r"(\d+)\s*(?:years?|yrs?)", text)
    if m:
        return f"{m.group(1)} yrs"

    # ── Hebrew word patterns ──────────────────────────────────────────────

    # "שנה-שנתיים" / "שנה עד שנתיים" (range)
    for sep_pat in [r"שנה\s*[-–]\s*שנתיים", r"שנה\s+עד\s+שנתיים"]:
        if re.search(sep_pat, text):
            return "1-2 yrs"

    for sep_pat in [r"שנתיים\s*[-–]\s*שלוש", r"שנתיים\s+עד\s+שלוש"]:
        if re.search(sep_pat, text):
            return "2-3 yrs"

    # "לפחות X" / "מעל X" / "מינימום X"
    prefix_m = re.search(
        r"(?:לפחות|מינימום|מעל|לא פחות מ)\s+(שנה|שנתיים|שלוש שנים|ארבע שנים|חמש שנים)", text
    )
    if prefix_m:
        word = prefix_m.group(1)
        yrs = _HEB_NUMS.get(word, 1)
        return f"{yrs}+ yrs"

    # Plain Hebrew year words
    for word, yrs in sorted(_HEB_NUMS.items(), key=lambda x: -len(x[0])):
        if word in text:
            return f"{yrs} yrs" if yrs > 1 else "1 yr"

    return "Entry Level"   # default


# ── Scrapers ──────────────────────────────────────────────────────────────────

def scrape_linkedin():
    """One request per role, Israel-wide. Removed per-city loop (was 7x6=42 requests)."""
    jobs = []
    for role in ROLES:
        try:
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={quote_plus(role)}"
                f"&location=Israel&f_E=2&sortBy=DD"
            )
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.content, "html.parser")

            for card in soup.find_all("div", class_="base-card")[:10]:
                try:
                    title_el   = card.find("h3", class_="base-search-card__title")
                    company_el = card.find("h4", class_="base-search-card__subtitle")
                    loc_el     = card.find("span", class_="job-search-card__location")
                    link_el    = card.find("a",   class_="base-card__full-link")
                    time_el    = card.find("time")

                    if not (title_el and link_el):
                        continue

                    title   = title_el.text.strip()
                    company = company_el.text.strip() if company_el else "Unknown"
                    loc     = loc_el.text.strip()     if loc_el     else "Israel"
                    link    = link_el.get("href", "").split("?")[0]

                    posted_iso = time_el.get("datetime") if time_el else None

                    exp = extract_experience(title)
                    if is_data_relevant(title) and is_entry_level(title, exp) and link not in cache["seen_urls"]:
                        job = {
                            "title":               title,
                            "company":             company,
                            "location":            loc,
                            "url":                 link,
                            "source":              "LinkedIn",
                            "posted":              posted_iso or "Recently",
                            "scraped_at":          datetime.now().isoformat(),
                            "experience_required": exp,
                        }
                        job["relevance_score"] = score_job(job)
                        if any(bl in job.get("company","").lower() for bl in COMPANY_BLACKLIST):
                            continue
                        jobs.append(job)
                        cache["seen_urls"].append(link)
                except Exception:
                    continue

            time.sleep(1)
        except Exception as e:
            print(f"  LinkedIn error [{role}]: {e}")

    return jobs


def scrape_jobmaster():
    """Scrape Jobmaster.co.il — major Israeli job board, English + Hebrew queries."""
    jobs = []
    all_roles = ROLES + ROLES_HEBREW

    for role in all_roles:
        try:
            url  = f"https://www.jobmaster.co.il/jobs/?q={quote_plus(role)}&from=0"
            resp = requests.get(url, headers=HEADERS, timeout=12)
            soup = BeautifulSoup(resp.content, "html.parser")

            # Each job is an <article class="JobItem ...">
            items = soup.find_all("article", class_=re.compile(r"JobItem|CardStyle"))

            for item in items[:6]:
                try:
                    # Title + link: <a class="CardHeader View_Job_Details" href="/jobs/checknum.asp?key=...">
                    link_el = item.find("a", class_=re.compile(r"CardHeader|View_Job_Details"))
                    if not link_el:
                        continue

                    title = link_el.get_text(strip=True)
                    href  = link_el.get("href", "")
                    link  = ("https://www.jobmaster.co.il" + href) if href.startswith("/") else href

                    # Company: text after "ע"י" — sits in a sibling <a> tag
                    company_el = item.find("a", class_=re.compile(r"CompanyLink|company|employer"))
                    if not company_el:
                        # fallback: second <a> in the item
                        all_a = item.find_all("a")
                        company_el = all_a[1] if len(all_a) > 1 else None
                    company = company_el.get_text(strip=True) if company_el else "Unknown"

                    # Date: <span class="Gray">פורסם לפני 3 שעות</span>
                    date_el = item.find("span", class_="Gray")
                    posted  = date_el.get_text(strip=True) if date_el else "Recently"

                    # Location: <span class="jobType"> or similar
                    loc_el = item.find("span", class_=re.compile(r"jobType|location|city"))
                    loc    = loc_el.get_text(strip=True) if loc_el else "Israel"

                    exp = extract_experience(title)
                    if link and is_data_relevant(title) and is_entry_level(title, exp) and link not in cache["seen_urls"]:
                        job = {
                            "title":               title,
                            "company":             company,
                            "location":            loc,
                            "url":                 link,
                            "source":              "Jobmaster",
                            "posted":              posted,
                            "scraped_at":          datetime.now().isoformat(),
                            "experience_required": exp,
                        }
                        job["relevance_score"] = score_job(job)
                        jobs.append(job)
                        cache["seen_urls"].append(link)
                except Exception:
                    continue

            time.sleep(1)
        except Exception as e:
            print(f"  Jobmaster error [{role}]: {e}")

    return jobs


def scrape_drushim():
    """Scrape Drushim.co.il — searches English + Hebrew role names.
    Actual selectors verified from live HTML inspection.
    """
    jobs = []
    all_roles = ROLES + ROLES_HEBREW

    seen_listing_ids = set()   # Drushim dedup by listing ID

    for role in all_roles:
        try:
            url  = f"https://www.drushim.co.il/jobs/search/{quote_plus(role)}/?experience=0-2&cities=2"
            resp = requests.get(url, headers=HEADERS, timeout=12)
            soup = BeautifulSoup(resp.content, "html.parser")

            # Real selector confirmed: <div class="flex job job-item ...">
            items = soup.find_all("div", class_="job-item")

            for item in items[:8]:
                try:
                    # Title: <span class="job-url primary--text ...">
                    title_el = item.find("span", class_="job-url")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)

                    # Link: <a href="/job/36379569/dbf0a920/"> (first a with /job/ href)
                    link_el = item.find("a", href=re.compile(r"^/job/"))
                    if not link_el:
                        continue
                    href = link_el.get("href", "")
                    link = "https://www.drushim.co.il" + href

                    # Dedup by listing ID embedded in href (/job/ID/slug/)
                    listing_id = href.split("/")[2] if len(href.split("/")) > 2 else href
                    if listing_id in seen_listing_ids:
                        continue
                    seen_listing_ids.add(listing_id)

                    # Company: <span class="bidi"> inside the employer section
                    company_el = item.find("span", class_="bidi")
                    company    = company_el.get_text(strip=True) if company_el else "Unknown"

                    # Date + location in <div class="job-details-sub">
                    # Text like: "רמת גן|1-2 שנים|משרה מלאה|לפני 6 שעות"
                    details_el = item.find("div", class_="job-details-sub")
                    details    = details_el.get_text("|", strip=True) if details_el else ""
                    parts      = [p.strip() for p in details.split("|") if p.strip()]
                    location   = parts[0] if parts else "ישראל"
                    experience = parts[1] if len(parts) > 1 else ""
                    posted     = parts[-1] if parts else "לאחרונה"

                    exp = experience or extract_experience(title)
                    if link and is_data_relevant(title) and is_entry_level(title, exp) and link not in cache["seen_urls"]:
                        job = {
                            "title":               title,
                            "company":             company,
                            "location":            location,
                            "url":                 link,
                            "source":              "Drushim",
                            "posted":              posted,
                            "scraped_at":          datetime.now().isoformat(),
                            "experience_required": extract_experience(title, exp),
                        }
                        job["relevance_score"] = score_job(job)
                        jobs.append(job)
                        cache["seen_urls"].append(link)
                except Exception:
                    continue

            time.sleep(1)
        except Exception as e:
            print(f"  Drushim error [{role}]: {e}")

    return jobs


def scrape_alljobs():
    """Scrape AllJobs.co.il — English + Hebrew queries.
    Actual selectors verified from live HTML inspection.
    """
    jobs = []
    all_roles = ROLES + ROLES_HEBREW

    for role in all_roles:
        try:
            url  = f"https://www.alljobs.co.il/SearchResultsGuest.aspx?position={quote_plus(role)}&type=&source=&duration="
            resp = requests.get(url, headers=HEADERS, timeout=12)
            soup = BeautifulSoup(resp.content, "html.parser")

            # Real selector confirmed: <div class="job-content-top">
            items = soup.find_all("div", class_="job-content-top")

            for item in items[:6]:
                try:
                    # Title + link: <a class="N" href="/Search/UploadSingle.aspx?JobID=..."><h2>title</h2></a>
                    link_el = item.find("a", class_="N")
                    if not link_el:
                        link_el = item.find("a", href=re.compile(r"JobID=|UploadSingle"))
                    if not link_el:
                        continue

                    title_el = link_el.find("h2") or link_el
                    title    = title_el.get_text(strip=True)
                    href     = link_el.get("href", "")
                    link     = ("https://www.alljobs.co.il" + href) if href.startswith("/") else href

                    # Company: <div class="T14"><a href="/Employer/...">Company</a></div>
                    company_el = item.find("div", class_="T14")
                    if company_el:
                        company_a = company_el.find("a")
                        company   = company_a.get_text(strip=True) if company_a else company_el.get_text(strip=True)
                    else:
                        company = "Unknown"

                    # Date: <div class="job-content-top-date">לפני 4 שעות</div>
                    date_el = item.find("div", class_="job-content-top-date")
                    posted  = date_el.get_text(strip=True) if date_el else "לאחרונה"

                    # Location: inside job-content-top-location
                    loc_el   = item.find("div", class_="job-content-top-location")
                    location = loc_el.get_text(" ", strip=True)[:50] if loc_el else "ישראל"

                    exp = extract_experience(title)
                    if link and is_data_relevant(title) and is_entry_level(title, exp) and link not in cache["seen_urls"]:
                        job = {
                            "title":               title,
                            "company":             company,
                            "location":            location,
                            "url":                 link,
                            "source":              "AllJobs",
                            "posted":              posted,
                            "scraped_at":          datetime.now().isoformat(),
                            "experience_required": exp,
                        }
                        job["relevance_score"] = score_job(job)
                        jobs.append(job)
                        cache["seen_urls"].append(link)
                except Exception:
                    continue

            time.sleep(1)
        except Exception as e:
            print(f"  AllJobs error [{role}]: {e}")

    return jobs


def scrape_glassdoor():
    """Scrape Glassdoor Israel job listings.
    Glassdoor may block requests with Cloudflare — 0 results is normal if blocked.
    """
    jobs = []
    GD_HEADERS = {
        **HEADERS,
        "Referer": "https://www.glassdoor.com/",
        "Accept": "text/html,application/xhtml+xml,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }

    # Glassdoor URL pattern: KO<start>,<end> encodes keyword char positions after city slug
    # e.g. "israel-data-analyst" → KO7,18  (7 = len("israel-"), 18 = 7+len("data analyst"))
    for role in ROLES[:5]:
        try:
            slug  = role.lower().replace(" ", "-")
            ko_end = 7 + len(role)
            url = (
                f"https://www.glassdoor.com/Job/israel-{slug}-jobs-"
                f"SRCH_IL.0,6_IN119_KO7,{ko_end}.htm"
                f"?sortBy=date_desc"
            )
            resp = requests.get(url, headers=GD_HEADERS, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.content, "html.parser")

            # Glassdoor React app embeds job data in a <script> tag as JSON
            json_block = None
            for sc in soup.find_all("script"):
                txt = sc.string or ""
                if '"jobListings"' in txt or '"jobTitle"' in txt:
                    json_block = txt
                    break

            if json_block:
                # Extract JSON-like structures
                matches = re.findall(r'"jobTitle"\s*:\s*"([^"]+)".*?"employerName"\s*:\s*"([^"]+)".*?"jobListingId"\s*:\s*(\d+)', json_block)
                for title, company, jid in matches[:8]:
                    link = f"https://www.glassdoor.com/job-listing/j?jl={jid}"
                    exp  = extract_experience(title)
                    if not is_data_relevant(title) or not is_entry_level(title, exp):
                        continue
                    if link in cache["seen_urls"]:
                        continue
                    if any(bl in company.lower() for bl in COMPANY_BLACKLIST):
                        continue
                    job = {
                        "title":               title,
                        "company":             company,
                        "location":            "Israel",
                        "url":                 link,
                        "source":              "Glassdoor",
                        "posted":              "Recently",
                        "scraped_at":          datetime.now().isoformat(),
                        "experience_required": exp,
                    }
                    job["relevance_score"] = score_job(job)
                    jobs.append(job)
                    cache["seen_urls"].append(link)
            else:
                # Fallback: try static HTML selectors
                for card in soup.find_all("li", attrs={"data-test": "jobListing"})[:8]:
                    try:
                        title_el   = card.find(attrs={"data-test": "job-title"}) or card.find("span", class_=re.compile(r"job-?title", re.I))
                        company_el = card.find(attrs={"data-test": "emp-name"})  or card.find("span", class_=re.compile(r"employer|company", re.I))
                        link_el    = card.find("a", href=True)
                        if not title_el or not link_el:
                            continue
                        title   = title_el.get_text(strip=True)
                        company = company_el.get_text(strip=True) if company_el else "Unknown"
                        href    = link_el["href"]
                        link    = ("https://www.glassdoor.com" + href) if href.startswith("/") else href
                        exp     = extract_experience(title)
                        if not is_data_relevant(title) or not is_entry_level(title, exp):
                            continue
                        if link in cache["seen_urls"]:
                            continue
                        if any(bl in company.lower() for bl in COMPANY_BLACKLIST):
                            continue
                        job = {
                            "title":               title,
                            "company":             company,
                            "location":            "Israel",
                            "url":                 link,
                            "source":              "Glassdoor",
                            "posted":              "Recently",
                            "scraped_at":          datetime.now().isoformat(),
                            "experience_required": exp,
                        }
                        job["relevance_score"] = score_job(job)
                        jobs.append(job)
                        cache["seen_urls"].append(link)
                    except Exception:
                        continue

            time.sleep(1)
        except Exception as e:
            print(f"  Glassdoor error [{role}]: {e}")

    return jobs


# ── Search links (fallback) ───────────────────────────────────────────────────

def generate_search_links():
    links = []
    for role in ROLES:
        links += [
            {"title": f"LinkedIn: {role}",  "url": f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(role)}&location=Israel&f_E=2&sortBy=DD"},
            {"title": f"Jobmaster: {role}", "url": f"https://www.jobmaster.co.il/jobs/?q={quote_plus(role)}"},
            {"title": f"Drushim: {role}",   "url": f"https://www.drushim.co.il/jobs/search/{quote_plus(role)}/?experience=0-2&cities=2"},
            {"title": f"AllJobs: {role}",   "url": f"https://www.alljobs.co.il/SearchResultsGuest.aspx?position={quote_plus(role)}"},
        ]
    return links


# ── HTML report (legacy) ──────────────────────────────────────────────────────

def generate_html(jobs, search_links):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
    <meta charset="UTF-8">
    <title>DataHunt IL</title>
    <style>
        * {{ margin:0;padding:0;box-sizing:border-box; }}
        body {{ font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);padding:20px;direction:rtl; }}
        .container {{ max-width:1200px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden; }}
        .header {{ background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;padding:40px;text-align:center; }}
        .header h1 {{ font-size:48px; }}
        .stats {{ display:flex;justify-content:space-around;padding:30px;background:#f8f9fa; }}
        .stat-number {{ font-size:36px;font-weight:bold;color:#667eea; }}
        .jobs {{ padding:30px; }}
        .job-card {{ background:#fff;border:1px solid #e9ecef;border-radius:12px;padding:24px;margin-bottom:20px; }}
        .job-title {{ font-size:22px;font-weight:bold; }}
        .job-company {{ font-size:18px;color:#667eea; }}
        .badge {{ display:inline-block;background:#667eea;color:#fff;padding:4px 10px;border-radius:12px;font-size:12px;margin:4px 2px; }}
        .apply-btn {{ display:inline-block;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;padding:10px 28px;border-radius:8px;text-decoration:none;font-weight:bold;margin-top:12px; }}
    </style>
</head>
<body>
<div class="container">
    <div class="header"><h1>🎯 DataHunt IL</h1><p>עדכון אחרון: {now}</p></div>
    <div class="stats">
        <div class="stat"><div class="stat-number">{len(jobs)}</div><div>משרות חדשות</div></div>
        <div class="stat"><div class="stat-number">{len(set(j['company'] for j in jobs))}</div><div>חברות</div></div>
    </div>
    <div class="jobs">
"""
    for job in jobs:
        html += f"""
    <div class="job-card">
        <span class="badge">{job['source']}</span>
        <span class="badge" style="background:#28a745">{job.get('experience_required','Entry Level')}</span>
        <div class="job-title">{job['title']}</div>
        <div class="job-company">{job['company']}</div>
        <div>📍 {job['location']}</div>
        <a href="{job['url']}" target="_blank" class="apply-btn">הגש מועמדות →</a>
    </div>"""

    html += "</div></div></body></html>"
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("DataHunt IL - Starting job search...")
    print(f"Roles: {', '.join(ROLES)}")
    print(f"Hebrew roles: {', '.join(ROLES_HEBREW[:4])} ...")
    print(f"Locations: {', '.join(LOCATIONS)}\n")

    all_jobs = []

    _write_progress(5, "Starting parallel scan...", 0)

    # Run all scrapers simultaneously — each is I/O bound so threads are ideal
    scrapers = [
        ("LinkedIn",  scrape_linkedin),
        ("Jobmaster", scrape_jobmaster),
        ("Drushim",   scrape_drushim),
        ("Glassdoor", scrape_glassdoor),
        # AllJobs skipped — blocked by Radware bot protection
    ]

    completed = 0
    lock = __import__("threading").Lock()

    def _run(name, fn):
        nonlocal completed
        result = fn()
        with lock:
            completed += 1
            pct = 10 + int(completed / len(scrapers) * 80)
            _write_progress(pct, f"{name} done ({len(result)} found)...", len(all_jobs) + len(result))
            print(f"   {name}: +{len(result)} jobs")
        return result

    with ThreadPoolExecutor(max_workers=len(scrapers)) as ex:
        futures = {ex.submit(_run, name, fn): name for name, fn in scrapers}
        for future in as_completed(futures):
            try:
                all_jobs.extend(future.result())
            except Exception as e:
                print(f"  Scraper error: {e}")

    _write_progress(95, "Deduplicating and saving...", len(all_jobs))

    print(f"\nTotal new jobs (before dedup): {len(all_jobs)}")

    # Cross-site deduplication: remove jobs that match an already-collected job
    # from a different source (same company + similar title)
    deduped = []
    for job in all_jobs:
        if not is_cross_site_duplicate(job, deduped):
            deduped.append(job)
        else:
            print(f"  [dedup] {job['source']}: {job['title']} @ {job['company']}")
    removed = len(all_jobs) - len(deduped)
    if removed:
        print(f"  Removed {removed} cross-site duplicates")
    all_jobs = deduped

    print(f"Total new jobs (after dedup): {len(all_jobs)}")

    search_links = generate_search_links()

    # Save cache
    cache["last_run"] = datetime.now().isoformat()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    # Persist job data — merge new jobs using stricter duplicate check
    try:
        with open(JOBS_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        existing = []

    # One-time retroactive dedup of store: keep most-recent duplicate
    deduped_store = []
    for job in existing:
        if not is_duplicate_in_store(job, deduped_store):
            deduped_store.append(job)
    if len(deduped_store) < len(existing):
        print(f"  Cleaned {len(existing)-len(deduped_store)} existing duplicates from store")
    existing = deduped_store

    added = 0
    for job in all_jobs:
        if not is_duplicate_in_store(job, existing):
            existing.append(job)
            added += 1

    print(f"Jobs added to file: {added} (file total: {len(existing)})")
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    generate_html(all_jobs, search_links)
    _write_progress(100, f"Done! {added} new jobs added.", len(existing))
    print(f"\nDone! Open {OUTPUT_FILE} or run app.py for the web dashboard.")


if __name__ == "__main__":
    main()
