"""Orchestrates discovery -> menu finding -> extraction -> storage for an area.

Restaurants with no extractable menu are still stored (so we don't re-crawl
them every run) but marked `not_found`; the API layer is responsible for
filtering those out of any results shown to the app.
"""

from app.db import MenuItemRow, RestaurantRow, SessionLocal
from app.ingestion.extractors.llm import extract_menu_from_html
from app.ingestion.extractors.pdf import extract_menu_from_pdf
from app.ingestion.extractors.structured import parse_structured_menu
from app.ingestion.menu_finder import find_menu_source
from app.ingestion.places import find_restaurants, geocode_area
from app.rag.embeddings import embed_text
from app.schemas import MenuItem, MenuStatus

# Below this many parsed items, the heuristic PDF parser is considered to
# have failed and we don't bother falling back to the LLM for a PDF (the
# LLM fallback is reserved for HTML, where it's the only option anyway).
MIN_PDF_ITEMS = 3


def _extract_menu_items(website: str) -> list[MenuItem]:
    source = find_menu_source(website)

    if source["type"] == "structured":
        return parse_structured_menu(source["data"])

    if source["type"] == "pdf":
        items = extract_menu_from_pdf(source["url"])
        return items if len(items) >= MIN_PDF_ITEMS else []

    if source["type"] == "html":
        return extract_menu_from_html(source["html"])

    return []


def ingest_area(area_query: str, radius_m: int) -> dict:
    lat, lng = geocode_area(area_query)
    restaurants = find_restaurants(lat, lng, radius_m)

    found_count = 0
    with SessionLocal() as session:
        for r in restaurants:
            menu_items = _extract_menu_items(r["website"]) if r["website"] else []
            status = MenuStatus.FOUND if menu_items else MenuStatus.NOT_FOUND
            if menu_items:
                found_count += 1

            row = session.merge(
                RestaurantRow(
                    place_id=r["place_id"],
                    name=r["name"],
                    address=r["address"],
                    lat=r["lat"],
                    lng=r["lng"],
                    website=r["website"],
                    menu_status=status.value,
                )
            )

            for idx, item in enumerate(menu_items):
                session.merge(
                    MenuItemRow(
                        id=f"{r['place_id']}:{idx}",
                        restaurant_id=row.place_id,
                        name=item.name,
                        description=item.description,
                        price=item.price,
                        currency=item.currency,
                        category=item.category,
                        embedding=embed_text(f"{item.name} {item.description or ''}"),
                    )
                )

        session.commit()

    return {"area": area_query, "restaurants_found": len(restaurants), "menus_found": found_count}
