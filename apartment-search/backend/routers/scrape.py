import aiosqlite
from fastapi import APIRouter, BackgroundTasks
from models import SearchFilters
from scrapers import Yad2Scraper, MadlanScraper
from database import get_db_path

router = APIRouter()

SCRAPERS = {
    "yad2": Yad2Scraper,
    "madlan": MadlanScraper,
}

_scrape_status: dict[str, dict] = {}


async def _run_scrape(filters: SearchFilters, job_id: str) -> None:
    _scrape_status[job_id] = {"status": "running", "total": 0, "errors": {}}
    total = 0
    errors: dict[str, str] = {}

    async with aiosqlite.connect(get_db_path()) as db:
        for source in filters.sources:
            cls = SCRAPERS.get(source)
            if not cls:
                continue
            try:
                listings = await cls().scrape(filters.dict())
                count = 0
                for listing in listings:
                    d = listing.to_dict()
                    cols = ", ".join(d.keys())
                    placeholders = ", ".join("?" * len(d))
                    await db.execute(
                        f"INSERT OR REPLACE INTO listings ({cols}) VALUES ({placeholders})",
                        list(d.values()),
                    )
                    count += 1
                    total += 1
                await db.commit()
                print(f"[Scrape] {source}: {count} listings saved")
            except Exception as e:
                err_msg = str(e)
                errors[source] = err_msg
                print(f"[Scrape] {source} failed: {err_msg}")

    _scrape_status[job_id] = {"status": "done", "total": total, "errors": errors}


@router.post("/start")
async def start_scrape(filters: SearchFilters, background_tasks: BackgroundTasks):
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _scrape_status[job_id] = {"status": "queued", "total": 0, "errors": {}}
    background_tasks.add_task(_run_scrape, filters, job_id)
    return {"job_id": job_id, "status": "queued"}


@router.get("/status/{job_id}")
async def scrape_status(job_id: str):
    info = _scrape_status.get(job_id)
    if info is None:
        return {"job_id": job_id, "status": "unknown", "count": None, "errors": {}}
    return {
        "job_id": job_id,
        "status": info["status"],
        "count": info.get("total"),
        "errors": info.get("errors", {}),
    }


@router.get("/sources")
async def list_sources():
    return {
        "sources": [
            {"id": "yad2", "name": "Yad2", "url": "https://www.yad2.co.il"},
            {"id": "madlan", "name": "Madlan", "url": "https://www.madlan.co.il"},
            {
                "id": "manual",
                "name": "Manual (Facebook / Other)",
                "url": None,
                "note": "Add listings manually via POST /api/listings/manual",
            },
        ]
    }
