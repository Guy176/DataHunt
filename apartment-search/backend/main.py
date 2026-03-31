from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import listings, scrape


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Israel Apartment Search API",
    description="Search and scrape apartment rentals from Yad2, Madlan, and more.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(listings.router, prefix="/api/listings", tags=["Listings"])
app.include_router(scrape.router, prefix="/api/scrape", tags=["Scraping"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
