from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import RestaurantRow, get_db
from app.ingestion.pipeline import ingest_area
from app.rag.search import search_menu_items

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("")
def list_restaurants(db: Session = Depends(get_db)):
    restaurants = db.query(RestaurantRow).filter(RestaurantRow.menu_status == "found").all()
    return [
        {"place_id": r.place_id, "name": r.name, "address": r.address, "website": r.website}
        for r in restaurants
    ]


@router.get("/search")
def search(
    q: str = Query(..., description="Natural language search, e.g. 'vegan appetizer'"),
    max_price: float | None = None,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    results = search_menu_items(db, q, max_price=max_price, limit=limit)
    return [
        {
            "restaurant": item.restaurant.name,
            "item": item.name,
            "description": item.description,
            "price": item.price,
        }
        for item in results
    ]


@router.post("/ingest")
def ingest(area_query: str, radius_m: int = 1500):
    """Kick off (offline/manual) ingestion for a test area. Not called by the app."""
    return ingest_area(area_query, radius_m)
