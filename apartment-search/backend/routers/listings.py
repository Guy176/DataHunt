import aiosqlite
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import uuid

from database import get_db_path
from models import ListingOut, ManualListing

router = APIRouter()


async def row_to_dict(row: aiosqlite.Row) -> dict:
    return dict(zip(row.keys(), row))


@router.get("/", response_model=list[ListingOut])
async def get_listings(
    min_price: Optional[int] = Query(None),
    max_price: Optional[int] = Query(None),
    min_rooms: Optional[float] = Query(None),
    max_rooms: Optional[float] = Query(None),
    min_floor: Optional[int] = Query(None),
    max_floor: Optional[int] = Query(None),
    city: Optional[str] = Query(None),
    neighborhood: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    favorites_only: bool = Query(False),
    sort_by: str = Query("scraped_at"),
    sort_order: str = Query("desc"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    conditions = []
    params: list = []

    if min_price is not None:
        conditions.append("price >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("price <= ?")
        params.append(max_price)
    if min_rooms is not None:
        conditions.append("rooms >= ?")
        params.append(min_rooms)
    if max_rooms is not None:
        conditions.append("rooms <= ?")
        params.append(max_rooms)
    if min_floor is not None:
        conditions.append("floor >= ?")
        params.append(min_floor)
    if max_floor is not None:
        conditions.append("floor <= ?")
        params.append(max_floor)
    if city:
        conditions.append("city LIKE ?")
        params.append(f"%{city}%")
    if neighborhood:
        conditions.append("neighborhood LIKE ?")
        params.append(f"%{neighborhood}%")
    if source:
        conditions.append("source = ?")
        params.append(source)
    if favorites_only:
        conditions.append("is_favorite = 1")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    allowed_sort = {"scraped_at", "price", "rooms", "floor", "size_sqm", "created_at"}
    sort_col = sort_by if sort_by in allowed_sort else "scraped_at"
    order = "DESC" if sort_order.lower() == "desc" else "ASC"

    sql = f"SELECT * FROM listings {where} ORDER BY {sort_col} {order} LIMIT ? OFFSET ?"
    params += [limit, offset]

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

    return [dict(row) for row in rows]


@router.get("/count")
async def count_listings(
    source: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
):
    conditions = []
    params: list = []
    if source:
        conditions.append("source = ?")
        params.append(source)
    if city:
        conditions.append("city LIKE ?")
        params.append(f"%{city}%")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"SELECT COUNT(*) FROM listings {where}"

    async with aiosqlite.connect(get_db_path()) as db:
        async with db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
    return {"count": row[0] if row else 0}


@router.get("/{listing_id}", response_model=ListingOut)
async def get_listing(listing_id: str):
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM listings WHERE id = ?", [listing_id]) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Listing not found")
    return dict(row)


@router.patch("/{listing_id}/favorite")
async def toggle_favorite(listing_id: str):
    async with aiosqlite.connect(get_db_path()) as db:
        async with db.execute("SELECT is_favorite FROM listings WHERE id = ?", [listing_id]) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        new_val = 0 if row[0] else 1
        await db.execute("UPDATE listings SET is_favorite = ? WHERE id = ?", [new_val, listing_id])
        await db.commit()
    return {"is_favorite": bool(new_val)}


@router.post("/manual", response_model=ListingOut, status_code=201)
async def add_manual_listing(body: ManualListing):
    """Add a listing manually (e.g. found on Facebook Marketplace)."""
    listing_id = f"manual_{uuid.uuid4().hex[:12]}"
    address = body.address or ", ".join(
        p for p in [body.street or "", body.neighborhood or "", body.city or ""] if p
    )
    row = {
        "id": listing_id,
        "source": "manual",
        "title": body.title,
        "price": body.price,
        "rooms": body.rooms,
        "floor": body.floor,
        "size_sqm": body.size_sqm,
        "city": body.city,
        "neighborhood": body.neighborhood,
        "street": body.street,
        "address": address,
        "description": body.description,
        "image_url": body.image_url,
        "url": body.url,
        "contact_name": body.contact_name,
        "phone": body.phone,
        "is_favorite": 0,
        "created_at": None,
        "scraped_at": None,
    }
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" * len(row))
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute(
            f"INSERT OR REPLACE INTO listings ({cols}) VALUES ({placeholders})",
            list(row.values()),
        )
        await db.commit()
    return {**row, "is_favorite": False}


@router.delete("/{listing_id}", status_code=204)
async def delete_listing(listing_id: str):
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("DELETE FROM listings WHERE id = ?", [listing_id])
        await db.commit()
