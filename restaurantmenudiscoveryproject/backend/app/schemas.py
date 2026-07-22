"""Canonical data schemas shared across ingestion and the API."""

from enum import Enum

from pydantic import BaseModel


class MenuStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"


class MenuItem(BaseModel):
    name: str
    description: str | None = None
    price: float | None = None
    currency: str = "USD"
    category: str | None = None
    dietary_tags: list[str] = []


class Restaurant(BaseModel):
    place_id: str
    name: str
    address: str
    lat: float
    lng: float
    website: str | None = None
    menu_status: MenuStatus
    menu_items: list[MenuItem] = []
