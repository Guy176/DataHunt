from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class Listing:
    id:           str
    source:       str
    title:        Optional[str]   = None
    price:        Optional[int]   = None
    rooms:        Optional[float] = None
    floor:        Optional[int]   = None
    size_sqm:     Optional[float] = None
    city:         Optional[str]   = None
    neighborhood: Optional[str]   = None
    street:       Optional[str]   = None
    address:      Optional[str]   = None
    description:  Optional[str]   = None
    image_url:    Optional[str]   = None
    url:          Optional[str]   = None
    contact_name: Optional[str]   = None
    phone:        Optional[str]   = None
    created_at:   Optional[str]   = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

class BaseScraper(ABC):
    @abstractmethod
    async def scrape(self, filters: dict) -> list[Listing]: ...
