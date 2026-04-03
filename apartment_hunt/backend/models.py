from pydantic import BaseModel, Field
from typing import Optional

class SearchFilters(BaseModel):
    min_price:    Optional[int]   = None
    max_price:    Optional[int]   = None
    min_rooms:    Optional[float] = None
    max_rooms:    Optional[float] = None
    min_floor:    Optional[int]   = None
    max_floor:    Optional[int]   = None
    city:         Optional[str]   = None
    neighborhood: Optional[str]   = None
    sources:      list[str]       = Field(default=["yad2", "madlan"])

class ManualListing(BaseModel):
    title:        str
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

class ListingOut(BaseModel):
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
    is_favorite:  bool            = False
    created_at:   Optional[str]   = None
    scraped_at:   Optional[str]   = None
