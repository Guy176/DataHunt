"""
Yad2 scraper — uses Yad2's internal JSON feed API (publicly accessible,
the same endpoint their website calls).
"""

import asyncio
import httpx
from typing import Optional
from .base import BaseScraper, Listing

# Yad2 city codes (city name -> numeric code used in their API)
YAD2_CITIES: dict[str, str] = {
    "תל אביב": "5000",
    "ירושלים": "3000",
    "חיפה": "4000",
    "ראשון לציון": "8300",
    "פתח תקווה": "7900",
    "אשדוד": "70",
    "נתניה": "7400",
    "באר שבע": "9000",
    "בני ברק": "6300",
    "חולון": "6400",
    "רמת גן": "8600",
    "אשקלון": "40",
    "רחובות": "8400",
    "בת ים": "6200",
    "בית שמש": "1200",
    "כפר סבא": "9200",
    "הרצליה": "6600",
    "חדרה": "6500",
    "מודיעין": "10200",
    "לוד": "7000",
    "רמלה": "8500",
    "עפולה": "9700",
    "נצרת עילית": "7600",
    "אילת": "100",
    "טבריה": "9500",
    "צפת": "9300",
    "קריית גת": "1050",
    "קריית שמונה": "1070",
    "דימונה": "1900",
    "יבנה": "6900",
    "גבעתיים": "6100",
    "אור יהודה": "140",
    "מגדל העמק": "7100",
    "עכו": "9800",
    "נהריה": "7300",
    # English aliases
    "tel aviv": "5000",
    "jerusalem": "3000",
    "haifa": "4000",
    "rishon lezion": "8300",
    "petah tikva": "7900",
    "ashdod": "70",
    "netanya": "7400",
    "beer sheva": "9000",
    "bnei brak": "6300",
    "holon": "6400",
    "ramat gan": "8600",
    "ashkelon": "40",
    "rehovot": "8400",
    "bat yam": "6200",
    "kfar saba": "9200",
    "herzliya": "6600",
    "hadera": "6500",
    "modiin": "10200",
    "lod": "7000",
    "eilat": "100",
}


class Yad2Scraper(BaseScraper):
    BASE_URL = "https://gw.yad2.co.il/feed-search-legacy/realestate/rent"
    MAX_PAGES = 3

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.yad2.co.il/",
        "Origin": "https://www.yad2.co.il",
    }

    async def scrape(self, filters: dict) -> list[Listing]:
        params = self._build_params(filters)
        results: list[Listing] = []

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for page in range(1, self.MAX_PAGES + 1):
                params["page"] = page
                try:
                    resp = await client.get(
                        self.BASE_URL, params=params, headers=self.HEADERS
                    )
                    if resp.status_code != 200:
                        print(f"[Yad2] HTTP {resp.status_code} on page {page}")
                        break

                    data = resp.json()
                    feed = data.get("data", {}).get("feed", {})
                    items = feed.get("feed_items", [])

                    if not items:
                        break

                    for item in items:
                        if item.get("type") == "ad":
                            listing = self._parse(item)
                            if listing:
                                results.append(listing)

                    total_pages = feed.get("total_pages", 1)
                    if page >= total_pages:
                        break

                    await asyncio.sleep(0.8)

                except httpx.RequestError as e:
                    print(f"[Yad2] Request error: {e}")
                    break
                except Exception as e:
                    print(f"[Yad2] Unexpected error: {e}")
                    break

        return results

    # ------------------------------------------------------------------
    def _build_params(self, filters: dict) -> dict:
        params: dict = {
            "propertyGroup": "apartments",
            "pageSize": 40,
        }

        if filters.get("min_price"):
            params["minPrice"] = filters["min_price"]
        if filters.get("max_price"):
            params["maxPrice"] = filters["max_price"]
        if filters.get("min_rooms"):
            params["minRooms"] = filters["min_rooms"]
        if filters.get("max_rooms"):
            params["maxRooms"] = filters["max_rooms"]
        if filters.get("min_floor"):
            params["minFloor"] = filters["min_floor"]
        if filters.get("max_floor"):
            params["maxFloor"] = filters["max_floor"]

        city = (filters.get("city") or "").strip().lower()
        if city:
            # Try exact match, then lowercase
            code = YAD2_CITIES.get(filters["city"]) or YAD2_CITIES.get(city)
            if code:
                params["city"] = code

        if filters.get("neighborhood"):
            params["neighborhood"] = filters["neighborhood"]

        return params

    def _parse(self, item: dict) -> Optional[Listing]:
        try:
            raw_price = item.get("price", "")
            price: Optional[int] = None
            if raw_price:
                cleaned = str(raw_price).replace(",", "").replace("₪", "").strip()
                if cleaned.isdigit():
                    price = int(cleaned)

            addr = item.get("address", {})
            city = addr.get("city", {}).get("text", "")
            neighborhood = addr.get("neighborhood", {}).get("text", "")
            street = addr.get("street", {}).get("text", "")
            full_address = ", ".join(p for p in [street, neighborhood, city] if p)

            images = item.get("images", [])
            image_url = images[0].get("src") if images else None

            rooms_raw = item.get("rooms")
            rooms: Optional[float] = None
            if rooms_raw is not None:
                try:
                    rooms = float(str(rooms_raw).replace("חדרים", "").replace("חדר", "").strip())
                except ValueError:
                    pass

            sqm_raw = item.get("square_meters")
            size_sqm: Optional[float] = None
            if sqm_raw:
                try:
                    size_sqm = float(str(sqm_raw).replace("מ\"ר", "").strip())
                except ValueError:
                    pass

            floor_raw = item.get("floor")
            floor: Optional[int] = None
            if floor_raw is not None:
                try:
                    floor = int(floor_raw)
                except (ValueError, TypeError):
                    pass

            item_id = str(item.get("id", ""))
            return Listing(
                id=f"yad2_{item_id}",
                source="yad2",
                title=item.get("title", full_address),
                price=price,
                rooms=rooms,
                floor=floor,
                size_sqm=size_sqm,
                city=city,
                neighborhood=neighborhood,
                street=street,
                address=full_address,
                description=item.get("info_text", ""),
                image_url=image_url,
                url=f"https://www.yad2.co.il/item/{item_id}",
                contact_name=item.get("contact_name"),
            )
        except Exception as e:
            print(f"[Yad2] Parse error: {e}")
            return None
