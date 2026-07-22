"""Semantic search over menu items, restricted to restaurants with a found menu."""

from sqlalchemy.orm import Session

from app.db import MenuItemRow, RestaurantRow
from app.rag.embeddings import embed_text


def search_menu_items(
    db: Session, query: str, max_price: float | None = None, limit: int = 10
) -> list[MenuItemRow]:
    query_embedding = embed_text(query)

    stmt = (
        db.query(MenuItemRow)
        .join(RestaurantRow, MenuItemRow.restaurant_id == RestaurantRow.place_id)
        .filter(RestaurantRow.menu_status == "found")
    )
    if max_price is not None:
        stmt = stmt.filter(MenuItemRow.price <= max_price)

    return stmt.order_by(MenuItemRow.embedding.cosine_distance(query_embedding)).limit(limit).all()
