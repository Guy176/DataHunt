import uuid
import aiosqlite
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from database import get_db
from models import ManualListing, ListingOut

router = APIRouter()


@router.get("/", response_model=list[ListingOut])
async def get_listings(
    min_price:     Optional[int]   = Query(None),
    max_price:     Optional[int]   = Query(None),
    min_rooms:     Optional[float] = Query(None),
    max_rooms:     Optional[float] = Query(None),
    min_floor:     Optional[int]   = Query(None),
    max_floor:     Optional[int]   = Query(None),
    city:          Optional[str]   = Query(None),
    neighborhood:  Optional[str]   = Query(None),
    source:        Optional[str]   = Query(None),
    favorites_only: bool           = Query(False),
    sort_by:       str             = Query("scraped_at"),
    sort_order:    str             = Query("desc"),
    limit:         int             = Query(200, ge=1, le=500),
    offset:        int             = Query(0, ge=0),
):
    conds, vals = [], []
    if min_price     is not None: conds.append("price >= ?");            vals.append(min_price)
    if max_price     is not None: conds.append("price <= ?");            vals.append(max_price)
    if min_rooms     is not None: conds.append("rooms >= ?");            vals.append(min_rooms)
    if max_rooms     is not None: conds.append("rooms <= ?");            vals.append(max_rooms)
    if min_floor     is not None: conds.append("floor >= ?");            vals.append(min_floor)
    if max_floor     is not None: conds.append("floor <= ?");            vals.append(max_floor)
    if city:                      conds.append("city LIKE ?");           vals.append(f"%{city}%")
    if neighborhood:              conds.append("neighborhood LIKE ?");   vals.append(f"%{neighborhood}%")
    if source:                    conds.append("source = ?");            vals.append(source)
    if favorites_only:            conds.append("is_favorite = 1")

    where    = ("WHERE " + " AND ".join(conds)) if conds else ""
    safe_col = sort_by if sort_by in {"scraped_at","price","rooms","floor","size_sqm","created_at"} else "scraped_at"
    order    = "DESC" if sort_order.lower() == "desc" else "ASC"
    sql      = f"SELECT * FROM listings {where} ORDER BY {safe_col} {order} LIMIT ? OFFSET ?"
    vals    += [limit, offset]

    async with aiosqlite.connect(get_db()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, vals) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.patch("/{listing_id}/favorite")
async def toggle_favorite(listing_id: str):
    async with aiosqlite.connect(get_db()) as db:
        async with db.execute("SELECT is_favorite FROM listings WHERE id = ?", [listing_id]) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        new = 0 if row[0] else 1
        await db.execute("UPDATE listings SET is_favorite = ? WHERE id = ?", [new, listing_id])
        await db.commit()
    return {"is_favorite": bool(new)}


@router.post("/manual", response_model=ListingOut, status_code=201)
async def add_manual(body: ManualListing):
    lid     = f"manual_{uuid.uuid4().hex[:12]}"
    address = body.address or ", ".join(x for x in [body.street or "", body.neighborhood or "", body.city or ""] if x)
    row = {
        "id": lid, "source": "manual", "title": body.title,
        "price": body.price, "rooms": body.rooms, "floor": body.floor,
        "size_sqm": body.size_sqm, "city": body.city, "neighborhood": body.neighborhood,
        "street": body.street, "address": address, "description": body.description,
        "image_url": body.image_url, "url": body.url,
        "contact_name": body.contact_name, "phone": body.phone,
        "is_favorite": 0, "created_at": None, "scraped_at": None,
    }
    cols = ", ".join(row.keys())
    ph   = ", ".join("?" * len(row))
    async with aiosqlite.connect(get_db()) as db:
        await db.execute(f"INSERT OR REPLACE INTO listings ({cols}) VALUES ({ph})", list(row.values()))
        await db.commit()
    return {**row, "is_favorite": False}


@router.delete("/{listing_id}", status_code=204)
async def delete_listing(listing_id: str):
    async with aiosqlite.connect(get_db()) as db:
        await db.execute("DELETE FROM listings WHERE id = ?", [listing_id])
        await db.commit()
