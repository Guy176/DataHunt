"""
Yad2 scraper — hits their internal JSON feed API using curl_cffi
to impersonate Chrome at the TLS level (bypasses bot detection).
"""
import asyncio
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

API  = "https://gw.yad2.co.il/feed-search-legacy/realestate/rent"
WARM = "https://www.yad2.co.il/realestate/rent"


class Yad2Scraper(BaseScraper):
    async def scrape(self, filters: dict) -> list[Listing]:
        params = self._params(filters)
        results: list[Listing] = []

        async with AsyncSession(impersonate="chrome124") as s:
            try:
                r = await s.get(WARM)
                print(f"[Yad2] warm-up {r.status_code}")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"[Yad2] warm-up error: {e}")

            for page in range(1, 4):
                params["page"] = page
                try:
                    r = await s.get(API, params=params)
                    print(f"[Yad2] page {page} → {r.status_code}")
                    if r.status_code != 200:
                        print(f"[Yad2] body: {r.text[:400]}")
                        break
                    feed  = r.json().get("data", {}).get("feed", {})
                    items = feed.get("feed_items", [])
                    if not items:
                        break
                    for item in items:
                        if item.get("type") == "ad":
                            lst = self._parse(item)
                            if lst:
                                results.append(lst)
                    if page >= feed.get("total_pages", 1):
                        break
                    await asyncio.sleep(0.8)
                except Exception as e:
                    print(f"[Yad2] page {page} error: {e}")
                    break

        print(f"[Yad2] done — {len(results)} listings")
        return results

    def _params(self, f: dict) -> dict:
        p: dict = {"propertyGroup": "apartments", "pageSize": 40}
        if f.get("min_price"):    p["minPrice"] = f["min_price"]
        if f.get("max_price"):    p["maxPrice"] = f["max_price"]
        if f.get("min_rooms"):    p["minRooms"] = f["min_rooms"]
        if f.get("max_rooms"):    p["maxRooms"] = f["max_rooms"]
        if f.get("min_floor"):    p["minFloor"] = f["min_floor"]
        if f.get("max_floor"):    p["maxFloor"] = f["max_floor"]
        city = (f.get("city") or "").strip()
        if city:
            code = CITIES.get(city) or CITIES.get(city.lower())
            if code:
                p["city"] = code
        return p

    def _parse(self, item: dict) -> Optional[Listing]:
        try:
            addr  = item.get("address", {})
            city  = addr.get("city",         {}).get("text", "")
            nbhd  = addr.get("neighborhood", {}).get("text", "")
            st    = addr.get("street",       {}).get("text", "")
            full  = ", ".join(x for x in [st, nbhd, city] if x)

            price = None
            raw   = str(item.get("price", "")).replace(",", "").replace("₪", "").strip()
            if raw.isdigit():
                price = int(raw)

            rooms = None
            rv    = item.get("rooms")
            if rv is not None:
                try:
                    rooms = float(str(rv).replace("חדרים","").replace("חדר","").strip())
                except ValueError:
                    pass

            sqm = None
            sv  = item.get("square_meters")
            if sv:
                try:
                    sqm = float(str(sv).replace('מ"ר', "").strip())
                except ValueError:
                    pass

            floor = None
            fv    = item.get("floor")
            if fv is not None:
                try:
                    floor = int(fv)
                except (ValueError, TypeError):
                    pass

            images    = item.get("images", [])
            image_url = images[0].get("src") if images else None
            item_id   = str(item.get("id", ""))

            return Listing(
                id=f"yad2_{item_id}", source="yad2",
                title=item.get("title") or full,
                price=price, rooms=rooms, floor=floor, size_sqm=sqm,
                city=city, neighborhood=nbhd, street=st, address=full,
                description=item.get("info_text", ""),
                image_url=image_url,
                url=f"https://www.yad2.co.il/item/{item_id}",
                contact_name=item.get("contact_name"),
            )
        except Exception as e:
            print(f"[Yad2] parse error: {e}")
            return None
