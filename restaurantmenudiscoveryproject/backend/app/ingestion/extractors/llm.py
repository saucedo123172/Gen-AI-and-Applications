"""Last-resort multimodal extraction for messy HTML or scanned/photographed menus.

Only reached when the structured and heuristic parsers fail, to keep LLM
call volume (and cost) minimal.
"""

import base64
import json

import anthropic
from bs4 import BeautifulSoup

from app.config import settings
from app.schemas import MenuItem

MODEL = "claude-haiku-4-5-20251001"

PROMPT = """Extract every menu item from the content below. Respond with ONLY a JSON \
array, no other text, where each element has this shape:
{"name": str, "description": str | null, "price": number | null, "category": str | null}

Content:
"""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _parse_items(raw_text: str) -> list[MenuItem]:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return []
    return [MenuItem(**entry) for entry in data if entry.get("name")]


def extract_menu_from_html(html: str) -> list[MenuItem]:
    text = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
    message = _client().messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": PROMPT + text}],
    )
    return _parse_items(message.content[0].text)


def extract_menu_from_image(image_bytes: bytes, media_type: str = "image/jpeg") -> list[MenuItem]:
    encoded = base64.standard_b64encode(image_bytes).decode("utf-8")
    message = _client().messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": encoded},
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )
    return _parse_items(message.content[0].text)
