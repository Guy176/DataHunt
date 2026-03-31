from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Listing:
    id: str
    source: str
    title: str = ""
    price: Optional[int] = None
    rooms: Optional[float] = None
    floor: Optional[int] = None
    size_sqm: Optional[float] = None
    city: str = ""
    neighborhood: str = ""
    street: str = ""
    address: str = ""
    description: str = ""
    image_url: Optional[str] = None
    url: str = ""
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "price": self.price,
            "rooms": self.rooms,
            "floor": self.floor,
            "size_sqm": self.size_sqm,
            "city": self.city,
            "neighborhood": self.neighborhood,
            "street": self.street,
            "address": self.address,
            "description": self.description,
            "image_url": self.image_url,
            "url": self.url,
            "contact_name": self.contact_name,
            "phone": self.phone,
            "created_at": self.created_at,
        }


class BaseScraper:
    async def scrape(self, filters: dict) -> list[Listing]:
        raise NotImplementedError
