"""
Madlan scraper — fetches their Next.js page and extracts __NEXT_DATA__.
Uses curl_cffi to impersonate Chrome (bypasses bot detection).
"""
import asyncio, json, re
from typing import Optional
from curl_cffi.requests import AsyncSession
from .base import BaseScraper, Listing

BASE  = "https://www.madlan.co.il"
WARM  = "https://www.madlan.co.il"

SLUGS = {
    "תל אביב": "tel-aviv-yafo",   "ירושלים": "jerusalem",
    "חיפה":    "haifa",           "ראשון לציון": "rishon-leziyyon",
    "פתח תקווה": "petah-tikva",   "אשדוד": "ashdod",
    "נתניה":   "netanya",         "באר שבע": "beer-sheva",
    "בני ברק": "bnei-brak",       "חולון": "holon",
    "רמת גן":  "ramat-gan",       "אשקלון": "ashkelon",
    "רחובות":  "rehovot",         "בת ים": "bat-yam",
    "כפר סבא": "kfar-sava",       "הרצליה": "herzliya",
    "חדרה":    "hadera",          "מודיעין": "modiin",
    "לוד":     "lod",             "אילת": "eilat",
}


class MadlanScraper(BaseScraper):
    async def scrape(self, filters: dict) -> list[Listing]:
        city = (filters.get("city") or "").strip()
        slug = SLUGS.get(city) or SLUGS.get(city.lower()) or "israel"
        url  = f"{BASE}/for-rent/{slug}"
        params = self._params(filters)
        results: list[Listing] = []

        async with AsyncSession(impersonate="chrome124") as s:
            try:
                r = await s.get(WARM)
                print(f"[Madlan] warm-up {r.status_code}")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"[Madlan] warm-up error: {e}")

            for page in range(1, 4):
                try:
                    r = await s.get(url, params={**params, "page": page})
                    print(f"[Madlan] page {page} → {r.status_code}")
                    if r.status_code != 200:
                        print(f"[Madlan] body: {r.text[:400]}")
                        break
                    items = self._extract(r.text)
                    if not items:
                        print(f"[Madlan] no listings in page {page}")
                        break
                    for raw in items:
                        lst = self._parse(raw)
                        if lst:
                            results.append(lst)
                    await asyncio.sleep(1.0)
                except Exception as e:
                    print(f"[Madlan] error: {e}")
                    break

        print(f"[Madlan] done — {len(results)} listings")
        return results

    def _params(self, f: dict) -> dict:
        p: dict = {}
        if f.get("min_price"): p["price_min"] = f["min_price"]
        if f.get("max_price"): p["price_max"] = f["max_price"]
        if f.get("min_rooms"): p["rooms_min"] = f["min_rooms"]
        if f.get("max_rooms"): p["rooms_max"] = f["max_rooms"]
        return p

    def _extract(self, html: str) -> list[dict]:
        m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        if not m:
            return []
        try:
            data  = json.loads(m.group(1))
            props = data.get("props", {}).get("pageProps", {})
        except json.JSONDecodeError:
            return []
        for key in ("listings", "items", "feed", "results", "data"):
            val = props.get(key)
            if isinstance(val, list) and val:
                return val
            if isinstance(val, dict):
                for sub in ("listings", "items", "feed", "results"):
                    v = val.get(sub)
                    if isinstance(v, list) and v:
                        return v
        return self._deep(props)

    def _deep(self, obj, depth=0) -> list[dict]:
        if depth > 5:
            return []
        if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "price" in obj[0]:
            return obj
        if isinstance(obj, dict):
            for v in obj.values():
                r = self._deep(v, depth + 1)
                if r:
                    return r
        return []

    def _parse(self, item: dict) -> Optional[Listing]:
        try:
            item_id = str(item.get("id") or item.get("_id") or item.get("listingId", ""))
            if not item_id:
                return None

            price = None
            try:
                raw = str(item.get("price") or item.get("rentPrice") or "")
                price = int(raw.replace(",", "").replace("₪", "").strip())
            except (ValueError, TypeError):
                pass

            def _float(v):
                try: return float(v) if v is not None else None
                except: return None

            def _int(v):
                try: return int(v) if v is not None else None
                except: return None

            rooms    = _float(item.get("rooms") or item.get("roomsCount"))
            floor    = _int(item.get("floor")  or item.get("floorNumber"))
            size_sqm = _float(item.get("size") or item.get("squareMeters") or item.get("area"))

            loc = item.get("location") or item.get("address") or {}
            if isinstance(loc, str):
                address = loc; city = nbhd = street = ""
            else:
                city    = loc.get("city", "") or item.get("city", "")
                nbhd    = loc.get("neighborhood", "") or item.get("neighborhood", "")
                street  = loc.get("street", "") or item.get("street", "")
                address = ", ".join(x for x in [street, nbhd, city] if x)

            images    = item.get("images") or item.get("photos") or []
            image_url = None
            if images:
                i = images[0]
                image_url = (i.get("url") or i.get("src")) if isinstance(i, dict) else (i if isinstance(i, str) else None)

            listing_url = item.get("url") or item.get("link") or f"{BASE}/listing/{item_id}"
            if not listing_url.startswith("http"):
                listing_url = BASE + listing_url

            return Listing(
                id=f"madlan_{item_id}", source="madlan",
                title=item.get("title") or address or "Madlan Listing",
                price=price, rooms=rooms, floor=floor, size_sqm=size_sqm,
                city=city, neighborhood=nbhd, street=street, address=address,
                description=item.get("description") or "",
                image_url=image_url, url=listing_url,
                contact_name=item.get("contactName"),
            )
        except Exception as e:
            print(f"[Madlan] parse error: {e}")
            return None
