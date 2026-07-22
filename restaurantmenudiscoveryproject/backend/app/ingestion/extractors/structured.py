"""Parse schema.org Menu/MenuSection/MenuItem JSON-LD into canonical MenuItems."""

from app.schemas import MenuItem


def _parse_price(offers: dict | list | None) -> float | None:
    if offers is None:
        return None
    offer = offers[0] if isinstance(offers, list) else offers
    if not isinstance(offer, dict):
        return None
    price = offer.get("price")
    try:
        return float(price) if price is not None else None
    except ValueError:
        return None


def _parse_section(section: dict, category: str | None = None) -> list[MenuItem]:
    items: list[MenuItem] = []
    section_name = section.get("name", category)

    for sub in section.get("hasMenuSection", []) or []:
        items.extend(_parse_section(sub, category=sub.get("name", section_name)))

    for entry in section.get("hasMenuItem", []) or []:
        items.append(
            MenuItem(
                name=entry.get("name", "Unnamed item"),
                description=entry.get("description"),
                price=_parse_price(entry.get("offers")),
                category=section_name,
            )
        )

    return items


def parse_structured_menu(menu_entries: list[dict]) -> list[MenuItem]:
    items: list[MenuItem] = []
    for menu in menu_entries:
        items.extend(_parse_section(menu))
    return items
