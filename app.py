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


@app.route("/api/config", methods=["GET"])
def api_config_get():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({"roles": DEFAULT_ROLES})


@app.route("/api/config", methods=["POST"])
def api_config_post():
    data  = request.get_json(silent=True) or {}
    roles = [r.strip() for r in data.get("roles", []) if r.strip()]
    if not roles:
        return jsonify({"ok": False, "message": "No roles provided"})
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"roles": roles}, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    if _status["running"]:
        return jsonify({"ok": False, "message": "Already running"})

    def run():
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

    threading.Thread(target=run, daemon=True).start()
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

<!-- HEADER -->
<div class="header">
  <div class="header-left">
    <h1>&#127919; DataHunt IL</h1>
    <p id="last-run-text">Loading...</p>
  </div>
  <div class="header-right">
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
  <div class="filter-row" style="flex-wrap:wrap;gap:6px">
    <span class="filter-label">Roles</span>
    <div class="role-chips" id="role-chips"></div>
    <select class="role-select" id="role-select" onchange="addRoleFromSelect(this)">
      <option value="">+ Add role...</option>
      <optgroup label="Data &amp; BI">
        <option>Data Analyst</option>
        <option>BI Developer</option>
        <option>BI Analyst</option>
        <option>Analytics Engineer</option>
        <option>Reporting Analyst</option>
        <option>Business Intelligence Developer</option>
      </optgroup>
      <optgroup label="Data Science &amp; AI">
        <option>Data Scientist</option>
        <option>Machine Learning Engineer</option>
        <option>AI Analyst</option>
        <option>AI Engineer</option>
        <option>NLP Engineer</option>
      </optgroup>
      <optgroup label="Engineering">
        <option>Data Engineer</option>
        <option>Software Developer</option>
        <option>Software Engineer</option>
        <option>Frontend Developer</option>
        <option>Backend Developer</option>
        <option>Full Stack Developer</option>
        <option>DevOps Engineer</option>
        <option>Python Developer</option>
        <option>Java Developer</option>
      </optgroup>
      <optgroup label="Product &amp; Design">
        <option>Product Manager</option>
        <option>Business Analyst</option>
        <option>UX Designer</option>
        <option>UI Designer</option>
        <option>QA Engineer</option>
      </optgroup>
    </select>
    <button class="save-roles-btn" onclick="clearRoles()" style="background:#2a1a1a;border-color:#7f1d1d;color:#f87171">Clear All</button>
    <button class="save-roles-btn" onclick="saveRoles()">&#128190; Save &amp; Apply</button>
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

<div class="toast" id="toast"></div>

<script>
let allJobs = [];
let timeFilter='all', sourceFilter='all', sortMode='relevance', viewMode='list';
let pollInterval = null;
const expandedCards = new Set();
const loadedDescs  = new Map();
let activeRoles = [];

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

// ── Role chip management ──────────────────────────────────────────────────────
function renderRoleChips(){
  document.getElementById('role-chips').innerHTML=activeRoles.map((r,i)=>
    `<span class="role-chip">${h(r)}<button class="chip-x" onclick="removeRole(${i})">&#215;</button></span>`
  ).join('');
  buildLinks();
}

function addRoleFromSelect(sel){
  const val=sel.value;
  sel.value='';
  if(!val) return;
  if(!activeRoles.map(r=>r.toLowerCase()).includes(val.toLowerCase()))
    activeRoles.push(val);
  renderRoleChips();
  renderJobs();
}

function removeRole(i){
  activeRoles.splice(i,1);
  renderRoleChips();
  renderJobs();
}

function clearRoles(){
  activeRoles=[];
  renderRoleChips();
  renderJobs();
}

async function saveRoles(){
  try{
    const r=await fetch('/api/config',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({roles:activeRoles})
    });
    const d=await r.json();
    showToast(d.ok?'Roles saved — next scan will use these roles':d.message||'Error saving');
  }catch{showToast('Could not save roles')}
}

async function loadConfig(){
  try{
    const d=await (await fetch('/api/config')).json();
    activeRoles=d.roles||[];
    renderRoleChips();
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
    const descHtml=isExp
      ? (loadedDescs.has(i)
          ? `<div class="card-desc">${h(loadedDescs.get(i))}</div>`
          : '<div class="card-loading"><div class="spinner"></div> Loading description...</div>')
      : '';
    return `<div class="job-card${isExp?' expanded':''}" id="card-${i}">
      <div class="card-header" onclick="toggleCard(${i},'${ha(j.url)}')">
        <div class="card-body-left">
          <div class="badges">
            <span class="badge ${srcClass(j.source)}">${h(j.source||'?')}</span>
            <span class="badge exp-badge">${h(exp)}</span>
            <span class="badge ${relClass(score)}">${relLabel(score)}</span>
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
  document.getElementById('links-grid').innerHTML=
    roles.flatMap(r=>SOURCES.map(s=>
      `<a class="search-link" href="${s.u(r)}" target="_blank" rel="noopener">${s.n}: ${h(r)}</a>`
    )).join('');
}

// Init
loadConfig().then(()=>{ loadJobs(); loadStats(); });

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
