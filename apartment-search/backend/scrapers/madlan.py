"""
Madlan scraper — fetches their Next.js search page and extracts
the __NEXT_DATA__ JSON blob that contains all listing data.
Uses curl_cffi to impersonate Chrome and bypass bot detection.
"""

import asyncio
import json
import re
from typing import Optional
from curl_cffi.requests import AsyncSession
from .base import BaseScraper, Listing

MADLAN_CITY_SLUGS: dict[str, str] = {
    "תל אביב": "tel-aviv-yafo",
    "ירושלים": "jerusalem",
    "חיפה": "haifa",
    "ראשון לציון": "rishon-leziyyon",
    "פתח תקווה": "petah-tikva",
    "אשדוד": "ashdod",
    "נתניה": "netanya",
    "באר שבע": "beer-sheva",
    "בני ברק": "bnei-brak",
    "חולון": "holon",
    "רמת גן": "ramat-gan",
    "אשקלון": "ashkelon",
    "רחובות": "rehovot",
    "בת ים": "bat-yam",
    "כפר סבא": "kfar-sava",
    "הרצליה": "herzliya",
    "חדרה": "hadera",
    "מודיעין": "modiin",
    "לוד": "lod",
    "אילת": "eilat",
    # English aliases
    "tel aviv": "tel-aviv-yafo",
    "jerusalem": "jerusalem",
    "haifa": "haifa",
    "rishon lezion": "rishon-leziyyon",
    "petah tikva": "petah-tikva",
    "ashdod": "ashdod",
    "netanya": "netanya",
    "beer sheva": "beer-sheva",
    "bnei brak": "bnei-brak",
    "holon": "holon",
    "ramat gan": "ramat-gan",
    "ashkelon": "ashkelon",
    "rehovot": "rehovot",
    "bat yam": "bat-yam",
    "kfar saba": "kfar-sava",
    "herzliya": "herzliya",
    "hadera": "hadera",
    "modiin": "modiin",
    "lod": "lod",
    "eilat": "eilat",
}

MADLAN_BASE = "https://www.madlan.co.il"


class MadlanScraper(BaseScraper):
    WARM_URL = "https://www.madlan.co.il"

    async def scrape(self, filters: dict) -> list[Listing]:
        city = (filters.get("city") or "").strip()
        slug = (
            MADLAN_CITY_SLUGS.get(city)
            or MADLAN_CITY_SLUGS.get(city.lower())
            or "israel"
        )

        url = f"{MADLAN_BASE}/for-rent/{slug}"
        params = self._build_params(filters)
        results: list[Listing] = []

        async with AsyncSession(impersonate="chrome124") as client:
            # Warm up: visit main site to get session cookies
            try:
                r = await client.get(self.WARM_URL)
                print(f"[Madlan] Warm-up: HTTP {r.status_code}")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"[Madlan] Warm-up failed (continuing): {e}")

            for page in range(1, 4):
                try:
                    page_params = {**params, "page": page}
                    resp = await client.get(url, params=page_params)
                    print(f"[Madlan] Page {page}: HTTP {resp.status_code}")

                    if resp.status_code != 200:
                        print(f"[Madlan] Body preview: {resp.text[:300]}")
                        break

                    items = self._extract_listings(resp.text)
                    if not items:
                        print(f"[Madlan] No __NEXT_DATA__ listings on page {page}")
                        break

                    for raw in items:
                        listing = self._parse(raw)
                        if listing:
                            results.append(listing)

                    await asyncio.sleep(1.0)

                except Exception as e:
                    print(f"[Madlan] Error: {e}")
                    break

        print(f"[Madlan] Done — {len(results)} listings")
        return results

    def _build_params(self, filters: dict) -> dict:
        params: dict = {}
        if filters.get("min_price"):
            params["price_min"] = filters["min_price"]
        if filters.get("max_price"):
            params["price_max"] = filters["max_price"]
        if filters.get("min_rooms"):
            params["rooms_min"] = filters["min_rooms"]
        if filters.get("max_rooms"):
            params["rooms_max"] = filters["max_rooms"]
        if filters.get("min_floor"):
            params["floor_min"] = filters["min_floor"]
        if filters.get("max_floor"):
            params["floor_max"] = filters["max_floor"]
        return params

    def _extract_listings(self, html: str) -> list[dict]:
        match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        props = data.get("props", {}).get("pageProps", {})

        for key in ("listings", "items", "feed", "results", "data"):
            val = props.get(key)
            if isinstance(val, list) and val:
                return val
            if isinstance(val, dict):
                for subkey in ("listings", "items", "feed", "results"):
                    sub = val.get(subkey)
                    if isinstance(sub, list) and sub:
                        return sub

        return self._deep_find_listings(props)

    def _deep_find_listings(self, obj, depth=0) -> list[dict]:
        if depth > 5:
            return []
        if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "price" in obj[0]:
            return obj
        if isinstance(obj, dict):
            for v in obj.values():
                result = self._deep_find_listings(v, depth + 1)
                if result:
                    return result
        return []

    def _parse(self, item: dict) -> Optional[Listing]:
        try:
            item_id = str(item.get("id") or item.get("_id") or item.get("listingId", ""))
            if not item_id:
                return None

            price_raw = item.get("price") or item.get("rentPrice") or 0
            try:
                price = int(str(price_raw).replace(",", "").replace("₪", "").strip())
            except (ValueError, TypeError):
                price = None

            rooms_raw = item.get("rooms") or item.get("roomsCount")
            try:
                rooms = float(rooms_raw) if rooms_raw is not None else None
            except (ValueError, TypeError):
                rooms = None

            floor_raw = item.get("floor") or item.get("floorNumber")
            try:
                floor = int(floor_raw) if floor_raw is not None else None
            except (ValueError, TypeError):
                floor = None

            sqm_raw = item.get("size") or item.get("squareMeters") or item.get("area")
            try:
                size_sqm = float(sqm_raw) if sqm_raw is not None else None
            except (ValueError, TypeError):
                size_sqm = None

            location = item.get("location") or item.get("address") or {}
            if isinstance(location, str):
                address = location
                city = neighborhood = street = ""
            else:
                city = location.get("city", "") or item.get("city", "")
                neighborhood = location.get("neighborhood", "") or item.get("neighborhood", "")
                street = location.get("street", "") or item.get("street", "")
                address = ", ".join(p for p in [street, neighborhood, city] if p)

            images = item.get("images") or item.get("photos") or []
            image_url = None
            if images and isinstance(images[0], dict):
                image_url = images[0].get("url") or images[0].get("src")
            elif images and isinstance(images[0], str):
                image_url = images[0]

            listing_url = item.get("url") or item.get("link") or f"{MADLAN_BASE}/listing/{item_id}"
            if listing_url and not listing_url.startswith("http"):
                listing_url = MADLAN_BASE + listing_url

            return Listing(
                id=f"madlan_{item_id}",
                source="madlan",
                title=item.get("title") or address or "Madlan Listing",
                price=price,
                rooms=rooms,
                floor=floor,
                size_sqm=size_sqm,
                city=city,
                neighborhood=neighborhood,
                street=street,
                address=address,
                description=item.get("description") or item.get("details") or "",
                image_url=image_url,
                url=listing_url,
                contact_name=(
                    item.get("contactName")
                    or (item.get("agent", {}).get("name") if isinstance(item.get("agent"), dict) else None)
                ),
            )
        except Exception as e:
            print(f"[Madlan] Parse error: {e}")
            return None
