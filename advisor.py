"""The LLM-powered advice engine.

Builds a plain-text context block from the schedule + per-event weather and asks
Claude (as CalBuddy) to produce a concise, friendly briefing. The persona and
behavioral rules live in ``config.SYSTEM_PROMPT``.
"""

import anthropic

import config


def _format_time_range(start, end):
    """Render a compact HH:MM–HH:MM range from ISO datetimes."""
    def hhmm(value):
        if value and "T" in value:
            return value.split("T")[1][:5]
        return value or "?"

    return f"{hhmm(start)}–{hhmm(end)}"


def build_context(events_with_weather):
    """Build the user-message context from (event, weather) pairs.

    ``weather`` is the dict from :func:`weather.get_event_weather` or ``None``
    when it could not be resolved. Returns a string ready to send to the model.
    """
    if not events_with_weather:
        return (
            "The user's calendar has no events. "
            "Let them know their schedule is clear and give a brief, general "
            "weather tip for the day."
        )

    lines = [
        "Here is the schedule with per-event weather (each figure is the "
        "forecast at that event's start time). Write the briefing.",
        "",
    ]
    for i, (event, weather) in enumerate(events_with_weather, start=1):
        lines.append(f"Event {i}:")
        lines.append(f"- Title: {event.get('title') or 'Untitled'}")
        lines.append(f"- Time: {_format_time_range(event.get('start'), event.get('end'))}")
        lines.append(f"- Location: {event.get('location') or 'unspecified'}")
        if weather:
            details = [f"{weather['conditions']}"]
            if weather.get("temperature"):
                details.append(f"temperature {weather['temperature']}")
            if weather.get("feels_like"):
                details.append(f"feels like {weather['feels_like']}")
            if weather.get("humidity") is not None:
                details.append(f"humidity {weather['humidity']}%")
            if weather.get("precipitation_probability") is not None:
                details.append(
                    f"precipitation chance {weather['precipitation_probability']}%"
                )
            if weather.get("wind_speed_kmh") is not None:
                details.append(f"wind {weather['wind_speed_kmh']} km/h")
            lines.append("- Weather: " + ", ".join(details))
        else:
            lines.append("- Weather: unavailable (location could not be resolved)")
        lines.append("")

    return "\n".join(lines).strip()


def generate_briefing(events_with_weather, client=None):
    """Generate the briefing text via the Claude API.

    ``client`` may be injected (used in tests); otherwise a default client is
    created from the environment API key.
    """
    if client is None:
        client = anthropic.Anthropic(api_key=config.get_api_key())

    context = build_context(events_with_weather)
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=config.MAX_BRIEFING_TOKENS,
        system=config.SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )

    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    return text.strip()
