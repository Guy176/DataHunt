import uuid
import aiosqlite
from fastapi import APIRouter, BackgroundTasks
from database import get_db
from models import SearchFilters
from scrapers import Yad2Scraper, MadlanScraper

router  = APIRouter()
SCRAPERS = {"yad2": Yad2Scraper, "madlan": MadlanScraper}
_jobs: dict[str, dict] = {}


async def _run(filters: SearchFilters, job_id: str):
    _jobs[job_id] = {"status": "running", "count": 0, "errors": {}}
    total  = 0
    errors = {}

    async with aiosqlite.connect(get_db()) as db:
        for source in filters.sources:
            cls = SCRAPERS.get(source)
            if not cls:
                continue
            try:
                listings = await cls().scrape(filters.model_dump())
                for lst in listings:
                    d    = lst.to_dict()
                    cols = ", ".join(d.keys())
                    ph   = ", ".join("?" * len(d))
                    await db.execute(f"INSERT OR REPLACE INTO listings ({cols}) VALUES ({ph})", list(d.values()))
                    total += 1
                await db.commit()
                print(f"[scrape] {source}: {len(listings)} saved")
            except Exception as e:
                errors[source] = str(e)
                print(f"[scrape] {source} failed: {e}")

    _jobs[job_id] = {"status": "done", "count": total, "errors": errors}


@router.post("/start")
async def start(filters: SearchFilters, bg: BackgroundTasks):
    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {"status": "queued", "count": 0, "errors": {}}
    bg.add_task(_run, filters, job_id)
    return {"job_id": job_id, "status": "queued"}


@router.get("/status/{job_id}")
async def status(job_id: str):
    info = _jobs.get(job_id)
    if not info:
        return {"job_id": job_id, "status": "unknown", "count": 0, "errors": {}}
    return {"job_id": job_id, **info}
