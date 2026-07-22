"""Best-effort text-based PDF menu extraction (no LLM call).

Works for text-layer PDFs with a simple "name .... price" layout. Anything
that doesn't match the price pattern is dropped; the caller should fall
back to the LLM extractor if this yields too few items.
"""

import re
from io import BytesIO

import pdfplumber
import requests

from app.schemas import MenuItem

PRICE_PATTERN = re.compile(r"(.+?)\s*\$?\s*(\d+\.\d{2})\s*$")


def _download(url: str) -> bytes:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.content


def extract_menu_from_pdf(url: str) -> list[MenuItem]:
    pdf_bytes = _download(url)
    items: list[MenuItem] = []

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                match = PRICE_PATTERN.match(line.strip())
                if not match:
                    continue
                name, price = match.groups()
                name = name.strip(" .-")
                if not name:
                    continue
                items.append(MenuItem(name=name, price=float(price)))

    return items
