"""
Madlan scraper — extracts listings from __NEXT_DATA__ on the search page,
with fallback to the /_next/data/ JSON endpoint.
"""
import asyncio, json, re
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


class MadlanScraper(BaseScraper):
    async def scrape(self, filters: dict) -> list[Listing]:
        city = (filters.get("city") or "").strip()
        slug = SLUGS.get(city) or SLUGS.get(city.lower()) or "israel"
        url  = f"{BASE}/for-rent/{slug}"
        qp   = self._params(filters)
        results: list[Listing] = []

        async with AsyncSession(impersonate="chrome124") as s:
            # Page 1: get HTML, extract __NEXT_DATA__, also grab buildId for JSON API
            try:
                r = await s.get(url, params=qp)
                print(f"[Madlan] page 1 → {r.status_code}")
                if r.status_code != 200:
                    print(f"[Madlan] body: {r.text[:300]}")
                    return []

                items, build_id = self._extract(r.text)

                if not items and build_id:
                    # Fallback: hit the Next.js JSON data endpoint directly
                    json_url = f"{BASE}/_next/data/{build_id}/for-rent/{slug}.json"
                    print(f"[Madlan] trying Next.js data endpoint: {json_url}")
                    jr = await s.get(json_url, params=qp)
                    print(f"[Madlan] _next/data → {jr.status_code}")
                    if jr.status_code == 200:
                        try:
                            jdata = jr.json()
                            items, _ = self._extract_from_props(
                                jdata.get("pageProps", jdata)
                            )
                        except Exception as e:
                            print(f"[Madlan] _next/data parse error: {e}")

                for raw in items:
                    lst = self._parse(raw)
                    if lst:
                        results.append(lst)

                await asyncio.sleep(1.0)

            except Exception as e:
                print(f"[Madlan] error: {e}")

        print(f"[Madlan] done — {len(results)} listings")
        return results

    def _params(self, f: dict) -> dict:
        p: dict = {}
        if f.get("min_price"): p["price_min"] = f["min_price"]
        if f.get("max_price"): p["price_max"] = f["max_price"]
        if f.get("min_rooms"): p["rooms_min"] = f["min_rooms"]
        if f.get("max_rooms"): p["rooms_max"] = f["max_rooms"]
        return p

    def _extract(self, html: str):
        """Returns (items, build_id)."""
        m = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if not m:
            print("[Madlan] __NEXT_DATA__ not found")
            return [], None

        try:
            data = json.loads(m.group(1))
        except Exception as e:
            print(f"[Madlan] JSON parse error: {e}")
            return [], None

        build_id = data.get("buildId")
        props    = data.get("props", {}).get("pageProps", {})
        items, _ = self._extract_from_props(props)
        return items, build_id

    def _extract_from_props(self, props: dict):
        print(f"[Madlan] pageProps keys: {list(props.keys())[:15]}")

        # Log sizes of dict/list values to spot where data lives
        for k, v in props.items():
            if isinstance(v, list) and v:
                print(f"[Madlan]   {k}: list[{len(v)}]")
            elif isinstance(v, dict) and v:
                print(f"[Madlan]   {k}: dict keys={list(v.keys())[:6]}")

        # Known paths to try
        candidates = [
            ["listings"],
            ["items"],
            ["feed"],
            ["results"],
            ["data", "listings"],
            ["data", "items"],
            ["data", "feed"],
            ["initialProps", "listings"],
            ["searchResults", "listings"],
            ["searchResults", "items"],
            ["listingsList"],
            ["listingsResult", "listings"],
        ]
        for path in candidates:
            obj = props
            for key in path:
                obj = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                print(f"[Madlan] found {len(obj)} items at {' > '.join(path)}")
                return obj, None

        # Deep search
        found = self._deep(props)
        if found:
            print(f"[Madlan] deep-search found {len(found)} items")
        else:
            print("[Madlan] no listings found in pageProps")
        return found, None

    def _deep(self, obj, depth=0) -> list[dict]:
        if depth > 6:
            return []
        if isinstance(obj, list) and len(obj) > 1 and isinstance(obj[0], dict):
            if any(k in obj[0] for k in ("price", "id", "listingId", "rentPrice")):
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

            def _f(v):
                try: return float(v) if v is not None else None
                except: return None
            def _i(v):
                try: return int(v) if v is not None else None
                except: return None

            rooms    = _f(item.get("rooms") or item.get("roomsCount"))
            floor    = _i(item.get("floor")  or item.get("floorNumber"))
            size_sqm = _f(item.get("size") or item.get("squareMeters") or item.get("area"))

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
            if listing_url and not listing_url.startswith("http"):
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
