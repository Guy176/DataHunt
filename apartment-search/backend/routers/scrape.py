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

_scrape_status: dict[str, str] = {}


async def _run_scrape(filters: SearchFilters, job_id: str) -> None:
    _scrape_status[job_id] = "running"
    total = 0

    async with aiosqlite.connect(get_db_path()) as db:
        for source in filters.sources:
            cls = SCRAPERS.get(source)
            if not cls:
                continue
            try:
                listings = await cls().scrape(filters.dict())
                for listing in listings:
                    d = listing.to_dict()
                    cols = ", ".join(d.keys())
                    placeholders = ", ".join("?" * len(d))
                    await db.execute(
                        f"INSERT OR REPLACE INTO listings ({cols}) VALUES ({placeholders})",
                        list(d.values()),
                    )
                    total += 1
                await db.commit()
            except Exception as e:
                print(f"[Scrape] {source} failed: {e}")

    _scrape_status[job_id] = f"done:{total}"


@router.post("/start")
async def start_scrape(filters: SearchFilters, background_tasks: BackgroundTasks):
    import uuid
    job_id = uuid.uuid4().hex[:8]
    _scrape_status[job_id] = "queued"
    background_tasks.add_task(_run_scrape, filters, job_id)
    return {"job_id": job_id, "status": "queued"}


@router.get("/status/{job_id}")
async def scrape_status(job_id: str):
    status = _scrape_status.get(job_id, "unknown")
    count = None
    if status.startswith("done:"):
        count = int(status.split(":")[1])
        status = "done"
    return {"job_id": job_id, "status": status, "count": count}


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
