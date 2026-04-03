"""
Yad2 scraper — scrapes www.yad2.co.il/realestate/rent HTML and extracts
listings from the React Query dehydratedState embedded in __NEXT_DATA__.
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
                    r = await s.get(f"{BASE}/realestate/rent", params=params)
                    print(f"[Yad2] page {page} → {r.status_code}")

                    if r.status_code != 200:
                        print(f"[Yad2] body: {r.text[:300]}")
                        break

                    items = self._extract(r.text)
                    if not items:
                        break

                    before = len(results)
                    for item in items:
                        if not isinstance(item, dict) or not item.get("id"):
                            continue  # skip ads (no id) and non-dict entries
                        lst = self._parse(item)
                        if lst:
                            results.append(lst)

                    print(f"[Yad2] page {page}: {len(results) - before} listings added")
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
            print("[Yad2] __NEXT_DATA__ not found")
            return []

        try:
            data = json.loads(m.group(1))
        except Exception as e:
            print(f"[Yad2] JSON parse error: {e}")
            return []

        props = data.get("props", {}).get("pageProps", {})

        # ── Strategy 1: React Query dehydratedState (current Yad2 structure) ──
        queries = props.get("dehydratedState", {}).get("queries", [])
        for q in queries:
            items = (q.get("state", {})
                      .get("data", {})
                      .get("feed", {})
                      .get("feed_items", []))
            if items:
                print(f"[Yad2] dehydratedState → {len(items)} raw items")
                return items

        # ── Strategy 2: direct feed key ──
        feed = props.get("feed")
        if isinstance(feed, dict):
            items = feed.get("feed_items", [])
            if items:
                print(f"[Yad2] feed.feed_items → {len(items)} items")
                return items
        if isinstance(feed, list) and feed:
            print(f"[Yad2] feed (list) → {len(feed)} items")
            return feed

        # ── Strategy 3: other known paths ──
        for path in [["listings"], ["items"], ["data", "feed", "feed_items"]]:
            obj = props
            for key in path:
                obj = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(obj, list) and obj:
                print(f"[Yad2] found at {path} → {len(obj)} items")
                return obj

        print(f"[Yad2] no items found; pageProps keys: {list(props.keys())}")
        return []

    def _parse(self, item: dict) -> Optional[Listing]:
        try:
            item_id = str(item.get("id", ""))

            # price is a plain number in the HTML page data
            price = None
            pv = item.get("price")
            if pv is not None:
                try:
                    price = int(str(pv).replace(",", "").replace("₪", "").strip())
                except (ValueError, TypeError):
                    pass

            # row_4: [{value: rooms}, {value: floor}, {value: sqm}]
            row4  = item.get("row_4") or []
            rooms = floor = sqm = None
            try: rooms = float(row4[0]["value"]) if len(row4) > 0 else None
            except (KeyError, TypeError, ValueError, IndexError): pass
            try:
                fv = row4[1]["value"] if len(row4) > 1 else None
                floor = int(fv) if fv is not None and str(fv).lstrip("-").isdigit() else None
            except (KeyError, TypeError, ValueError, IndexError): pass
            try: sqm = float(row4[2]["value"]) if len(row4) > 2 else None
            except (KeyError, TypeError, ValueError, IndexError): pass

            # address fields
            city         = item.get("city", "")
            neighborhood = item.get("neighborhood", "")
            street       = item.get("title_1", "")   # street address
            full         = ", ".join(x for x in [street, neighborhood, city] if x)

            # image
            images    = item.get("images", [])
            image_url = None
            if images and isinstance(images[0], dict):
                image_url = images[0].get("src") or images[0].get("url")

            return Listing(
                id=f"yad2_{item_id}", source="yad2",
                title=street or full,
                price=price, rooms=rooms, floor=floor, size_sqm=sqm,
                city=city, neighborhood=neighborhood, street=street, address=full,
                description=item.get("info_text", "") or "",
                image_url=image_url,
                url=f"{BASE}/item/{item_id}",
                contact_name=None,
            )
        except Exception as e:
            print(f"[Yad2] parse error: {e} | item keys: {list(item.keys())[:8]}")
            return None
