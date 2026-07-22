"""Waterfall logic for locating a restaurant's menu from its website.

Order (cheapest/most reliable first):
  1. schema.org structured data (JSON-LD) on the homepage.
  2. A linked page whose text/href mentions "menu".
     - If that page is a PDF, hand off to the PDF extractor.
     - If it's HTML, hand off to the LLM/heuristic extractor.
  3. Nothing usable found -> not_found.
"""

import json
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENT = "MenuDiscoveryBot/0.1 (school project)"
TIMEOUT = 10


def _get(url: str) -> requests.Response:
    return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)


def _find_structured_menu(soup: BeautifulSoup) -> list[dict] | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            if entry.get("@type") in ("Menu", "Restaurant") and "hasMenu" in entry:
                return entry["hasMenu"] if isinstance(entry["hasMenu"], list) else [entry["hasMenu"]]
            if entry.get("@type") == "Menu":
                return [entry]
    return None


def _find_menu_link(soup: BeautifulSoup, base_url: str) -> str | None:
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").lower()
        href = a["href"].lower()
        if "menu" in text or "menu" in href:
            return urljoin(base_url, a["href"])
    return None


def find_menu_source(website: str) -> dict:
    """Returns one of:
    {"type": "structured", "data": [...]}
    {"type": "pdf", "url": str}
    {"type": "html", "url": str, "html": str}
    {"type": "not_found"}
    """
    try:
        home_resp = _get(website)
        home_resp.raise_for_status()
    except requests.RequestException:
        return {"type": "not_found"}

    soup = BeautifulSoup(home_resp.text, "html.parser")

    structured = _find_structured_menu(soup)
    if structured:
        return {"type": "structured", "data": structured}

    menu_url = _find_menu_link(soup, website)
    if not menu_url:
        return {"type": "not_found"}

    try:
        menu_resp = _get(menu_url)
        menu_resp.raise_for_status()
    except requests.RequestException:
        return {"type": "not_found"}

    content_type = menu_resp.headers.get("Content-Type", "")
    if "pdf" in content_type or menu_url.lower().endswith(".pdf"):
        return {"type": "pdf", "url": menu_url}

    return {"type": "html", "url": menu_url, "html": menu_resp.text}
