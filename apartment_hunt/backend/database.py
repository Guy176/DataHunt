import aiosqlite, os

DB_PATH = os.getenv("DB_PATH", "apartments.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS listings (
                id           TEXT PRIMARY KEY,
                source       TEXT NOT NULL DEFAULT '',
                title        TEXT,
                price        INTEGER,
                rooms        REAL,
                floor        INTEGER,
                size_sqm     REAL,
                city         TEXT,
                neighborhood TEXT,
                street       TEXT,
                address      TEXT,
                description  TEXT,
                image_url    TEXT,
                url          TEXT,
                contact_name TEXT,
                phone        TEXT,
                is_favorite  INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT,
                scraped_at   TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_city      ON listings(city);
            CREATE INDEX IF NOT EXISTS idx_source    ON listings(source);
            CREATE INDEX IF NOT EXISTS idx_price     ON listings(price);
            CREATE INDEX IF NOT EXISTS idx_scraped   ON listings(scraped_at DESC);
        """)
        await db.commit()

def get_db() -> str:
    return DB_PATH
