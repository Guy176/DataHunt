#!/usr/bin/env python3
"""
DataHunt IL - Web Dashboard
Run: python app.py   →   http://localhost:5000
"""

from flask import Flask, jsonify, request
import json, subprocess, threading, os, sys, re
from datetime import datetime, timedelta

try:
    import requests
    from bs4 import BeautifulSoup
    _preview_ok = True
except ImportError:
    _preview_ok = False

app      = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DATA_DIR can be overridden via env var to point at a persistent volume on Railway
DATA_DIR    = os.environ.get("DATA_DIR", BASE_DIR)
JOBS_FILE      = os.path.join(DATA_DIR, "jobs_data.json")
CACHE_FILE     = os.path.join(DATA_DIR, "datahunt_cache.json")
SCRAPER_FILE   = os.path.join(BASE_DIR, "datahunt_scraper.py")
PROGRESS_FILE  = os.path.join(DATA_DIR, "scan_progress.json")
CONFIG_FILE    = os.path.join(DATA_DIR, "user_config.json")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_ROLES = [
    "Data Analyst", "BI Analyst", "BI Developer", "Junior Data Scientist",
    "AI Analyst", "Business Analyst", "Analytics Engineer",
]

_status = {"running": False, "message": "Idle"}


def _run_scan():
    _status["running"] = True
    _status["message"] = "Scanning..."
    try:
        env = {**os.environ, "DATA_DIR": DATA_DIR}
        subprocess.run([sys.executable, SCRAPER_FILE], cwd=BASE_DIR, env=env, timeout=600)
        _status["message"] = "Done"
    except subprocess.TimeoutExpired:
        _status["message"] = "Timed out"
    except Exception as e:
        _status["message"] = f"Error: {e}"
    finally:
        _status["running"] = False


def _auto_scan_worker():
    """Background thread: auto-trigger a scan when configured interval elapses."""
    import time as _time
    while True:
        _time.sleep(3600)
        try:
            with open(CONFIG_FILE, encoding="utf-8") as _f:
                _cfg = json.load(_f)
            interval = _cfg.get("auto_scan_hours")
            if not interval:
                continue
            _cache = load_cache()
            last_run = _cache.get("last_run")
            if last_run:
                elapsed = (datetime.now() - datetime.fromisoformat(last_run)).total_seconds() / 3600
                if elapsed < float(interval):
                    continue
            if not _status["running"]:
                threading.Thread(target=_run_scan, daemon=True).start()
        except Exception:
            pass


threading.Thread(target=_auto_scan_worker, daemon=True).start()

PREVIEW_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
}


def load_jobs():
    try:
        with open(JOBS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return []
    # Deduplicate by normalised title+company — keep the most-recently scraped copy
    seen = {}
    for job in raw:
        key = (
            re.sub(r"\s+", " ", (job.get("title") or "").lower().strip()),
            re.sub(r"\s+", " ", (job.get("company") or "").lower().strip()),
        )
        existing = seen.get(key)
        if existing is None:
            seen[key] = job
        else:
            # prefer whichever has a later scraped_at
            def _ts(j):
                s = j.get("scraped_at")
                try:
                    return datetime.fromisoformat(s) if s else datetime.min
                except Exception:
                    return datetime.min
            if _ts(job) > _ts(existing):
                seen[key] = job
    return list(seen.values())


def load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return DASHBOARD_HTML


@app.route("/api/jobs")
def api_jobs():
    return jsonify(load_jobs())


@app.route("/api/stats")
def api_stats():
    jobs  = load_jobs()
    cache = load_cache()
    now   = datetime.now()

    def ts(j):
        s = j.get("scraped_at")
        return datetime.fromisoformat(s) if s else None

    return jsonify({
        "total":     len(jobs),
        "today":     sum(1 for j in jobs if ts(j) and ts(j) >= now - timedelta(hours=24)),
        "week":      sum(1 for j in jobs if ts(j) and ts(j) >= now - timedelta(days=7)),
        "companies": len(set(j.get("company","") for j in jobs if j.get("company"))),
        "last_run":  cache.get("last_run"),
        "scraper":   _status,
    })


@app.route("/api/upload-resume", methods=["POST"])
def api_upload_resume():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "No file"})

    fname = f.filename.lower()
    text  = ""

    try:
        if fname.endswith(".pdf"):
            try:
                import pdfplumber, io
                with pdfplumber.open(io.BytesIO(f.read())) as pdf:
                    text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            except ImportError:
                return jsonify({"ok": False, "error": "pdfplumber not installed"})

        elif fname.endswith(".docx"):
            try:
                import docx, io
                doc  = docx.Document(io.BytesIO(f.read()))
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except ImportError:
                return jsonify({"ok": False, "error": "python-docx not installed"})

        else:
            return jsonify({"ok": False, "error": "Only PDF and DOCX files are supported"})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

    text = text.strip()[:8000]
    if not text:
        return jsonify({"ok": False, "error": "Could not extract text from file"})

    # Extract skills from resume text
    from datahunt_scraper import extract_skills_from_text
    skills = extract_skills_from_text(text)

    # Save to config
    payload = {}
    try:
        with open(CONFIG_FILE, encoding="utf-8") as cf:
            payload = json.load(cf)
    except Exception:
        pass
    payload["resume_text"] = text
    payload["skills"] = skills
    with open(CONFIG_FILE, "w", encoding="utf-8") as cf:
        json.dump(payload, cf, ensure_ascii=False, indent=2)

    return jsonify({"ok": True, "text": text, "skills": skills})


@app.route("/api/config", methods=["GET"])
def api_config_get():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({"roles": []})


@app.route("/api/config", methods=["POST"])
def api_config_post():
    data  = request.get_json(silent=True) or {}
    roles = [r.strip() for r in data.get("roles", []) if r.strip()]
    payload = {}
    # Preserve existing config fields
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        pass
    if roles:
        payload["roles"] = roles
    if "resume_text" in data:
        payload["resume_text"] = data["resume_text"]
        # Re-extract skills whenever resume text is updated
        from datahunt_scraper import extract_skills_from_text
        payload["skills"] = extract_skills_from_text(data["resume_text"])
    if "notes" in data:
        payload["notes"] = data["notes"]
    if "auto_scan_hours" in data:
        v = data["auto_scan_hours"]
        if v is None:
            payload.pop("auto_scan_hours", None)
        else:
            payload["auto_scan_hours"] = int(v)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    if _status["running"]:
        return jsonify({"ok": False, "message": "Already running"})
    threading.Thread(target=_run_scan, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/scan/status")
def api_scan_status():
    progress = {"pct": 0, "stage": "", "found": 0}
    try:
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            progress = json.load(f)
    except Exception:
        pass
    return jsonify({**_status, **progress})


@app.route("/api/preview")
def api_preview():
    """Fetch a job page and extract description + requirements for Quick View."""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL"})
    if not _preview_ok:
        return jsonify({"description": "Preview unavailable (missing requests/bs4)."})

    try:
        resp = requests.get(url, headers=PREVIEW_HEADERS, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        # Remove noise
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()

        desc = ""

        if "linkedin.com" in url:
            el = (
                soup.find("div", class_="show-more-less-html__markup") or
                soup.find("div", class_=re.compile(r"description__text")) or
                soup.find("section", class_=re.compile(r"description"))
            )
            if el:
                desc = el.get_text("\n", strip=True)

        elif "indeed.com" in url:
            el = (
                soup.find("div", id="jobDescriptionText") or
                soup.find("div", class_=re.compile(r"jobsearch-jobDescriptionText|jobDescription"))
            )
            if el:
                desc = el.get_text("\n", strip=True)

        elif "drushim.co.il" in url:
            el = (
                soup.find("div", class_=re.compile(r"job-description|description|job-content")) or
                soup.find("section", class_=re.compile(r"description"))
            )
            if el:
                desc = el.get_text("\n", strip=True)

        elif "alljobs.co.il" in url:
            el = (
                soup.find("div", class_=re.compile(r"job-description|content|description")) or
                soup.find("span", id=re.compile(r"description|job"))
            )
            if el:
                desc = el.get_text("\n", strip=True)

        # Generic fallback — find largest meaningful text block
        if not desc:
            candidates = soup.find_all(["div", "section", "article"])
            if candidates:
                best = max(candidates, key=lambda t: len(t.get_text(strip=True)))
                raw  = best.get_text("\n", strip=True)
                # Skip if it looks like a nav / boilerplate (too many short lines)
                lines = [l for l in raw.splitlines() if len(l.strip()) > 20]
                if len(lines) >= 3:
                    desc = "\n".join(lines)

        desc = desc[:3000].strip()
        if not desc:
            desc = "Description not available — please visit the original posting."

        return jsonify({"description": desc})

    except Exception as e:
        return jsonify({
            "description": f"Could not load preview ({e}). Please visit the original posting."
        })


# ── Skills gap ────────────────────────────────────────────────────────────────

@app.route("/api/skills-gap")
def api_skills_gap():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    user_skills = set(s.lower() for s in cfg.get("skills", []))
    if not user_skills:
        return jsonify({"ok": False, "error": "No resume uploaded yet"})

    from datahunt_scraper import TECH_VOCAB
    jobs  = load_jobs()
    total = len(jobs)
    if not total:
        return jsonify({"ok": False, "error": "No jobs scanned yet"})

    counts = {}
    for job in jobs:
        haystack = (job.get("title", "") + " " + job.get("experience_required", "")).lower()
        for skill in TECH_VOCAB:
            pat = r'\b' + re.escape(skill) + r'\b' if len(skill) <= 3 else None
            hit = (re.search(pat, haystack) if pat else skill in haystack)
            if hit and skill not in user_skills:
                counts[skill] = counts.get(skill, 0) + 1

    gap = sorted(
        [{"skill": s, "count": c, "pct": round(c * 100 / total)} for s, c in counts.items() if c >= 2],
        key=lambda x: -x["count"]
    )[:20]
    return jsonify({"ok": True, "gap": gap, "total_jobs": total, "user_skills": sorted(user_skills)})


# ── Resume profiles ────────────────────────────────────────────────────────────

@app.route("/api/profiles", methods=["GET"])
def api_profiles_get():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    return jsonify({"profiles": cfg.get("profiles", []), "active_profile": cfg.get("active_profile")})


@app.route("/api/profiles", methods=["POST"])
def api_profiles_post():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Name required"})
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    profiles = cfg.get("profiles", [])
    pid = str(int(datetime.now().timestamp()))
    profile = {
        "id":          pid,
        "name":        name,
        "resume_text": cfg.get("resume_text", ""),
        "skills":      cfg.get("skills", []),
        "roles":       cfg.get("roles", []),
    }
    profiles.append(profile)
    cfg["profiles"] = profiles[-3:]   # keep max 3
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True, "profile": profile})


@app.route("/api/profiles/<pid>/activate", methods=["POST"])
def api_profiles_activate(pid):
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return jsonify({"ok": False, "error": "No config"})
    profile = next((p for p in cfg.get("profiles", []) if p["id"] == pid), None)
    if not profile:
        return jsonify({"ok": False, "error": "Not found"})
    cfg["resume_text"]    = profile["resume_text"]
    cfg["skills"]         = profile["skills"]
    cfg["roles"]          = profile["roles"]
    cfg["active_profile"] = pid
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True, "profile": profile})


@app.route("/api/profiles/<pid>", methods=["DELETE"])
def api_profiles_delete(pid):
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return jsonify({"ok": False})
    cfg["profiles"] = [p for p in cfg.get("profiles", []) if p["id"] != pid]
    if cfg.get("active_profile") == pid:
        cfg.pop("active_profile", None)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


# ── Dashboard HTML ────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html><!-- DH_V3 -->
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>DataHunt IL</title>
<style>
/* ── reset ── */
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Tahoma,sans-serif;background:#0f0f1a;color:#e0e0e0;min-height:100vh}

/* ═══════════════ MOBILE-FIRST BASE ═══════════════ */

/* header */
.header{background:linear-gradient(135deg,#667eea,#764ba2);padding:16px;display:flex;flex-direction:column;gap:10px}
.header-left h1{font-size:22px;color:#fff}
.header-left p{font-size:12px;color:rgba(255,255,255,.75);margin-top:2px}
.header-right{display:flex;flex-direction:column;gap:8px;width:100%}
.scan-btn{background:rgba(255,255,255,.15);border:2px solid rgba(255,255,255,.5);color:#fff;padding:10px 20px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;transition:all .2s;width:100%}
.scan-btn:hover:not(:disabled){background:rgba(255,255,255,.28);border-color:#fff}
.scan-btn:disabled{opacity:.6;cursor:not-allowed}
.spinner{width:15px;height:15px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:spin .8s linear infinite;display:none}
.scan-btn.running .spinner{display:block}
@keyframes spin{to{transform:rotate(360deg)}}

/* progress bar */
.progress-wrap{display:none;flex-direction:column;gap:5px}
.progress-wrap.visible{display:flex}
.progress-track{background:rgba(255,255,255,.15);border-radius:99px;height:6px;overflow:hidden}
.progress-fill{height:100%;background:#fff;border-radius:99px;transition:width .6s ease;width:0%}
.progress-stage{font-size:11px;color:rgba(255,255,255,.8);text-align:center}

/* stats */
.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:12px 14px;background:#161625;border-bottom:1px solid #2a2a40}
.stat-card{background:#1e1e30;border:1px solid #2e2e48;border-radius:10px;padding:10px 14px;text-align:center}
.stat-number{font-size:22px;font-weight:700;color:#a78bfa}
.stat-label{font-size:10px;color:#888;margin-top:2px;text-transform:uppercase;letter-spacing:.4px}

/* filters */
.filters{display:flex;flex-direction:column;gap:6px;padding:10px 14px;background:#161625;border-bottom:1px solid #2a2a40}
.filter-row{display:flex;align-items:center;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:2px}
.filter-row::-webkit-scrollbar{height:2px}
.filter-row::-webkit-scrollbar-thumb{background:#3a3a58;border-radius:2px}
.filter-label{font-size:10px;color:#666;text-transform:uppercase;letter-spacing:.4px;white-space:nowrap;min-width:38px}
.filter-btn{background:#1e1e30;border:1px solid #2e2e48;color:#aaa;padding:5px 12px;border-radius:6px;font-size:12px;cursor:pointer;transition:all .15s;white-space:nowrap;flex-shrink:0}
.filter-btn:hover{border-color:#667eea;color:#fff}
.filter-btn.active{background:linear-gradient(135deg,#667eea,#764ba2);border-color:transparent;color:#fff;font-weight:600}
.search-box{width:100%;background:#1e1e30;border:1px solid #2e2e48;color:#e0e0e0;padding:8px 12px;border-radius:6px;font-size:14px;outline:none}
.search-box:focus{border-color:#667eea}
.search-box::placeholder{color:#555}

/* content */
.content{padding:12px 14px}
.result-count{font-size:11px;color:#666;margin-bottom:10px}

/* job cards — unified expandable card */
.jobs-container{display:flex;flex-direction:column;gap:10px}
.job-card{background:#1e1e30;border:1px solid #2e2e48;border-radius:12px;overflow:hidden;transition:border-color .18s}
.job-card.expanded{border-color:#667eea}
.card-header{padding:14px;cursor:pointer;display:flex;align-items:flex-start;gap:10px;-webkit-tap-highlight-color:transparent}
.card-header:active{background:rgba(102,126,234,.06)}
.card-body-left{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px}
.job-title{font-size:15px;font-weight:700;color:#fff;line-height:1.3;word-break:break-word}
.job-company{font-size:13px;color:#a78bfa;font-weight:500}
.job-meta{display:flex;gap:8px;font-size:11px;color:#666;flex-wrap:wrap}
.badges{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
.card-arrow{font-size:14px;color:#666;transition:transform .25s;flex-shrink:0;margin-top:2px;padding:2px 4px}
.job-card.expanded .card-arrow{transform:rotate(180deg);color:#a78bfa}

/* card expanded section */
.card-expand{display:none;border-top:1px solid #2a2a40;padding:14px}
.job-card.expanded .card-expand{display:block}
.card-desc{font-size:13px;line-height:1.7;color:#c0c0c0;white-space:pre-wrap;word-break:break-word;max-height:300px;overflow-y:auto;margin-bottom:12px}
.card-loading{display:flex;align-items:center;gap:8px;color:#888;font-size:13px;padding:8px 0}
.card-loading .spinner{display:block;border-color:#444;border-top-color:#a78bfa;width:16px;height:16px}
.expand-actions{display:flex;gap:8px;flex-wrap:wrap;padding-top:4px}

/* badges */
.badge{display:inline-block;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.2px}
.src-linkedin{background:#0a66c2;color:#fff}
.src-jobmaster{background:#c0392b;color:#fff}
.src-drushim{background:#e8532b;color:#fff}
.src-alljobs{background:#1a7f37;color:#fff}
.src-glassdoor{background:#0caa41;color:#fff}
.src-unknown{background:#444;color:#ccc}
.exp-badge{background:#1e3a2f;color:#4ade80;border:1px solid #166534}
.rel-high{background:#1a3a1a;color:#4ade80;border:1px solid #166534}
.rel-med{background:#2a2a10;color:#facc15;border:1px solid #854d0e}
.rel-low{background:#2a1a1a;color:#f87171;border:1px solid #7f1d1d}

/* role chips */
.role-chips{display:flex;flex-wrap:wrap;gap:5px;align-items:center;flex:1}
.role-chip{display:inline-flex;align-items:center;gap:3px;background:#1e2d4a;border:1px solid #3a5a9a;color:#7eb4f0;padding:3px 6px 3px 10px;border-radius:20px;font-size:12px;font-weight:600;white-space:nowrap}
.chip-x{background:none;border:none;color:#7eb4f0;cursor:pointer;font-size:15px;line-height:1;padding:0 2px;opacity:.7;transition:opacity .15s}
.chip-x:hover{opacity:1;color:#fff}
.role-select{background:#1e1e30;border:1px solid #2e2e48;color:#aaa;padding:5px 10px;border-radius:6px;font-size:12px;outline:none;flex-shrink:0;cursor:pointer;max-width:160px}
.role-select:focus{border-color:#667eea}
.role-select option,.role-select optgroup{background:#1e1e30;color:#e0e0e0}
.save-roles-btn{background:#1e2d4a;border:1px solid #3a5a9a;color:#7eb4f0;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;transition:all .15s;flex-shrink:0}
.save-roles-btn:hover{background:#2a3d6a;border-color:#667eea;color:#fff}

/* apply button */
.apply-link{display:inline-flex;align-items:center;justify-content:center;gap:6px;color:#fff;font-size:14px;font-weight:700;text-decoration:none;padding:11px 22px;border-radius:8px;border:none;background:linear-gradient(135deg,#667eea,#764ba2);transition:all .18s;width:100%}
.apply-link:hover{background:linear-gradient(135deg,#7c8fef,#8a5db5);transform:translateY(-1px);box-shadow:0 4px 16px rgba(102,126,234,.4)}

/* empty */
.empty{text-align:center;padding:50px 20px;color:#555}
.empty h2{font-size:18px;margin-bottom:8px;color:#666}

/* search links */
.links-section{padding:16px 14px 32px;border-top:1px solid #2a2a40}
.links-section h2{font-size:12px;color:#666;margin-bottom:10px;text-transform:uppercase;letter-spacing:.4px}
.links-grid{display:grid;grid-template-columns:1fr;gap:6px}
.search-link{background:#1e1e30;border:1px solid #2e2e48;color:#a78bfa;padding:9px 12px;border-radius:7px;text-decoration:none;font-size:12px;font-weight:500;transition:all .15s;display:block}
.search-link:hover{background:#26263d;border-color:#667eea;color:#fff}

/* toast */
.toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:#1e1e30;border:1px solid #667eea;color:#e0e0e0;padding:10px 18px;border-radius:8px;font-size:13px;opacity:0;transition:opacity .3s;pointer-events:none;z-index:999;white-space:nowrap}
.toast.show{opacity:1}

/* ── Wizard ── */
.wiz-screen{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}

/* Step 1 hero background */
#wiz-1{background:radial-gradient(ellipse at 60% 20%,rgba(102,126,234,.18) 0%,transparent 60%),radial-gradient(ellipse at 20% 80%,rgba(118,75,162,.15) 0%,transparent 55%),#0a0a14;position:relative;overflow:hidden}
#wiz-1::before{content:'';position:absolute;inset:0;background:url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23667eea' fill-opacity='0.03'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");pointer-events:none}
.wiz-hero-wrap{display:flex;flex-direction:column;align-items:center;width:100%;max-width:520px;gap:0}
.wiz-hero{text-align:center;padding:0 0 28px;position:relative}
.wiz-hero-badge{display:inline-block;background:rgba(102,126,234,.15);border:1px solid rgba(102,126,234,.35);color:#a78bfa;font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;padding:5px 14px;border-radius:99px;margin-bottom:20px}
.wiz-hero-title{font-size:36px;font-weight:900;line-height:1.15;color:#fff;letter-spacing:-.5px}
.wiz-hero-title span{background:linear-gradient(135deg,#667eea,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.wiz-hero-sub{font-size:14px;color:#6a6a8a;margin-top:12px;line-height:1.6;max-width:380px;margin-left:auto;margin-right:auto}
.wiz-card{background:rgba(18,18,30,.95);border:1px solid rgba(102,126,234,.2);border-radius:16px;padding:28px 24px;width:100%;max-width:520px;display:flex;flex-direction:column;gap:16px;box-shadow:0 24px 64px rgba(0,0,0,.5),0 0 0 1px rgba(255,255,255,.03)}
.wiz-card-step2{background:#161625;border:1px solid #2e2e48;box-shadow:none}
.wiz-card h2{font-size:20px;font-weight:700;color:#fff}
.wiz-card h3{font-size:12px;font-weight:700;color:#667eea;text-transform:uppercase;letter-spacing:.8px;margin-top:4px}
.wiz-sub{font-size:13px;color:#6a6a8a;line-height:1.6}
.wiz-textarea{width:100%;background:#0f0f1a;border:1px solid #2a2a3e;color:#e0e0e0;padding:12px;border-radius:8px;font-size:13px;line-height:1.6;resize:vertical;min-height:100px;outline:none;font-family:inherit;transition:border-color .15s}
.wiz-textarea:focus{border-color:#667eea}
.wiz-textarea::placeholder{color:#444}
.wiz-actions{display:flex;gap:10px;align-items:center;justify-content:flex-end;flex-wrap:wrap;margin-top:4px}
.wiz-btn{background:linear-gradient(135deg,#667eea,#764ba2);border:none;color:#fff;padding:13px 32px;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;transition:all .18s;box-shadow:0 4px 20px rgba(102,126,234,.35)}
.wiz-btn:hover{transform:translateY(-1px);box-shadow:0 6px 28px rgba(102,126,234,.5)}
.wiz-btn-ghost{background:transparent;border:1px solid #2e2e48;color:#777;padding:12px 18px;border-radius:8px;font-size:13px;cursor:pointer;transition:all .18s}
.wiz-btn-ghost:hover{border-color:#667eea;color:#a78bfa}
.wiz-skip{color:#444;font-size:13px;cursor:pointer;padding:10px;transition:color .15s;text-decoration:underline;text-underline-offset:3px}
.wiz-skip:hover{color:#888}
.wiz-back{background:none;border:none;color:#666;font-size:13px;cursor:pointer;padding:0 0 4px;text-align:left;transition:color .15s}
.wiz-back:hover{color:#fff}
.wiz-roles-area{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:12px 14px;background:#1e1e30;border:1px solid #2e2e48;border-radius:8px;min-height:52px}
.role-chip{gap:6px;padding:5px 8px 5px 12px;font-size:12px}

/* Custom dropdown */
.custom-dd-wrap{position:relative;flex-shrink:0}
.custom-dd-btn{background:#1e1e30;border:1px solid #2e2e48;color:#a78bfa;padding:7px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;transition:all .15s;white-space:nowrap}
.custom-dd-btn:hover{border-color:#667eea;color:#fff}
.custom-dd-list{display:none;position:absolute;top:calc(100% + 4px);left:0;min-width:220px;background:#1a1a2e;border:1px solid #2e2e48;border-radius:10px;box-shadow:0 16px 40px rgba(0,0,0,.6);z-index:200;overflow:hidden;max-height:300px;overflow-y:auto}
.custom-dd-list.open{display:block}
.custom-dd-cat{font-size:10px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;color:#667eea;padding:12px 14px 5px;background:rgba(102,126,234,.06);border-top:1px solid #2a2a40}
.custom-dd-cat:first-child{border-top:none}
.custom-dd-item{padding:9px 18px;font-size:13px;color:#c0c0d0;cursor:pointer;transition:background .12s}
.custom-dd-item:hover{background:rgba(102,126,234,.15);color:#fff}
/* Scan progress screen */
.wiz-scan{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;padding:40px 20px;background:#0f0f1a;text-align:center}
.wiz-scan-logo{font-size:26px;font-weight:800;color:#fff}
.wiz-scan h2{font-size:17px;color:#b0b0c0;font-weight:500}
.wiz-progress-track{width:100%;max-width:440px;background:#1e1e30;border-radius:99px;height:8px;overflow:hidden;border:1px solid #2e2e48}
.wiz-progress-fill{height:100%;background:linear-gradient(90deg,#667eea,#a78bfa);border-radius:99px;width:5%;transition:width .7s ease}
.wiz-stage{font-size:13px;color:#888;min-height:20px}
.wiz-found{font-size:12px;color:#555}
/* file upload zone */
.upload-zone{display:flex;flex-direction:column;align-items:center;gap:6px;padding:20px;border:2px dashed #2e2e48;border-radius:10px;cursor:pointer;transition:border-color .2s,background .2s;background:#1a1a2a;text-align:center}
.upload-zone:hover,.upload-zone.drag-over{border-color:#667eea;background:#1e1e38}
.upload-icon{font-size:28px;line-height:1}
.upload-text{font-size:13px;color:#aaa}
.upload-link{color:#a78bfa;cursor:pointer;text-decoration:underline}
.upload-hint{font-size:11px;color:#555}
.upload-status{font-size:12px;min-height:16px;font-weight:600}
.upload-status.ok{color:#4ade80}
.upload-status.err{color:#f87171}
.upload-status.loading{color:#facc15}
/* prefs button in results header */
.prefs-btn{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.3);color:rgba(255,255,255,.85);padding:7px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;transition:all .15s}
.prefs-btn:hover{background:rgba(255,255,255,.22);color:#fff}

/* ── Application tracker ── */
.status-row{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.status-btn{border:1px solid #2e2e48;background:#1e1e30;color:#666;padding:4px 11px;border-radius:20px;font-size:11px;font-weight:700;cursor:pointer;opacity:.6;transition:all .15s}
.status-btn:hover{opacity:1;border-color:#667eea;color:#fff}
.status-btn.active{opacity:1}
.status-btn.active.s-saved{background:#1e2d4a;color:#7eb4f0;border-color:#3a5a9a}
.status-btn.active.s-applied{background:#1e3a2f;color:#4ade80;border-color:#166534}
.status-btn.active.s-interviewing{background:#2a2a10;color:#facc15;border-color:#854d0e}
.status-btn.active.s-rejected{background:#2a1a1a;color:#f87171;border-color:#7f1d1d}
.status-clear{background:none;border:none;color:#444;cursor:pointer;font-size:13px;line-height:1;padding:0 4px;transition:color .15s}
.status-clear:hover{color:#f87171}
/* pipeline row */
.pipeline{display:flex;gap:14px;padding:7px 14px;background:#12121f;border-bottom:1px solid #2a2a40;flex-wrap:wrap;align-items:center}
.pipeline-lbl{font-size:10px;color:#444;text-transform:uppercase;letter-spacing:.4px;margin-right:4px}
.pipeline-item{display:flex;align-items:center;gap:5px;font-size:12px;color:#666}
.pipeline-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.pipeline-count{font-weight:700;color:#e0e0e0}
/* NEW + stale badges */
.new-badge{background:#7c3aed;color:#fff}
.stale-badge{background:#292929;color:#555;border:1px solid #333}
.stale-card .job-title{color:#888}
.stale-card .job-company{color:#666}
/* score breakdown */
.breakdown{background:#0f0f1a;border-radius:8px;padding:10px 12px;margin-bottom:10px}
.breakdown-title{color:#555;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px}
.breakdown-row{display:flex;align-items:center;gap:8px;margin-bottom:5px}
.breakdown-label{color:#777;font-size:11px;min-width:76px}
.breakdown-bar-wrap{flex:1;background:#1e1e30;border-radius:3px;height:5px;overflow:hidden}
.breakdown-bar{height:100%;border-radius:3px}
.breakdown-val{font-size:11px;color:#aaa;font-weight:700;min-width:30px;text-align:right}
.breakdown-skills{margin-top:7px;font-size:11px;color:#666}
.breakdown-skill-tag{display:inline-block;background:#1e2d4a;color:#7eb4f0;border:1px solid #3a5a9a;padding:2px 7px;border-radius:10px;margin:2px 2px 0 0;font-size:11px}
/* skills gap modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:600;display:flex;align-items:center;justify-content:center;padding:20px}
.modal{background:#161625;border:1px solid #2e2e48;border-radius:14px;padding:24px;max-width:500px;width:100%;max-height:80vh;overflow-y:auto}
.modal h2{font-size:17px;color:#fff;margin-bottom:4px}
.modal-sub{font-size:12px;color:#555;margin-bottom:16px}
.gap-item{display:flex;align-items:center;gap:10px;margin-bottom:7px}
.gap-skill{font-size:12px;color:#e0e0e0;min-width:110px;font-weight:600}
.gap-bar-wrap{flex:1;background:#1e1e30;border-radius:3px;height:6px;overflow:hidden}
.gap-bar{height:100%;background:linear-gradient(90deg,#667eea,#a78bfa);border-radius:3px}
.gap-pct{font-size:11px;color:#666;min-width:36px;text-align:right}
.modal-close{background:none;border:1px solid #2e2e48;color:#777;padding:6px 16px;border-radius:6px;cursor:pointer;font-size:12px;margin-top:14px;transition:all .15s}
.modal-close:hover{border-color:#667eea;color:#fff}
/* profiles */
.profile-list{display:flex;gap:7px;flex-wrap:wrap}
.profile-chip{display:inline-flex;align-items:center;gap:4px;background:#1a1a2e;border:1px solid #2e2e48;color:#888;padding:5px 10px;border-radius:20px;font-size:12px;cursor:pointer;transition:all .15s}
.profile-chip:hover{border-color:#667eea;color:#fff}
.profile-chip.active-profile{background:#1e2d4a;border-color:#3a5a9a;color:#7eb4f0}
.profile-chip-x{background:none;border:none;color:#555;cursor:pointer;font-size:13px;line-height:1;padding:0 2px;transition:color .15s}
.profile-chip-x:hover{color:#f87171}
/* action buttons (Export / Skills Gap) */
.action-btn{background:#1e1e30;border:1px solid #2e2e48;color:#a78bfa;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;transition:all .15s;white-space:nowrap}
.action-btn:hover{border-color:#667eea;color:#fff}
/* auto-scan toggle */
.autoscan-row{display:flex;align-items:center;gap:10px;margin-top:8px;flex-wrap:wrap}
.toggle-wrap{display:flex;align-items:center;gap:8px;font-size:13px;color:#888;cursor:pointer}
.tog{position:relative;width:36px;height:20px;flex-shrink:0}
.tog input{opacity:0;width:0;height:0}
.tog-slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#2e2e48;border-radius:20px;transition:.3s}
.tog-slider:before{position:absolute;content:'';width:14px;height:14px;left:3px;bottom:3px;background:#555;border-radius:50%;transition:.3s}
.tog input:checked+.tog-slider{background:#667eea}
.tog input:checked+.tog-slider:before{transform:translateX(16px);background:#fff}
.autoscan-hours{background:#1e1e30;border:1px solid #2e2e48;color:#e0e0e0;padding:4px 8px;border-radius:6px;font-size:12px;width:58px;outline:none}
.autoscan-hours:focus{border-color:#667eea}
.autoscan-hours:disabled{opacity:.4}

/* ═══════════════ DESKTOP ENHANCEMENTS ═══════════════ */
@media(min-width:700px){
  .header{flex-direction:row;align-items:center;padding:22px 40px;gap:20px}
  .header-right{flex-direction:row;align-items:center;width:auto;gap:14px}
  .scan-btn{width:auto}
  .header-left h1{font-size:28px}
  .stats{display:flex;flex-wrap:wrap;padding:16px 40px;gap:14px}
  .stat-card{flex:1;min-width:110px;padding:12px 22px}
  .stat-number{font-size:26px}
  .stat-label{font-size:11px}
  .filters{flex-direction:row;flex-wrap:wrap;align-items:center;padding:12px 40px;gap:10px}
  .filter-row{overflow-x:visible;padding-bottom:0}
  .search-box{width:220px;font-size:13px;padding:6px 12px;margin-left:auto}
  .content{padding:22px 40px}
  .jobs-container.grid-mode{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
  .links-section{padding:20px 40px 40px}
  .links-grid{grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}
  .toast{left:auto;right:22px;transform:none}
}
</style>
</head>
<body>

<!-- ══ WIZARD ══ -->
<div id="wiz">

  <!-- Step 1: Resume -->
  <div id="wiz-1" class="wiz-screen">
    <div class="wiz-hero-wrap">
      <div class="wiz-hero">
        <div class="wiz-hero-badge">&#127919; DataHunt IL</div>
        <div class="wiz-hero-title">Your next role,<br><span>found faster.</span></div>
        <p class="wiz-hero-sub">Real-time job scraping across Israeli job boards — ranked and filtered to match you.</p>
      </div>
      <div class="wiz-card">
        <div>
          <h2>Let's personalise your search</h2>
          <p class="wiz-sub" style="margin-top:6px">Upload your CV so we can rank results by how well they match your background.</p>
        </div>
        <label class="upload-zone" id="upload-zone" ondragover="event.preventDefault()" ondrop="handleDrop(event)">
          <input type="file" id="resume-file" accept=".pdf,.docx" style="display:none" onchange="handleFileSelect(this)">
          <div class="upload-icon">&#128196;</div>
          <div class="upload-text" id="upload-text">Drop your CV here or <span class="upload-link" onclick="document.getElementById('resume-file').click();event.stopPropagation()">browse</span></div>
          <div class="upload-hint">PDF or Word (.docx) &bull; max 5MB</div>
          <div class="upload-status" id="upload-status"></div>
        </label>
        <div id="profile-section" style="display:none">
          <div style="font-size:11px;color:#555;margin-bottom:6px;text-transform:uppercase;letter-spacing:.4px">Saved profiles</div>
          <div class="profile-list" id="profile-list"></div>
        </div>
        <div style="display:flex;align-items:center;gap:10px;color:#333;font-size:12px"><div style="flex:1;height:1px;background:#2a2a3e"></div>or paste below<div style="flex:1;height:1px;background:#2a2a3e"></div></div>
        <textarea id="resume-input" class="wiz-textarea" placeholder="Describe your skills and experience...&#10;E.g. 2 years as BI Developer, strong Power BI and SQL, looking for data/analytics roles in Tel Aviv."></textarea>
        <div class="wiz-actions">
          <span class="wiz-skip" onclick="goStep(2)">Skip for now</span>
          <button class="wiz-btn-ghost" id="save-profile-btn" style="display:none" onclick="saveAsProfilePrompt()">&#9733; Save Profile</button>
          <button class="wiz-btn" onclick="saveResumeAndNext()">Next &#8594;</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Step 2: Preferences -->
  <div id="wiz-2" class="wiz-screen" style="display:none;background:#0a0a14">
    <div class="wiz-card wiz-card-step2" style="max-width:520px">
      <button class="wiz-back" onclick="goStep(1)">&#8592; Back</button>
      <div>
        <h2>What roles are you looking for?</h2>
        <p class="wiz-sub" style="margin-top:6px">Select from the list — these filter your results and guide the scan.</p>
      </div>
      <div class="wiz-roles-area" id="wiz-roles-area">
        <div id="wiz-role-chips" style="display:contents"></div>
        <div class="custom-dd-wrap">
          <button class="custom-dd-btn" onclick="toggleDropdown(event)">&#43; Add role</button>
          <div class="custom-dd-list" id="role-dd-list">
            <div class="custom-dd-cat">Data &amp; BI</div>
            <div class="custom-dd-item" onclick="addRoleItem('Data Analyst')">Data Analyst</div>
            <div class="custom-dd-item" onclick="addRoleItem('BI Developer')">BI Developer</div>
            <div class="custom-dd-item" onclick="addRoleItem('BI Analyst')">BI Analyst</div>
            <div class="custom-dd-item" onclick="addRoleItem('Analytics Engineer')">Analytics Engineer</div>
            <div class="custom-dd-item" onclick="addRoleItem('Reporting Analyst')">Reporting Analyst</div>
            <div class="custom-dd-item" onclick="addRoleItem('Business Intelligence Developer')">Business Intelligence Developer</div>
            <div class="custom-dd-cat">Data Science &amp; AI</div>
            <div class="custom-dd-item" onclick="addRoleItem('Data Scientist')">Data Scientist</div>
            <div class="custom-dd-item" onclick="addRoleItem('Machine Learning Engineer')">Machine Learning Engineer</div>
            <div class="custom-dd-item" onclick="addRoleItem('AI Analyst')">AI Analyst</div>
            <div class="custom-dd-item" onclick="addRoleItem('AI Engineer')">AI Engineer</div>
            <div class="custom-dd-item" onclick="addRoleItem('NLP Engineer')">NLP Engineer</div>
            <div class="custom-dd-cat">Engineering</div>
            <div class="custom-dd-item" onclick="addRoleItem('Data Engineer')">Data Engineer</div>
            <div class="custom-dd-item" onclick="addRoleItem('Software Developer')">Software Developer</div>
            <div class="custom-dd-item" onclick="addRoleItem('Software Engineer')">Software Engineer</div>
            <div class="custom-dd-item" onclick="addRoleItem('Frontend Developer')">Frontend Developer</div>
            <div class="custom-dd-item" onclick="addRoleItem('Backend Developer')">Backend Developer</div>
            <div class="custom-dd-item" onclick="addRoleItem('Full Stack Developer')">Full Stack Developer</div>
            <div class="custom-dd-item" onclick="addRoleItem('DevOps Engineer')">DevOps Engineer</div>
            <div class="custom-dd-item" onclick="addRoleItem('Python Developer')">Python Developer</div>
            <div class="custom-dd-item" onclick="addRoleItem('Java Developer')">Java Developer</div>
            <div class="custom-dd-cat">Product &amp; Design</div>
            <div class="custom-dd-item" onclick="addRoleItem('Product Manager')">Product Manager</div>
            <div class="custom-dd-item" onclick="addRoleItem('Business Analyst')">Business Analyst</div>
            <div class="custom-dd-item" onclick="addRoleItem('UX Designer')">UX Designer</div>
            <div class="custom-dd-item" onclick="addRoleItem('UI Designer')">UI Designer</div>
            <div class="custom-dd-item" onclick="addRoleItem('QA Engineer')">QA Engineer</div>
          </div>
        </div>
        <button class="save-roles-btn" onclick="clearRoles()" style="background:#2a1a1a;border-color:#7f1d1d;color:#f87171;flex-shrink:0">Clear All</button>
      </div>
      <h3>Any extra preferences?</h3>
      <textarea id="notes-input" class="wiz-textarea" style="min-height:78px" placeholder="E.g. prefer Tel Aviv / Ramat Gan, not heavy ETL, Python automation a plus, hybrid ok..."></textarea>
      <div class="autoscan-row">
        <label class="toggle-wrap">
          <label class="tog"><input type="checkbox" id="autoscan-toggle" onchange="toggleAutoScan(this.checked)"><span class="tog-slider"></span></label>
          Auto-scan every
        </label>
        <input class="autoscan-hours" id="autoscan-hours" type="number" min="1" max="168" value="24" disabled>
        <span style="font-size:12px;color:#555">hours</span>
      </div>
      <div class="wiz-actions">
        <button class="wiz-btn-ghost" onclick="goResults()" id="view-existing-btn" style="display:none">View existing results</button>
        <button class="wiz-btn" onclick="wizStartScan()">&#128269; Start Scan</button>
      </div>
    </div>
  </div>

  <!-- Step 3: Scanning -->
  <div id="wiz-3" class="wiz-scan" style="display:none">
    <div class="wiz-scan-logo">&#127919; DataHunt IL</div>
    <h2>Scanning job boards...</h2>
    <div class="wiz-progress-track"><div class="wiz-progress-fill" id="wiz-fill"></div></div>
    <div class="wiz-stage" id="wiz-stage">Starting...</div>
    <div class="wiz-found" id="wiz-found"></div>
  </div>

</div><!-- /wiz -->

<!-- ══ RESULTS ══ -->
<div id="results-wrap" style="display:none">

<!-- HEADER -->
<div class="header">
  <div class="header-left">
    <h1>&#127919; DataHunt IL</h1>
    <p id="last-run-text">Loading...</p>
  </div>
  <div class="header-right">
    <button class="prefs-btn" onclick="goStep(2);showWizard()">&#9881; Preferences</button>
    <div class="progress-wrap" id="progress-wrap">
      <div class="progress-track"><div class="progress-fill" id="progress-fill"></div></div>
      <div class="progress-stage" id="progress-stage"></div>
    </div>
    <button class="scan-btn" id="scan-btn" onclick="startScan()">
      <div class="spinner"></div>
      <span id="scan-label">&#128269; Scan Now</span>
    </button>
  </div>
</div>

<!-- STATS -->
<div class="stats">
  <div class="stat-card"><div class="stat-number" id="s-total">-</div><div class="stat-label">Total Jobs</div></div>
  <div class="stat-card"><div class="stat-number" id="s-today">-</div><div class="stat-label">Today</div></div>
  <div class="stat-card"><div class="stat-number" id="s-week">-</div><div class="stat-label">This Week</div></div>
  <div class="stat-card"><div class="stat-number" id="s-co">-</div><div class="stat-label">Companies</div></div>
</div>

<!-- PIPELINE -->
<div class="pipeline" id="pipeline-row">
  <span class="pipeline-lbl">Tracking:</span>
  <span class="pipeline-item"><span class="pipeline-dot" style="background:#7eb4f0"></span><span class="pipeline-count" id="p-saved">0</span>&nbsp;Saved</span>
  <span class="pipeline-item"><span class="pipeline-dot" style="background:#4ade80"></span><span class="pipeline-count" id="p-applied">0</span>&nbsp;Applied</span>
  <span class="pipeline-item"><span class="pipeline-dot" style="background:#facc15"></span><span class="pipeline-count" id="p-interviewing">0</span>&nbsp;Interviewing</span>
  <span class="pipeline-item"><span class="pipeline-dot" style="background:#f87171"></span><span class="pipeline-count" id="p-rejected">0</span>&nbsp;Rejected</span>
</div>

<!-- FILTERS -->
<div class="filters">
  <div class="filter-row">
    <span class="filter-label">Period</span>
    <button class="filter-btn active" onclick="setFilter('time','all',this)">All</button>
    <button class="filter-btn" onclick="setFilter('time','today',this)">Today</button>
    <button class="filter-btn" onclick="setFilter('time','week',this)">This Week</button>
  </div>
  <div class="filter-row">
    <span class="filter-label">Source</span>
    <button class="filter-btn active" onclick="setFilter('source','all',this)">All</button>
    <button class="filter-btn" onclick="setFilter('source','LinkedIn',this)">LinkedIn</button>
    <button class="filter-btn" onclick="setFilter('source','Jobmaster',this)">Jobmaster</button>
    <button class="filter-btn" onclick="setFilter('source','Drushim',this)">Drushim</button>
    <button class="filter-btn" onclick="setFilter('source','Glassdoor',this)">Glassdoor</button>
  </div>
  <div class="filter-row">
    <span class="filter-label">Sort</span>
    <button class="filter-btn active" onclick="setFilter('sort','relevance',this)">Relevance</button>
    <button class="filter-btn" onclick="setFilter('sort','date',this)">Date</button>
    <span class="filter-label" style="margin-left:10px">View</span>
    <button class="filter-btn active" onclick="setFilter('view','list',this)">&#9776; List</button>
    <button class="filter-btn" onclick="setFilter('view','grid',this)">&#9783; Grid</button>
  </div>
  <div class="filter-row" style="gap:6px">
    <button class="action-btn" onclick="openGapModal()">&#128270; Skills Gap</button>
    <button class="action-btn" onclick="exportCSV()">&#8595; Export CSV</button>
  </div>
  <input class="search-box" id="search-input" type="text" placeholder="&#128269; Search title or company..." oninput="renderJobs()">
</div>

<!-- JOBS -->
<div class="content">
  <div class="result-count" id="result-count"></div>
  <div class="jobs-container" id="jobs-container"><div class="empty"><h2>Loading...</h2></div></div>
</div>

<!-- DIRECT SEARCH LINKS -->
<div class="links-section">
  <h2>&#128269; Direct Search Links</h2>
  <div class="links-grid" id="links-grid"></div>
</div>

<!-- SKILLS GAP MODAL -->
<div id="gap-modal" class="modal-overlay" style="display:none" onclick="if(event.target===this)closeGapModal()">
  <div class="modal">
    <h2>&#128270; Skills Gap Analysis</h2>
    <p class="modal-sub" id="gap-sub">Skills appearing in your target jobs that aren&#39;t on your resume.</p>
    <div id="gap-list" style="min-height:60px"></div>
    <div id="gap-you" style="margin-top:14px;font-size:11px;color:#444;line-height:1.8"></div>
    <button class="modal-close" onclick="closeGapModal()">Close</button>
  </div>
</div>

<div class="toast" id="toast"></div>

</div><!-- /results-wrap -->

<script>
let allJobs = [];
let timeFilter='all', sourceFilter='all', sortMode='relevance', viewMode='list';
let pollInterval = null;
const expandedCards = new Set();
const loadedDescs  = new Map();
let activeRoles = [];

// ── Persistent state ──────────────────────────────────────────────────────────
let jobStatuses = {};   // url → 'saved'|'applied'|'interviewing'|'rejected'
let lastVisitTime = null;

function _saveStatuses(){ try{localStorage.setItem('dh_statuses',JSON.stringify(jobStatuses));}catch{} }
function _loadStatuses(){ try{jobStatuses=JSON.parse(localStorage.getItem('dh_statuses')||'{}');}catch{jobStatuses={};} }
_loadStatuses();

const SOURCES = [
  {n:"LinkedIn", u:r=>`https://www.linkedin.com/jobs/search/?keywords=${enc(r)}&location=Israel&f_E=2&sortBy=DD`},
  {n:"Jobmaster",u:r=>`https://www.jobmaster.co.il/jobs/?q=${enc(r)}`},
  {n:"Drushim",  u:r=>`https://www.drushim.co.il/jobs/search/${enc(r)}/?experience=0-2&cities=2`},
  {n:"Glassdoor",u:r=>`https://www.glassdoor.com/Job/israel-${r.toLowerCase().replace(/ /g,'-')}-jobs-SRCH_IL.0,6_IN119.htm`},
];

function enc(s){return encodeURIComponent(s)}
function h(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function ha(s){return String(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;')}

function srcClass(s){
  const m={linkedin:'src-linkedin',jobmaster:'src-jobmaster',drushim:'src-drushim',alljobs:'src-alljobs',glassdoor:'src-glassdoor'};
  return m[(s||'').toLowerCase()]||'src-unknown';
}
function relClass(s){return s>=70?'rel-high':s>=45?'rel-med':'rel-low'}
function relLabel(s){return s+'% match'}

function fmtDate(iso){
  if(!iso||iso==='Recently'||iso==='Last 7 days') return iso||'';
  try{
    const d=new Date(iso),now=new Date(),h=(now-d)/3600000;
    if(h<1)  return 'Just now';
    if(h<24) return 'Today '+d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
    if(h<48) return 'Yesterday';
    return d.toLocaleDateString('en-GB',{day:'2-digit',month:'short'});
  }catch{return iso}
}

function isNew(j){
  if(!j.scraped_at||!lastVisitTime) return false;
  try{return new Date(j.scraped_at)>new Date(lastVisitTime);}catch{return false;}
}
function isStale(j){
  if(!j.scraped_at) return false;
  try{return (new Date()-new Date(j.scraped_at))>14*24*3600000;}catch{return false;}
}

// ── Pipeline ──────────────────────────────────────────────────────────────────
function renderPipeline(){
  const counts={saved:0,applied:0,interviewing:0,rejected:0};
  Object.values(jobStatuses).forEach(s=>{ if(counts[s]!==undefined) counts[s]++; });
  ['saved','applied','interviewing','rejected'].forEach(k=>{
    const el=document.getElementById('p-'+k);
    if(el) el.textContent=counts[k];
  });
}

// ── Application status ────────────────────────────────────────────────────────
function setJobStatus(url, status, e){
  if(e) e.stopPropagation();
  if(status==='') delete jobStatuses[url];
  else            jobStatuses[url]=status;
  _saveStatuses();
  renderPipeline();
  renderJobs();
}

// ── Export CSV ────────────────────────────────────────────────────────────────
function exportCSV(){
  const filtered=applyFilters(allJobs);
  if(!filtered.length){showToast('No jobs to export');return;}
  const cols=['title','company','location','source','relevance_score','experience_required','posted','url'];
  const esc=v=>'"'+(String(v||'').replace(/"/g,'""'))+'"';
  const rows=[cols.join(','),...filtered.map(j=>cols.map(c=>esc(j[c])).join(','))];
  const blob=new Blob([rows.join('\n')],{type:'text/csv'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='datahunt_jobs.csv';
  a.click();
  showToast('Exported '+filtered.length+' jobs');
}

// ── Skills Gap Modal ──────────────────────────────────────────────────────────
async function openGapModal(){
  document.getElementById('gap-modal').style.display='flex';
  document.getElementById('gap-list').innerHTML='<div style="color:#555;font-size:13px;padding:20px 0;text-align:center">Loading...</div>';
  try{
    const d=await (await fetch('/api/skills-gap')).json();
    if(!d.ok){
      document.getElementById('gap-list').innerHTML=`<div style="color:#f87171;font-size:13px">${h(d.error)}</div>`;
      return;
    }
    document.getElementById('gap-sub').textContent=
      'Skills appearing in your target jobs that aren\'t on your resume. Based on '+d.total_jobs+' jobs.';
    const maxC=d.gap[0]?d.gap[0].count:1;
    document.getElementById('gap-list').innerHTML=d.gap.length
      ? d.gap.map(g=>`<div class="gap-item">
          <span class="gap-skill">${h(g.skill)}</span>
          <div class="gap-bar-wrap"><div class="gap-bar" style="width:${Math.round(g.count/maxC*100)}%"></div></div>
          <span class="gap-pct">${g.pct}%</span>
        </div>`).join('')
      : '<div style="color:#4ade80;font-size:13px;padding:10px 0">Great news — no significant skill gaps found!</div>';
    if(d.user_skills&&d.user_skills.length){
      document.getElementById('gap-you').innerHTML=
        '<span style="color:#444;font-size:10px;text-transform:uppercase;letter-spacing:.4px">Your resume skills:</span><br>'+
        d.user_skills.map(s=>`<span class="breakdown-skill-tag">${h(s)}</span>`).join('');
    }
  }catch(e){
    document.getElementById('gap-list').innerHTML=`<div style="color:#f87171;font-size:13px">Error: ${h(e.message)}</div>`;
  }
}
function closeGapModal(){ document.getElementById('gap-modal').style.display='none'; }

// ── Resume Profiles ───────────────────────────────────────────────────────────
let savedProfiles=[], activeProfileId=null;

async function loadProfiles(){
  try{
    const d=await (await fetch('/api/profiles')).json();
    savedProfiles=d.profiles||[];
    activeProfileId=d.active_profile||null;
    renderProfileChips();
    const sec=document.getElementById('profile-section');
    const btn=document.getElementById('save-profile-btn');
    if(sec) sec.style.display=savedProfiles.length?'':'none';
    if(btn) btn.style.display='';
  }catch{}
}

function renderProfileChips(){
  const el=document.getElementById('profile-list');
  if(!el) return;
  el.innerHTML=savedProfiles.map(p=>`
    <span class="profile-chip${p.id===activeProfileId?' active-profile':''}" onclick="activateProfile('${ha(p.id)}')">
      ${h(p.name)}
      <button class="profile-chip-x" onclick="deleteProfile('${ha(p.id)}',event)">&#215;</button>
    </span>`).join('');
  const sec=document.getElementById('profile-section');
  if(sec) sec.style.display=savedProfiles.length?'':'none';
}

async function saveAsProfilePrompt(){
  const name=prompt('Profile name (e.g. "Data Analyst", "BI Focus"):','');
  if(!name||!name.trim()) return;
  const d=await (await fetch('/api/profiles',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name.trim()})})).json();
  if(d.ok){ savedProfiles.push(d.profile); renderProfileChips(); showToast('Profile saved: '+name); }
  else showToast(d.error||'Could not save profile');
}

async function activateProfile(pid){
  const d=await (await fetch('/api/profiles/'+pid+'/activate',{method:'POST'})).json();
  if(d.ok){
    activeProfileId=pid;
    renderProfileChips();
    const p=d.profile;
    if(p.resume_text){ document.getElementById('resume-input').value=p.resume_text; }
    if(p.roles){ activeRoles=p.roles; renderRoleChips(); }
    showToast('Profile loaded');
  }
}

async function deleteProfile(pid, e){
  if(e) e.stopPropagation();
  savedProfiles=savedProfiles.filter(p=>p.id!==pid);
  if(activeProfileId===pid) activeProfileId=null;
  renderProfileChips();
  await fetch('/api/profiles/'+pid,{method:'DELETE'});
}

// ── Auto-scan toggle ──────────────────────────────────────────────────────────
async function toggleAutoScan(on){
  const hoursEl=document.getElementById('autoscan-hours');
  if(hoursEl) hoursEl.disabled=!on;
  const hours=on?(parseInt(hoursEl&&hoursEl.value)||24):null;
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({auto_scan_hours:hours})});
}

async function loadAutoScanState(){
  try{
    const d=await (await fetch('/api/config')).json();
    const h=d.auto_scan_hours;
    const tog=document.getElementById('autoscan-toggle');
    const hrs=document.getElementById('autoscan-hours');
    if(tog&&h){ tog.checked=true; if(hrs){hrs.value=h;hrs.disabled=false;} }
  }catch{}
}

// ── Filters ───────────────────────────────────────────────────────────────────
function setFilter(type,val,btn){
  if(type==='time')   timeFilter=val;
  if(type==='source') sourceFilter=val;
  if(type==='sort')   sortMode=val;
  if(type==='view')   viewMode=val;
  btn.closest('.filter-row').querySelectorAll('.filter-btn').forEach(b=>{
    if(b.getAttribute('onclick')&&b.getAttribute('onclick').includes("'"+type+"'"))
      b.classList.remove('active');
  });
  btn.classList.add('active');
  renderJobs();
}

function applyFilters(jobs){
  const now=new Date();
  const q=document.getElementById('search-input').value.toLowerCase().trim();
  return jobs.filter(j=>{
    if(timeFilter!=='all'){
      if(!j.scraped_at) return false;
      const dh=(now-new Date(j.scraped_at))/3600000;
      if(timeFilter==='today'&&dh>24)  return false;
      if(timeFilter==='week' &&dh>168) return false;
    }
    if(sourceFilter!=='all'&&(j.source||'').toLowerCase()!==sourceFilter.toLowerCase()) return false;
    if(activeRoles.length>0){
      const t=(j.title||'').toLowerCase();
      if(!activeRoles.some(r=>t.includes(r.toLowerCase()))) return false;
    }
    if(q){const hay=((j.title||'')+' '+(j.company||'')).toLowerCase();if(!hay.includes(q))return false;}
    return true;
  });
}

// ── Resume file upload ────────────────────────────────────────────────────────
function handleFileSelect(input){
  if(input.files[0]) uploadResume(input.files[0]);
}
function handleDrop(e){
  e.preventDefault();
  document.getElementById('upload-zone').classList.remove('drag-over');
  const file=e.dataTransfer.files[0];
  if(file) uploadResume(file);
}
document.addEventListener('DOMContentLoaded',()=>{
  const zone=document.getElementById('upload-zone');
  if(zone){
    zone.addEventListener('dragover',()=>zone.classList.add('drag-over'));
    zone.addEventListener('dragleave',()=>zone.classList.remove('drag-over'));
  }
});

async function uploadResume(file){
  const status=document.getElementById('upload-status');
  const text=document.getElementById('upload-text');
  if(file.size>5*1024*1024){status.className='upload-status err';status.textContent='File too large (max 5MB)';return;}
  if(!file.name.match(/\.(pdf|docx)$/i)){status.className='upload-status err';status.textContent='Only PDF or .docx files';return;}

  status.className='upload-status loading';
  status.textContent='Extracting text...';
  text.innerHTML='<span style="color:#888">'+h(file.name)+'</span>';

  const fd=new FormData();
  fd.append('file',file);
  try{
    const r=await fetch('/api/upload-resume',{method:'POST',body:fd});
    const d=await r.json();
    if(d.ok){
      document.getElementById('resume-input').value=d.text;
      status.className='upload-status ok';
      status.textContent='Resume loaded — '+d.text.split(' ').length+' words extracted';
      const btn=document.getElementById('save-profile-btn');
      if(btn) btn.style.display='';
    } else {
      status.className='upload-status err';
      status.textContent=d.error||'Upload failed';
    }
  }catch{
    status.className='upload-status err';
    status.textContent='Upload failed — try pasting text instead';
  }
}

// ── Wizard navigation ─────────────────────────────────────────────────────────
function goStep(n){
  [1,2,3].forEach(i=>{
    const el=document.getElementById('wiz-'+i);
    if(el) el.style.display=i===n?'':' none';
  });
  // fix: proper show/hide
  document.getElementById('wiz-1').style.display=n===1?'':'none';
  document.getElementById('wiz-2').style.display=n===2?'':'none';
  document.getElementById('wiz-3').style.display=n===3?'flex':'none';
}

function showWizard(step){
  document.getElementById('wiz').style.display='';
  document.getElementById('results-wrap').style.display='none';
  goStep(step||1);
}

function goResults(){
  document.getElementById('wiz').style.display='none';
  document.getElementById('results-wrap').style.display='';
  localStorage.setItem('datahunt_done','1');
  // Record the current time as "last visit" BEFORE loading so new jobs on THIS load get the badge
  lastVisitTime = localStorage.getItem('dh_last_visit');
  localStorage.setItem('dh_last_visit', new Date().toISOString());
  loadJobs(); loadStats(); renderPipeline();
}

async function saveResumeAndNext(){
  const resume=document.getElementById('resume-input').value.trim();
  if(resume){
    await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({resume_text:resume})});
  }
  goStep(2);
}

async function wizStartScan(){
  const notes=document.getElementById('notes-input').value.trim();
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({roles:activeRoles,notes})});

  goStep(3);
  document.getElementById('wiz-fill').style.width='5%';
  document.getElementById('wiz-stage').textContent='Starting...';
  document.getElementById('wiz-found').textContent='';

  try{
    const r=await fetch('/api/scan',{method:'POST'});
    const d=await r.json();
    if(!d.ok){showToast(d.message||'Already running — showing existing results');goResults();return;}
  }catch{showToast('Could not start scan');goResults();return;}

  const poll=setInterval(async()=>{
    try{
      const st=await (await fetch('/api/scan/status')).json();
      if(st.pct) document.getElementById('wiz-fill').style.width=st.pct+'%';
      if(st.stage) document.getElementById('wiz-stage').textContent=st.stage;
      if(st.found) document.getElementById('wiz-found').textContent=st.found+' jobs found so far';
      if(!st.running){
        clearInterval(poll);
        document.getElementById('wiz-fill').style.width='100%';
        document.getElementById('wiz-stage').textContent='Done!';
        setTimeout(()=>goResults(),800);
      }
    }catch{}
  },2500);
}

// ── Role chip management ──────────────────────────────────────────────────────
function renderRoleChips(){
  const html=activeRoles.map((r,i)=>
    `<span class="role-chip">${h(r)}<button class="chip-x" onclick="removeRole(${i})">&#215;</button></span>`
  ).join('');
  // render in wizard and results (if they exist)
  const wc=document.getElementById('wiz-role-chips');
  if(wc) wc.innerHTML=html;
  buildLinks();
}

function toggleDropdown(e){
  e.stopPropagation();
  document.getElementById('role-dd-list').classList.toggle('open');
}
function addRoleItem(val){
  document.getElementById('role-dd-list').classList.remove('open');
  if(!val) return;
  if(!activeRoles.map(r=>r.toLowerCase()).includes(val.toLowerCase()))
    activeRoles.push(val);
  renderRoleChips(); renderJobs();
}
document.addEventListener('click',()=>{
  const dd=document.getElementById('role-dd-list');
  if(dd) dd.classList.remove('open');
});
// keep old select handler for results filters if present
function addRoleFromSelect(sel){
  const val=sel.value; sel.value='';
  if(!val) return;
  addRoleItem(val);
}

function removeRole(i){
  activeRoles.splice(i,1);
  renderRoleChips(); renderJobs();
}

function clearRoles(){
  activeRoles=[];
  renderRoleChips(); renderJobs();
}

async function loadConfig(){
  try{
    const d=await (await fetch('/api/config')).json();
    activeRoles=d.roles||[];
    renderRoleChips();
    if(d.resume_text){
      document.getElementById('resume-input').value=d.resume_text;
      const btn=document.getElementById('save-profile-btn');
      if(btn) btn.style.display='';
    }
    if(d.notes) document.getElementById('notes-input').value=d.notes;
  }catch{}
}

// ── Render ────────────────────────────────────────────────────────────────────
function renderJobs(){
  const filtered=applyFilters(allJobs);
  document.getElementById('result-count').textContent=`Showing ${filtered.length} of ${allJobs.length} jobs`;
  const container=document.getElementById('jobs-container');

  if(!filtered.length){
    container.className='jobs-container';
    container.innerHTML='<div class="empty"><h2>No jobs match your filters</h2><p>Try adjusting filters or run a new scan.</p></div>';
    return;
  }

  if(sortMode==='relevance') filtered.sort((a,b)=>(b.relevance_score||0)-(a.relevance_score||0));
  else filtered.sort((a,b)=>{
    if(!a.scraped_at&&!b.scraped_at)return 0;
    if(!a.scraped_at)return 1;if(!b.scraped_at)return -1;
    return new Date(b.scraped_at)-new Date(a.scraped_at);
  });

  container.className='jobs-container'+(viewMode==='grid'?' grid-mode':'');

  const urlIdx=new Map(allJobs.map((j,i)=>[j.url,i]));

  container.innerHTML=filtered.map(j=>{
    const i=urlIdx.get(j.url)??-1;
    const exp=j.experience_required||'Entry Level';
    const score=j.relevance_score||0;
    const isExp=expandedCards.has(i);
    const stale=isStale(j);
    const curStatus=jobStatuses[j.url]||'';

    const descHtml=isExp
      ? (loadedDescs.has(i)
          ? `<div class="card-desc">${h(loadedDescs.get(i))}</div>`
          : '<div class="card-loading"><div class="spinner"></div> Loading description...</div>')
      : '';

    // Score breakdown (only in expanded cards that have breakdown data)
    const bd=j.score_breakdown||{};
    const breakdownHtml=isExp&&bd.role!==undefined?`
      <div class="breakdown">
        <div class="breakdown-title">Match Breakdown</div>
        <div class="breakdown-row">
          <span class="breakdown-label">Role fit</span>
          <div class="breakdown-bar-wrap"><div class="breakdown-bar" style="width:${Math.round(bd.role/52*100)}%;background:#667eea"></div></div>
          <span class="breakdown-val">${bd.role}/52</span>
        </div>
        <div class="breakdown-row">
          <span class="breakdown-label">Tech match</span>
          <div class="breakdown-bar-wrap"><div class="breakdown-bar" style="width:${Math.round(Math.max(0,bd.tech)/28*100)}%;background:#a78bfa"></div></div>
          <span class="breakdown-val">${bd.tech}/28</span>
        </div>
        <div class="breakdown-row">
          <span class="breakdown-label">Location</span>
          <div class="breakdown-bar-wrap"><div class="breakdown-bar" style="width:${Math.round((bd.location+10)/20*100)}%;background:#4ade80"></div></div>
          <span class="breakdown-val">${bd.location>0?'+':''}${bd.location}</span>
        </div>
        <div class="breakdown-row">
          <span class="breakdown-label">Exp fit</span>
          <div class="breakdown-bar-wrap"><div class="breakdown-bar" style="width:${Math.round(bd.exp/10*100)}%;background:#facc15"></div></div>
          <span class="breakdown-val">${bd.exp}/10</span>
        </div>
        ${bd.matched_skills&&bd.matched_skills.length?`<div class="breakdown-skills">Matched: ${bd.matched_skills.slice(0,8).map(s=>`<span class="breakdown-skill-tag">${h(s)}</span>`).join('')}</div>`:''}
      </div>`:'';

    // Application status buttons (only in expanded cards)
    const statusBtns=isExp?`
      <div class="status-row">
        <span style="font-size:11px;color:#555;margin-right:2px">Track:</span>
        ${['saved','applied','interviewing','rejected'].map(s=>`
          <button class="status-btn${curStatus===s?' active s-'+s:''}" onclick="setJobStatus('${ha(j.url)}','${s}',event)">${s.charAt(0).toUpperCase()+s.slice(1)}</button>`).join('')}
        ${curStatus?`<button class="status-clear" title="Clear status" onclick="setJobStatus('${ha(j.url)}','',event)">&#10005;</button>`:''}
      </div>`:'';

    return `<div class="job-card${isExp?' expanded':''}${stale?' stale-card':''}" id="card-${i}">
      <div class="card-header" onclick="toggleCard(${i},'${ha(j.url)}')">
        <div class="card-body-left">
          <div class="badges">
            <span class="badge ${srcClass(j.source)}">${h(j.source||'?')}</span>
            <span class="badge exp-badge">${h(exp)}</span>
            <span class="badge ${relClass(score)}">${relLabel(score)}</span>
            ${isNew(j)?'<span class="badge new-badge">NEW</span>':''}
            ${stale?'<span class="badge stale-badge">Old</span>':''}
            ${curStatus?`<span class="badge" style="background:#2a2a3a;color:#888;border:1px solid #3a3a50">${curStatus}</span>`:''}
          </div>
          <div class="job-title">${h(j.title||'Untitled')}</div>
          <div class="job-company">${h(j.company||'')}</div>
          <div class="job-meta">
            ${j.location?`<span>&#128205; ${h(j.location)}</span>`:''}
            ${j.scraped_at?`<span>&#128336; ${fmtDate(j.scraped_at)}</span>`:''}
          </div>
        </div>
        <div class="card-arrow">&#9660;</div>
      </div>
      <div class="card-expand">
        ${statusBtns}
        ${breakdownHtml}
        <div id="desc-${i}">${descHtml}</div>
        <div class="expand-actions">
          <a class="apply-link" href="${ha(j.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Open Job Page &#8594;</a>
        </div>
      </div>
    </div>`;
  }).join('');
}

// ── Expand / collapse ─────────────────────────────────────────────────────────
function toggleCard(i, url){
  if(expandedCards.has(i)){
    expandedCards.delete(i);
  } else {
    expandedCards.add(i);
    if(!loadedDescs.has(i)) fetchDesc(i, url);
  }
  renderJobs();
  // Scroll card into view after toggle
  requestAnimationFrame(()=>{
    const el=document.getElementById('card-'+i);
    if(el) el.scrollIntoView({behavior:'smooth',block:'nearest'});
  });
}

function fetchDesc(i, url){
  fetch(`/api/preview?url=${encodeURIComponent(url)}`)
    .then(r=>r.json())
    .then(data=>{
      loadedDescs.set(i, data.description||'No description available.');
      const el=document.getElementById('desc-'+i);
      if(el) el.innerHTML=`<div class="card-desc">${h(loadedDescs.get(i))}</div>`;
    })
    .catch(()=>{
      loadedDescs.set(i,'Could not load description — please use the Open Job Page button.');
      const el=document.getElementById('desc-'+i);
      if(el) el.innerHTML=`<div class="card-desc">${h(loadedDescs.get(i))}</div>`;
    });
}

// ── Data loading ──────────────────────────────────────────────────────────────
async function loadJobs(){
  try{
    allJobs=await (await fetch('/api/jobs')).json();
    renderJobs();
  }catch(e){
    document.getElementById('jobs-container').innerHTML=
      `<div class="empty"><h2>Failed to load jobs</h2><p>${e.message}</p></div>`;
  }
}

async function loadStats(){
  try{
    const s=await (await fetch('/api/stats')).json();
    document.getElementById('s-total').textContent=s.total;
    document.getElementById('s-today').textContent=s.today;
    document.getElementById('s-week').textContent =s.week;
    document.getElementById('s-co').textContent   =s.companies;
    document.getElementById('last-run-text').textContent=
      s.last_run?'Last scan: '+fmtDate(s.last_run):'No scans yet — click Scan Now';
  }catch(e){}
}

// ── Scan + progress ───────────────────────────────────────────────────────────
async function startScan(){
  const btn=document.getElementById('scan-btn');
  const lbl=document.getElementById('scan-label');
  btn.disabled=true; btn.classList.add('running');
  lbl.textContent='Scanning...';
  showProgress(5,'Starting scan...');
  try{
    const r=await (await fetch('/api/scan',{method:'POST'})).json();
    if(!r.ok){showToast(r.message||'Already running');stopScan(btn,lbl);return;}
  }catch{showToast('Could not start scan');stopScan(btn,lbl);return;}

  pollInterval=setInterval(async()=>{
    try{
      const st=await (await fetch('/api/scan/status')).json();
      if(st.pct) showProgress(st.pct, st.stage||'Scanning...');
      if(!st.running){
        clearInterval(pollInterval);
        showProgress(100,'Done!');
        setTimeout(()=>hideProgress(),2000);
        stopScan(btn,lbl);
        showToast('Scan complete — refreshing...');
        await loadJobs(); await loadStats();
      }
    }catch{}
  },2500);
}

function stopScan(btn,lbl){
  btn.disabled=false; btn.classList.remove('running');
  lbl.innerHTML='&#128269; Scan Now';
}
function showProgress(pct,stage){
  document.getElementById('progress-wrap').classList.add('visible');
  document.getElementById('progress-fill').style.width=pct+'%';
  document.getElementById('progress-stage').textContent=stage;
}
function hideProgress(){
  document.getElementById('progress-wrap').classList.remove('visible');
}

function showToast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg; t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),3500);
}

function buildLinks(){
  const roles=activeRoles.length>0?activeRoles:['Data Analyst','BI Developer','BI Analyst'];
  const el=document.getElementById('links-grid');
  if(el) el.innerHTML=roles.flatMap(r=>SOURCES.map(s=>
    `<a class="search-link" href="${s.u(r)}" target="_blank" rel="noopener">${s.n}: ${h(r)}</a>`
  )).join('');
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init(){
  await loadConfig();
  await loadProfiles();
  await loadAutoScanState();
  _loadStatuses();
  const done=localStorage.getItem('datahunt_done');
  if(done){
    const jobs=await (await fetch('/api/jobs')).json();
    if(jobs.length>0){
      allJobs=jobs;
      lastVisitTime=localStorage.getItem('dh_last_visit');
      localStorage.setItem('dh_last_visit', new Date().toISOString());
      renderJobs(); loadStats(); renderPipeline();
      goResults();
      const vb=document.getElementById('view-existing-btn');
      if(vb) vb.style.display='';
    } else {
      showWizard(2);
    }
  } else {
    showWizard(1);
  }
  fetch('/api/jobs').then(r=>r.json()).then(jobs=>{
    const vb=document.getElementById('view-existing-btn');
    if(vb&&jobs.length>0) vb.style.display='';
  });
}

init();

</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print()
    print("  DataHunt IL Dashboard")
    print("  " + "=" * 38)
    print(f"  Open your browser:  http://localhost:{port}")
    print("  Press Ctrl+C to stop")
    print()
    app.run(debug=False, port=port, host="0.0.0.0")
