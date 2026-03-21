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
JOBS_FILE   = os.path.join(DATA_DIR, "jobs_data.json")
CACHE_FILE  = os.path.join(DATA_DIR, "datahunt_cache.json")
SCRAPER_FILE = os.path.join(BASE_DIR, "datahunt_scraper.py")
os.makedirs(DATA_DIR, exist_ok=True)

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
    return jsonify(_status)


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

/* ── header ── */
.header{background:linear-gradient(135deg,#667eea,#764ba2);padding:26px 40px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px}
.header-left h1{font-size:30px;color:#fff}
.header-left p{font-size:13px;color:rgba(255,255,255,.75);margin-top:3px}
.scan-btn{background:rgba(255,255,255,.15);border:2px solid rgba(255,255,255,.5);color:#fff;padding:9px 24px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:8px;transition:all .2s}
.scan-btn:hover:not(:disabled){background:rgba(255,255,255,.28);border-color:#fff}
.scan-btn:disabled{opacity:.6;cursor:not-allowed}
.spinner{width:15px;height:15px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:spin .8s linear infinite;display:none}
.scan-btn.running .spinner{display:block}
@keyframes spin{to{transform:rotate(360deg)}}

/* ── stats ── */
.stats{display:flex;gap:14px;padding:18px 40px;background:#161625;border-bottom:1px solid #2a2a40;flex-wrap:wrap}
.stat-card{background:#1e1e30;border:1px solid #2e2e48;border-radius:10px;padding:12px 22px;text-align:center;flex:1;min-width:100px}
.stat-number{font-size:26px;font-weight:700;color:#a78bfa}
.stat-label{font-size:11px;color:#888;margin-top:3px;text-transform:uppercase;letter-spacing:.4px}

/* ── filters ── */
.filters{display:flex;align-items:center;gap:10px;padding:14px 40px;background:#161625;border-bottom:1px solid #2a2a40;flex-wrap:wrap}
.filter-label{font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.4px;margin-right:2px}
.filter-btn{background:#1e1e30;border:1px solid #2e2e48;color:#aaa;padding:6px 14px;border-radius:6px;font-size:12px;cursor:pointer;transition:all .15s}
.filter-btn:hover{border-color:#667eea;color:#fff}
.filter-btn.active{background:linear-gradient(135deg,#667eea,#764ba2);border-color:transparent;color:#fff;font-weight:600}
.search-box{margin-left:auto;background:#1e1e30;border:1px solid #2e2e48;color:#e0e0e0;padding:6px 12px;border-radius:6px;font-size:13px;width:210px;outline:none}
.search-box:focus{border-color:#667eea}
.search-box::placeholder{color:#555}

/* ── content area ── */
.content{padding:22px 40px}
.result-count{font-size:12px;color:#666;margin-bottom:14px}

/* ── grid view ── */
.jobs-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}

/* ── list view ── */
.jobs-list{display:flex;flex-direction:column;gap:8px}
.list-row{background:#1e1e30;border:1px solid #2e2e48;border-radius:10px;padding:12px 18px;display:flex;align-items:center;gap:14px;transition:all .18s;cursor:default;flex-wrap:wrap}
.list-row:hover{border-color:#667eea;box-shadow:0 2px 12px rgba(102,126,234,.15)}
.list-badges{display:flex;gap:5px;flex-shrink:0;flex-wrap:wrap}
.list-main{flex:1;min-width:200px}
.list-title{font-size:14px;font-weight:700;color:#fff}
.list-company{font-size:12px;color:#a78bfa}
.list-meta{display:flex;gap:10px;font-size:11px;color:#666;flex-shrink:0;flex-wrap:wrap}
.list-actions{display:flex;gap:7px;flex-shrink:0}

/* ── full view ── */
.jobs-full{display:flex;flex-direction:column;gap:16px}
.full-card{background:#1e1e30;border:1px solid #2e2e48;border-radius:12px;padding:22px;display:flex;flex-direction:column;gap:10px;transition:border-color .18s}
.full-card:hover{border-color:#667eea}
.full-header{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:10px}
.full-title{font-size:18px;font-weight:700;color:#fff}
.full-company{font-size:14px;color:#a78bfa;font-weight:500;margin-top:2px}
.full-badges{display:flex;gap:6px;flex-wrap:wrap}
.full-meta{display:flex;gap:14px;font-size:12px;color:#666;flex-wrap:wrap;border-top:1px solid #2a2a40;padding-top:10px}
.full-actions{display:flex;gap:8px}

/* ── job card (grid) ── */
.job-card{background:#1e1e30;border:1px solid #2e2e48;border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:7px;transition:all .18s;cursor:default}
.job-card:hover{border-color:#667eea;box-shadow:0 4px 20px rgba(102,126,234,.15);transform:translateY(-1px)}

/* badges */
.badges{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.badge{display:inline-block;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.2px}
.src-linkedin{background:#0a66c2;color:#fff}
.src-jobmaster{background:#c0392b;color:#fff}
.src-drushim{background:#e8532b;color:#fff}
.src-alljobs{background:#1a7f37;color:#fff}
.src-glassdoor{background:#0caa41;color:#fff}
.src-unknown{background:#444;color:#ccc}
.exp-badge{background:#1e3a2f;color:#4ade80;border:1px solid #166534}
.rel-high{background:#1a3a1a;color:#4ade80;border:1px solid #166534}
.rel-med {background:#2a2a10;color:#facc15;border:1px solid #854d0e}
.rel-low {background:#2a1a1a;color:#f87171;border:1px solid #7f1d1d}

.job-title{font-size:15px;font-weight:700;color:#fff;line-height:1.3}
.job-company{font-size:13px;color:#a78bfa;font-weight:500}
.job-meta{display:flex;gap:12px;font-size:12px;color:#666;flex-wrap:wrap}

/* card actions */
.card-actions{display:flex;gap:8px;margin-top:6px}
.quickview-btn{background:#2a2a40;border:1px solid #3a3a58;color:#a78bfa;padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;transition:all .15s}
.quickview-btn:hover{background:#3a3a58;border-color:#667eea;color:#fff}
.apply-link{display:inline-flex;align-items:center;gap:4px;color:#a78bfa;font-size:12px;font-weight:600;text-decoration:none;padding:6px 14px;border-radius:6px;border:1px solid #3a3a58;background:#2a2a40;transition:all .15s}
.apply-link:hover{background:#3a3a58;border-color:#667eea;color:#fff}

/* ── empty ── */
.empty{grid-column:1/-1;text-align:center;padding:60px 20px;color:#555}
.empty h2{font-size:20px;margin-bottom:10px;color:#666}

/* ── MODAL ── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:1000;display:none;align-items:center;justify-content:center;padding:20px}
.modal-overlay.open{display:flex}
.modal{background:#1a1a2e;border:1px solid #2e2e48;border-radius:14px;width:100%;max-width:720px;max-height:88vh;display:flex;flex-direction:column;overflow:hidden}
.modal-header{padding:20px 24px 16px;border-bottom:1px solid #2a2a40;display:flex;flex-direction:column;gap:8px}
.modal-close{position:absolute;top:14px;right:20px;background:none;border:none;color:#888;font-size:22px;cursor:pointer;line-height:1;transition:color .15s}
.modal-close:hover{color:#fff}
.modal-header{position:relative}
.modal-badges{display:flex;gap:6px;flex-wrap:wrap}
.modal-title{font-size:20px;font-weight:700;color:#fff;padding-right:28px}
.modal-company{font-size:14px;color:#a78bfa;font-weight:500}
.modal-meta{display:flex;gap:14px;font-size:12px;color:#666;flex-wrap:wrap}
.modal-body{padding:20px 24px;overflow-y:auto;flex:1}
.modal-body pre{white-space:pre-wrap;word-break:break-word;font-family:'Segoe UI',sans-serif;font-size:13px;line-height:1.7;color:#d0d0d0}
.modal-loading{display:flex;align-items:center;gap:10px;color:#888;font-size:14px}
.modal-loading .spinner{display:block;border-color:#444;border-top-color:#a78bfa;width:18px;height:18px}
.modal-footer{padding:14px 24px;border-top:1px solid #2a2a40;display:flex;justify-content:flex-end;gap:8px}
.modal-apply-btn{background:linear-gradient(135deg,#667eea,#764ba2);border:none;color:#fff;padding:9px 24px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}

/* ── search links ── */
.links-section{padding:20px 40px 40px;border-top:1px solid #2a2a40}
.links-section h2{font-size:14px;color:#666;margin-bottom:12px;text-transform:uppercase;letter-spacing:.4px}
.links-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:7px}
.search-link{background:#1e1e30;border:1px solid #2e2e48;color:#a78bfa;padding:9px 12px;border-radius:7px;text-decoration:none;font-size:12px;font-weight:500;transition:all .15s;display:block}
.search-link:hover{background:#26263d;border-color:#667eea;color:#fff}

/* ── toast ── */
.toast{position:fixed;bottom:22px;right:22px;background:#1e1e30;border:1px solid #667eea;color:#e0e0e0;padding:11px 18px;border-radius:8px;font-size:13px;opacity:0;transition:opacity .3s;pointer-events:none;z-index:999}
.toast.show{opacity:1}

@media(max-width:700px){
  .header,.stats,.filters,.content,.links-section{padding-left:12px;padding-right:12px}
  .header{flex-direction:column;align-items:flex-start;gap:10px}
  .scan-btn{width:100%}
  .header-left h1{font-size:22px}
  .stats{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .stat-card{padding:10px 14px;min-width:unset}
  .stat-number{font-size:20px}
  .jobs-grid{grid-template-columns:1fr}
  .filters{flex-direction:column;align-items:flex-start;gap:6px;overflow-x:hidden}
  .filters>div{margin-left:0!important;overflow-x:auto;max-width:100%;padding-bottom:4px;-webkit-overflow-scrolling:touch}
  .filter-label{white-space:nowrap}
  .search-box{width:100%;margin-left:0;box-sizing:border-box}
  .list-meta,.list-actions{display:none}
  .full-meta{gap:8px}
  .modal{max-height:96vh;margin:0;border-radius:12px 12px 0 0;position:fixed;bottom:0;left:0;right:0;width:100%}
  .modal-overlay{align-items:flex-end;padding:0}
  .links-grid{grid-template-columns:1fr}
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
  <button class="scan-btn" id="scan-btn" onclick="startScan()">
    <div class="spinner" id="spinner"></div>
    <span id="scan-label">&#128269; Scan Now</span>
  </button>
</div>

<!-- STATS -->
<div class="stats">
  <div class="stat-card"><div class="stat-number" id="s-total">-</div><div class="stat-label">Total Jobs</div></div>
  <div class="stat-card"><div class="stat-number" id="s-today">-</div><div class="stat-label">Found Today</div></div>
  <div class="stat-card"><div class="stat-number" id="s-week">-</div><div class="stat-label">This Week</div></div>
  <div class="stat-card"><div class="stat-number" id="s-co">-</div><div class="stat-label">Companies</div></div>
</div>

<!-- FILTERS -->
<div class="filters">
  <div style="display:flex;align-items:center;gap:6px">
    <span class="filter-label">Period</span>
    <button class="filter-btn active" onclick="setTime('all',this)">All Time</button>
    <button class="filter-btn" onclick="setTime('today',this)">Today</button>
    <button class="filter-btn" onclick="setTime('week',this)">This Week</button>
  </div>
  <div style="display:flex;align-items:center;gap:6px;margin-left:14px">
    <span class="filter-label">Source</span>
    <button class="filter-btn active" onclick="setSource('all',this)">All</button>
    <button class="filter-btn" onclick="setSource('LinkedIn',this)">LinkedIn</button>
    <button class="filter-btn" onclick="setSource('Jobmaster',this)">Jobmaster</button>
    <button class="filter-btn" onclick="setSource('Drushim',this)">Drushim</button>
    <button class="filter-btn" onclick="setSource('Glassdoor',this)">Glassdoor</button>
  </div>
  <div style="display:flex;align-items:center;gap:6px;margin-left:14px">
    <span class="filter-label">Sort</span>
    <button class="filter-btn active" onclick="setSort('relevance',this)">Relevance</button>
    <button class="filter-btn" onclick="setSort('date',this)">Date</button>
  </div>
  <div style="display:flex;align-items:center;gap:6px;margin-left:14px">
    <span class="filter-label">View</span>
    <button class="filter-btn active" onclick="setView('grid',this)">&#9783; Grid</button>
    <button class="filter-btn" onclick="setView('list',this)">&#9776; List</button>
    <button class="filter-btn" onclick="setView('full',this)">&#9783; Full</button>
  </div>
  <input class="search-box" id="search-input" type="text" placeholder="Search title or company..." oninput="renderJobs()">
</div>

<!-- JOBS -->
<div class="content">
  <div class="result-count" id="result-count"></div>
  <div class="jobs-grid" id="jobs-container"><div class="empty"><h2>Loading...</h2></div></div>
</div>

<!-- DIRECT SEARCH LINKS -->
<div class="links-section">
  <h2>&#128269; Direct Search Links</h2>
  <div class="links-grid" id="links-grid"></div>
</div>

<!-- QUICK VIEW MODAL -->
<div class="modal-overlay" id="modal-overlay" onclick="closeModal(event)">
  <div class="modal" id="modal">
    <div class="modal-header">
      <button class="modal-close" onclick="closeModalDirect()">&#215;</button>
      <div class="modal-badges" id="m-badges"></div>
      <div class="modal-title"   id="m-title"></div>
      <div class="modal-company" id="m-company"></div>
      <div class="modal-meta"    id="m-meta"></div>
    </div>
    <div class="modal-body" id="m-body">
      <div class="modal-loading"><div class="spinner"></div> Loading description...</div>
    </div>
    <div class="modal-footer">
      <a class="modal-apply-btn" id="m-apply" href="#" target="_blank" rel="noopener">Open Job Page &#8594;</a>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let allJobs = [];
let timeFilter = 'all', sourceFilter = 'all', sortMode = 'relevance', viewMode = 'grid';
let pollInterval = null;

const ROLES = [
  "Data Analyst","BI Analyst","BI Developer","Junior Data Scientist",
  "AI Analyst","Business Analyst","Analytics Engineer"
];
const SOURCES = [
  {n:"LinkedIn", u: r => `https://www.linkedin.com/jobs/search/?keywords=${enc(r)}&location=Israel&f_E=2&sortBy=DD`},
  {n:"Jobmaster",u: r => `https://www.jobmaster.co.il/jobs/?q=${enc(r)}`},
  {n:"Drushim",  u: r => `https://www.drushim.co.il/jobs/search/${enc(r)}/?experience=0-2&cities=2`},
  {n:"Glassdoor",u: r => `https://www.glassdoor.com/Job/israel-${r.toLowerCase().replace(/ /g,'-')}-jobs-SRCH_IL.0,6_IN119.htm`},
];

function enc(s){return encodeURIComponent(s)}

function srcClass(s){
  const m={linkedin:'src-linkedin',jobmaster:'src-jobmaster',drushim:'src-drushim',alljobs:'src-alljobs',glassdoor:'src-glassdoor'};
  return m[(s||'').toLowerCase()]||'src-unknown';
}

function fmtDate(iso){
  if(!iso||iso==='Recently'||iso==='Last 7 days') return iso||'';
  try{
    const d=new Date(iso), now=new Date();
    const h=(now-d)/3600000;
    if(h<1)  return 'Just now';
    if(h<24) return `Today ${d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})}`;
    if(h<48) return `Yesterday ${d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})}`;
    return d.toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'});
  }catch{return iso}
}

function setTime(v,btn){
  timeFilter=v;
  btn.closest('div').querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  renderJobs();
}
function setSource(v,btn){
  sourceFilter=v;
  btn.closest('div').querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  renderJobs();
}
function setSort(v,btn){
  sortMode=v;
  btn.closest('div').querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  renderJobs();
}
function setView(v,btn){
  viewMode=v;
  btn.closest('div').querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  renderJobs();
}

function relClass(score){
  if(score>=40) return 'rel-high';
  if(score>=25) return 'rel-med';
  return 'rel-low';
}
function relLabel(score){
  if(score>=40) return score+'% match';
  if(score>=25) return score+'% match';
  return score+'% match';
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
    if(q){
      const hay=((j.title||'')+' '+(j.company||'')).toLowerCase();
      if(!hay.includes(q)) return false;
    }
    return true;
  });
}

function h(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function ha(s){return String(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;')}

function renderJobs(){
  const filtered=applyFilters(allJobs);
  document.getElementById('result-count').textContent=`Showing ${filtered.length} of ${allJobs.length} jobs`;
  const container=document.getElementById('jobs-container');

  if(!filtered.length){
    container.className='jobs-grid';
    container.innerHTML='<div class="empty"><h2>No jobs match your filters</h2><p>Try adjusting filters or run a new scan.</p></div>';
    return;
  }

  if(sortMode==='relevance'){
    filtered.sort((a,b)=>(b.relevance_score||0)-(a.relevance_score||0));
  } else {
    filtered.sort((a,b)=>{
      if(!a.scraped_at&&!b.scraped_at) return 0;
      if(!a.scraped_at) return 1; if(!b.scraped_at) return -1;
      return new Date(b.scraped_at)-new Date(a.scraped_at);
    });
  }

  const idx=new Map(allJobs.map((j,i)=>[j.url,i]));

  if(viewMode==='grid'){
    container.className='jobs-grid';
    container.innerHTML=filtered.map(j=>{
      const i=idx.get(j.url)??-1;
      const exp=j.experience_required||'Entry Level';
      const score=j.relevance_score||0;
      return `<div class="job-card">
        <div class="badges">
          <span class="badge ${srcClass(j.source)}">${h(j.source||'?')}</span>
          <span class="badge exp-badge">${h(exp)}</span>
          <span class="badge ${relClass(score)}">${relLabel(score)}</span>
        </div>
        <div class="job-title">${h(j.title||'Untitled')}</div>
        <div class="job-company">${h(j.company||'')}</div>
        <div class="job-meta">
          <span>&#128205; ${h(j.location||'')}</span>
          ${j.scraped_at?`<span>&#128336; ${fmtDate(j.scraped_at)}</span>`:''}
        </div>
        <div class="card-actions">
          <button class="quickview-btn" onclick="openModal(${i})">&#128269; Quick View</button>
          <a class="apply-link" href="${ha(j.url)}" target="_blank" rel="noopener">Apply &#8594;</a>
        </div>
      </div>`;
    }).join('');

  } else if(viewMode==='list'){
    container.className='jobs-list';
    container.innerHTML=filtered.map(j=>{
      const i=idx.get(j.url)??-1;
      const exp=j.experience_required||'Entry Level';
      const score=j.relevance_score||0;
      return `<div class="list-row">
        <div class="list-badges">
          <span class="badge ${srcClass(j.source)}">${h(j.source||'?')}</span>
          <span class="badge ${relClass(score)}">${relLabel(score)}</span>
        </div>
        <div class="list-main">
          <div class="list-title">${h(j.title||'Untitled')}</div>
          <div class="list-company">${h(j.company||'')}</div>
        </div>
        <div class="list-meta">
          <span class="badge exp-badge">${h(exp)}</span>
          ${j.location?`<span>&#128205; ${h(j.location)}</span>`:''}
          ${j.scraped_at?`<span>&#128336; ${fmtDate(j.scraped_at)}</span>`:''}
        </div>
        <div class="list-actions">
          <button class="quickview-btn" onclick="openModal(${i})">&#128269; View</button>
          <a class="apply-link" href="${ha(j.url)}" target="_blank" rel="noopener">Apply &#8594;</a>
        </div>
      </div>`;
    }).join('');

  } else {
    // full view
    container.className='jobs-full';
    container.innerHTML=filtered.map(j=>{
      const i=idx.get(j.url)??-1;
      const exp=j.experience_required||'Entry Level';
      const score=j.relevance_score||0;
      return `<div class="full-card">
        <div class="full-header">
          <div>
            <div class="full-title">${h(j.title||'Untitled')}</div>
            <div class="full-company">${h(j.company||'')}</div>
          </div>
          <div class="full-badges">
            <span class="badge ${srcClass(j.source)}">${h(j.source||'?')}</span>
            <span class="badge exp-badge">${h(exp)}</span>
            <span class="badge ${relClass(score)}">${relLabel(score)}</span>
          </div>
        </div>
        <div class="full-meta">
          ${j.location?`<span>&#128205; ${h(j.location)}</span>`:''}
          ${j.scraped_at?`<span>&#128336; Scraped: ${fmtDate(j.scraped_at)}</span>`:''}
          ${j.posted&&j.posted!=='Recently'?`<span>&#128197; Posted: ${h(j.posted)}</span>`:''}
          <span>&#127760; ${h(j.source||'Unknown source')}</span>
        </div>
        <div class="full-actions">
          <button class="quickview-btn" onclick="openModal(${i})">&#128269; Quick View Description</button>
          <a class="apply-link" href="${ha(j.url)}" target="_blank" rel="noopener">Open Job Page &#8594;</a>
        </div>
      </div>`;
    }).join('');
  }
}

// ── Quick-view modal ──────────────────────────────────────────────────────────
function openModal(idx){
  const j=allJobs[idx];
  if(!j) return;

  const mscore=j.relevance_score||0;
  document.getElementById('m-badges').innerHTML=
    `<span class="badge ${srcClass(j.source)}">${h(j.source)}</span>`+
    `<span class="badge exp-badge">${h(j.experience_required||'Entry Level')}</span>`+
    `<span class="badge ${relClass(mscore)}">${relLabel(mscore)}</span>`;
  document.getElementById('m-title').textContent  = j.title||'';
  document.getElementById('m-company').textContent= j.company||'';
  document.getElementById('m-meta').innerHTML=
    `<span>&#128205; ${h(j.location||'')}</span>`+
    (j.scraped_at?`<span>&#128336; ${fmtDate(j.scraped_at)}</span>`:'')+
    (j.posted&&j.posted!=='Recently'?`<span>&#128197; Posted: ${h(j.posted)}</span>`:'');
  document.getElementById('m-apply').href=j.url||'#';
  document.getElementById('m-body').innerHTML=
    '<div class="modal-loading"><div class="spinner"></div> Fetching description...</div>';

  document.getElementById('modal-overlay').classList.add('open');
  document.body.style.overflow='hidden';

  // Fetch description
  fetch(`/api/preview?url=${encodeURIComponent(j.url)}`)
    .then(r=>r.json())
    .then(data=>{
      const desc=data.description||'No description available.';
      document.getElementById('m-body').innerHTML=
        `<pre>${h(desc)}</pre>`;
    })
    .catch(()=>{
      document.getElementById('m-body').innerHTML=
        '<pre>Could not load description — please use the Apply button above.</pre>';
    });
}

function closeModal(e){
  if(e&&e.target!==document.getElementById('modal-overlay')) return;
  closeModalDirect();
}
function closeModalDirect(){
  document.getElementById('modal-overlay').classList.remove('open');
  document.body.style.overflow='';
}
document.addEventListener('keydown',e=>{if(e.key==='Escape') closeModalDirect();});

// ── Data loading ──────────────────────────────────────────────────────────────
async function loadJobs(){
  try{
    allJobs=await (await fetch('/api/jobs')).json();
    renderJobs();
  }catch(e){
    document.getElementById('jobs-grid').innerHTML=
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
      s.last_run ? 'Last scan: '+fmtDate(s.last_run) : 'No scans yet — click Scan Now';
  }catch(e){}
}

async function startScan(){
  const btn=document.getElementById('scan-btn');
  const lbl=document.getElementById('scan-label');
  btn.disabled=true; btn.classList.add('running');
  lbl.textContent='Scanning...';
  try{
    const r=await (await fetch('/api/scan',{method:'POST'})).json();
    showToast(r.ok?'Scan started — may take a few minutes...':r.message||'Already running');
  }catch{showToast('Could not start scan')}

  pollInterval=setInterval(async()=>{
    const st=await (await fetch('/api/scan/status')).json();
    if(!st.running){
      clearInterval(pollInterval);
      btn.disabled=false; btn.classList.remove('running');
      lbl.innerHTML='&#128269; Scan Now';
      showToast('Scan complete — refreshing...');
      await loadJobs(); await loadStats();
    }
  },3000);
}

function showToast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg; t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),3500);
}

function buildLinks(){
  document.getElementById('links-grid').innerHTML=
    ROLES.flatMap(r=>SOURCES.map(s=>
      `<a class="search-link" href="${s.u(r)}" target="_blank" rel="noopener">${s.n}: ${h(r)}</a>`
    )).join('');
}

// Init
loadJobs(); loadStats(); buildLinks();
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
