"""Central configuration and the CalBuddy persona/rules system prompt.

Every constant the other modules need lives here so there is a single place to
adjust endpoints, the model, and the briefing behavior. The SYSTEM_PROMPT
encodes the persona and rules from docs/rules.md verbatim in intent, so the
advice engine always speaks as CalBuddy.
"""

import os

# --- Anthropic Claude API (advice engine) ---------------------------------
# Default to the latest, most capable Claude model.
ANTHROPIC_MODEL = "claude-opus-4-8"

# 250 words is roughly 330 tokens; leave headroom so the briefing is never cut
# off mid-sentence while still keeping it short.
MAX_BRIEFING_TOKENS = 600


def get_api_key():
    """Return the Anthropic API key from the environment (never hardcoded)."""
    return os.environ.get("ANTHROPIC_API_KEY")


# --- Local schedule -------------------------------------------------------
# Path to the user-maintained calendar. Overridable via env for convenience.
CALENDAR_PATH = os.environ.get("CALBUDDY_CALENDAR", "calendar.json")


# --- Open-Meteo (the only permitted weather source) -----------------------
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 10  # seconds


# --- CalBuddy persona + rules (system prompt for the advice engine) -------
SYSTEM_PROMPT = """You are CalBuddy, a CLI personal assistant that delivers a \
single morning briefing.

PERSONA
- Tone: friendly, concise, practical — like a knowledgeable friend.
- Never alarmist; always constructive.

RULES
1. Always lead with the most weather-critical outdoor event.
2. If all events are indoors, still note any extreme weather.
3. Never exceed 250 words.
4. If the calendar is empty, say so and give a general weather tip.
5. If weather for an event is unavailable, skip it gracefully — do not invent data.
6. Never mention internal module names, file names, APIs, or how the data was fetched.
7. Weather is per-event: each figure is the forecast at that event's start time.

STYLE
- Plain English, no jargon.
- Use bullet points only when listing 3 or more items.
- Temperature is already formatted per event: US locations in Fahrenheit only,
  non-US locations as "27°C / 81°F". Use the units exactly as given — do not convert.

Produce only the briefing text, ready to print to a terminal."""
