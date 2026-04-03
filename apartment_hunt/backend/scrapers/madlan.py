"""
Madlan scraper — tries multiple endpoints:
1. homes/getData REST API (older but may still work)
2. __NEXT_DATA__ HTML extraction (Next.js 12 style)
3. Next.js 13 RSC chunk extraction
"""
import asyncio, json, re, urllib.parse
from typing import Optional
from curl_cffi.requests import AsyncSession
from .base import BaseScraper, Listing

BASE = "https://www.madlan.co.il"

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

# Hebrew city names for the REST API (uses Hebrew directly)
CITY_HE = {v: k for k, v in SLUGS.items()}  # slug → hebrew


class MadlanScraper(BaseScraper):
    async def scrape(self, filters: dict) -> list[Listing]:
        city_he = (filters.get("city") or "").strip() or "ישראל"
        slug    = SLUGS.get(city_he) or SLUGS.get(city_he.lower()) or "israel"
        results: list[Listing] = []

        async with AsyncSession(impersonate="chrome124") as s:
            # ── Attempt 1: homes/getData REST API ──────────────────────────
            items = await self._try_rest_api(s, city_he, filters)
            if items:
                print(f"[Madlan] REST API returned {len(items)} raw items")
            else:
                # ── Attempt 2: HTML page __NEXT_DATA__ / RSC ──────────────
                items = await self._try_html(s, slug, filters)

            for raw in items:
                lst = self._parse(raw)
                if lst:
                    results.append(lst)

        print(f"[Madlan] done — {len(results)} listings")
        return results

    # ── REST API ──────────────────────────────────────────────────────────
    async def _try_rest_api(self, s, city_he: str, filters: dict) -> list[dict]:
        query = {
            "sortBy": "auto",
            "zoom": 12,
            "source": "all",
            "areaId": city_he,
            "filter": {
                "dealTypes": ["FOR_RENT"],
                "addBulletinFromPrivate": True,
                "addBulletinFromAgent": True,
                "addProjects": False,
                "conditions": [],
            },
        }
        if filters.get("min_price") or filters.get("max_price"):
            query["filter"]["price"] = {
                "min": filters.get("min_price") or 0,
                "max": filters.get("max_price") or 99999,
            }
        if filters.get("min_rooms"):
            query["filter"]["rooms"] = {"min": filters["min_rooms"]}

        url = f"{BASE}/homes/getData/?json={urllib.parse.quote(json.dumps(query, ensure_ascii=False))}"
        try:
            r = await s.get(url)
            print(f"[Madlan] homes/getData → {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"[Madlan] REST response type: {type(data).__name__}, keys: {list(data.keys())[:8] if isinstance(data, dict) else 'list'}")
                items = self._deep(data)
                if items:
                    return items
        except Exception as e:
            print(f"[Madlan] REST API error: {e}")
        return []

    # ── HTML scraping ─────────────────────────────────────────────────────
    async def _try_html(self, s, slug: str, filters: dict) -> list[dict]:
        url    = f"{BASE}/for-rent/{slug}"
        params = self._params(filters)
        try:
            r = await s.get(url, params=params)
            print(f"[Madlan] HTML page → {r.status_code}")
            if r.status_code != 200:
                return []
            return self._extract_html(r.text)
        except Exception as e:
            print(f"[Madlan] HTML error: {e}")
            return []

    def _params(self, f: dict) -> dict:
        p: dict = {}
        if f.get("min_price"): p["price_min"] = f["min_price"]
        if f.get("max_price"): p["price_max"] = f["max_price"]
        if f.get("min_rooms"): p["rooms_min"] = f["min_rooms"]
        if f.get("max_rooms"): p["rooms_max"] = f["max_rooms"]
        return p

    def _extract_html(self, html: str) -> list[dict]:
        # Classic __NEXT_DATA__
        m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                data  = json.loads(m.group(1))
                props = data.get("props", {}).get("pageProps", {})
                print(f"[Madlan] __NEXT_DATA__ pageProps keys: {list(props.keys())[:10]}")

                # dehydratedState (React Query)
                queries = props.get("dehydratedState", {}).get("queries", [])
                for q in queries:
                    items = self._deep(q.get("state", {}).get("data", {}))
                    if items:
                        print(f"[Madlan] dehydratedState → {len(items)} items")
                        return items

                items = self._deep(props)
                if items:
                    return items
            except Exception as e:
                print(f"[Madlan] __NEXT_DATA__ error: {e}")

        # Next.js 13 RSC chunks
        chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html)
        for chunk in chunks:
            try:
                decoded = chunk.encode("utf-8").decode("unicode_escape")
                if '"price"' in decoded or '"rentPrice"' in decoded:
                    items = self._extract_rsc(decoded)
                    if items:
                        print(f"[Madlan] RSC chunk → {len(items)} items")
                        return items
            except Exception:
                pass

        print(f"[Madlan] no data in HTML (length={len(html)}, scripts={html.count('<script')})")
        return []

    def _extract_rsc(self, text: str) -> list[dict]:
        for line in text.splitlines():
            try:
                colon = line.index(":")
                payload = json.loads(line[colon + 1:])
                found   = self._deep(payload)
                if found:
                    return found
            except Exception:
                pass
        return []

    def _deep(self, obj, depth=0) -> list[dict]:
        if depth > 7:
            return []
        if isinstance(obj, list) and len(obj) > 1 and isinstance(obj[0], dict):
            if any(k in obj[0] for k in ("price", "rentPrice", "id", "listingId")):
                return obj
        if isinstance(obj, dict):
            for v in obj.values():
                r = self._deep(v, depth + 1)
                if r:
                    return r
        return []

    def _parse(self, item: dict) -> Optional[Listing]:
        try:
            item_id = str(item.get("id") or item.get("_id") or item.get("listingId") or item.get("bulletinId") or "")
            if not item_id:
                return None

            price = None
            try:
                raw   = str(item.get("price") or item.get("rentPrice") or "")
                price = int(raw.replace(",", "").replace("₪", "").strip())
            except (ValueError, TypeError):
                pass

            def _f(v):
                try: return float(v) if v is not None else None
                except: return None
            def _i(v):
                try: return int(v) if v is not None else None
                except: return None

            rooms    = _f(item.get("rooms") or item.get("roomsCount") or item.get("numberOfRooms"))
            floor    = _i(item.get("floor") or item.get("floorNumber"))
            size_sqm = _f(item.get("size") or item.get("squareMeters") or item.get("area") or item.get("totalArea"))

            loc = item.get("location") or item.get("address") or {}
            if isinstance(loc, str):
                address = loc; city = nbhd = street = ""
            else:
                city    = loc.get("city", "") or item.get("city", "") or item.get("cityName", "")
                nbhd    = loc.get("neighborhood", "") or item.get("neighborhood", "") or item.get("neighborhoodName", "")
                street  = loc.get("street", "") or item.get("street", "") or item.get("streetName", "")
                address = ", ".join(x for x in [street, nbhd, city] if x)

            images    = item.get("images") or item.get("photos") or []
            image_url = None
            if images:
                i = images[0]
                image_url = (i.get("url") or i.get("src")) if isinstance(i, dict) else (i if isinstance(i, str) else None)

            listing_url = item.get("url") or item.get("link") or f"{BASE}/listing/{item_id}"
            if listing_url and not listing_url.startswith("http"):
                listing_url = BASE + listing_url

            return Listing(
                id=f"madlan_{item_id}", source="madlan",
                title=item.get("title") or address or "Madlan Listing",
                price=price, rooms=rooms, floor=floor, size_sqm=size_sqm,
                city=city, neighborhood=nbhd, street=street, address=address,
                description=item.get("description") or item.get("comments") or "",
                image_url=image_url, url=listing_url,
                contact_name=item.get("contactName") or item.get("contact_name"),
            )
        except Exception as e:
            print(f"[Madlan] parse error: {e}")
            return None
