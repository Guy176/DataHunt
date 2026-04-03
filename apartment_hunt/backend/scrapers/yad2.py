"""
Yad2 scraper — scrapes the HTML search page and extracts __NEXT_DATA__,
avoiding the blocked internal API at gw.yad2.co.il.
"""
import asyncio, json, re
from typing import Optional
from curl_cffi.requests import AsyncSession
from .base import BaseScraper, Listing

CITIES = {
    "תל אביב": "5000", "ירושלים": "3000", "חיפה": "4000",
    "ראשון לציון": "8300", "פתח תקווה": "7900", "אשדוד": "70",
    "נתניה": "7400", "באר שבע": "9000", "בני ברק": "6300",
    "חולון": "6400", "רמת גן": "8600", "אשקלון": "40",
    "רחובות": "8400", "בת ים": "6200", "כפר סבא": "9200",
    "הרצליה": "6600", "חדרה": "6500", "מודיעין": "10200",
    "לוד": "7000", "אילת": "100", "גבעתיים": "6100",
    "בית שמש": "1200", "רמלה": "8500", "יבנה": "6900",
    "עכו": "9800", "נהריה": "7300", "טבריה": "9500",
}

BASE = "https://www.yad2.co.il"


class Yad2Scraper(BaseScraper):
    async def scrape(self, filters: dict) -> list[Listing]:
        params = self._params(filters)
        results: list[Listing] = []

        async with AsyncSession(impersonate="chrome124") as s:
            for page in range(1, 4):
                params["page"] = page
                try:
                    url = f"{BASE}/realestate/rent"
                    r = await s.get(url, params=params)
                    print(f"[Yad2] page {page} → {r.status_code}")

                    if r.status_code != 200:
                        print(f"[Yad2] body preview: {r.text[:300]}")
                        break

                    items = self._extract(r.text)
                    if not items:
                        break

                    if items:
                        print(f"[Yad2] first item keys: {list(items[0].keys())[:10]}")
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        lst = self._parse(item)
                        if lst:
                            results.append(lst)

                    await asyncio.sleep(1.0)

                except Exception as e:
                    print(f"[Yad2] error page {page}: {e}")
                    break

        print(f"[Yad2] done — {len(results)} listings")
        return results

    def _params(self, f: dict) -> dict:
        p: dict = {}
        if f.get("min_price"): p["minPrice"] = f["min_price"]
        if f.get("max_price"): p["maxPrice"] = f["max_price"]
        if f.get("min_rooms"): p["minRooms"] = f["min_rooms"]
        if f.get("max_rooms"): p["maxRooms"] = f["max_rooms"]
        if f.get("min_floor"): p["minFloor"] = f["min_floor"]
        if f.get("max_floor"): p["maxFloor"] = f["max_floor"]
        city = (f.get("city") or "").strip()
        if city:
            code = CITIES.get(city) or CITIES.get(city.lower())
            if code:
                p["city"] = code
        return p

    def _extract(self, html: str) -> list[dict]:
        m = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if not m:
            print("[Yad2] __NEXT_DATA__ not found in HTML")
            return []

        try:
            data = json.loads(m.group(1))
        except Exception as e:
            print(f"[Yad2] failed to parse __NEXT_DATA__: {e}")
            return []

        props = data.get("props", {}).get("pageProps", {})
        print(f"[Yad2] pageProps keys: {list(props.keys())[:12]}")

        # Try every known path Yad2 has used
        candidates = [
            ["feed"],                             # <-- direct list under "feed"
            ["data", "feed", "feed_items"],
            ["initialData", "feed", "feed_items"],
            ["serverData", "feed", "feed_items"],
            ["feedData", "feed_items"],
            ["feed", "feed_items"],
            ["listings"],
            ["items"],
        ]
        for path in candidates:
            obj = props
            for key in path:
                obj = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(obj, list) and obj:
                print(f"[Yad2] found {len(obj)} items at {' > '.join(path)}")
                return obj

        # Last resort: deep search for list of ad-type dicts
        found = self._deep(props)
        if found:
            print(f"[Yad2] deep-search found {len(found)} items")
        else:
            print(f"[Yad2] no items found; top-level pageProps keys: {list(props.keys())}")
        return found

    def _deep(self, obj, depth=0) -> list[dict]:
        if depth > 6:
            return []
        if isinstance(obj, list) and len(obj) > 2 and isinstance(obj[0], dict):
            if "price" in obj[0] or "id" in obj[0]:
                return obj
        if isinstance(obj, dict):
            for v in obj.values():
                r = self._deep(v, depth + 1)
                if r:
                    return r
        return []

    def _parse(self, item: dict) -> Optional[Listing]:
        try:
            addr  = item.get("address", {})
            city  = addr.get("city",         {}).get("text", "") if isinstance(addr, dict) else ""
            nbhd  = addr.get("neighborhood", {}).get("text", "") if isinstance(addr, dict) else ""
            st    = addr.get("street",       {}).get("text", "") if isinstance(addr, dict) else ""
            full  = ", ".join(x for x in [st, nbhd, city] if x)

            price = None
            raw   = str(item.get("price", "")).replace(",", "").replace("₪", "").strip()
            if raw.isdigit():
                price = int(raw)

            rooms = None
            rv    = item.get("rooms")
            if rv is not None:
                try: rooms = float(str(rv).replace("חדרים","").replace("חדר","").strip())
                except ValueError: pass

            sqm  = None
            sv   = item.get("square_meters")
            if sv:
                try: sqm = float(str(sv).replace('מ"ר', "").strip())
                except ValueError: pass

            floor = None
            fv    = item.get("floor")
            if fv is not None:
                try: floor = int(fv)
                except (ValueError, TypeError): pass

            images    = item.get("images", [])
            image_url = images[0].get("src") if images and isinstance(images[0], dict) else None
            item_id   = str(item.get("id", ""))

            return Listing(
                id=f"yad2_{item_id}", source="yad2",
                title=item.get("title") or full,
                price=price, rooms=rooms, floor=floor, size_sqm=sqm,
                city=city, neighborhood=nbhd, street=st, address=full,
                description=item.get("info_text", ""),
                image_url=image_url,
                url=f"{BASE}/item/{item_id}" if item_id else None,
                contact_name=item.get("contact_name"),
            )
        except Exception as e:
            print(f"[Yad2] parse error: {e}")
            return None
