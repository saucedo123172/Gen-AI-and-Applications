"""CalBuddy CLI entry point.

Reads the local schedule, fetches per-event weather from Open-Meteo, and prints
a single Claude-generated morning briefing. Every failure mode degrades to a
friendly, user-facing message — internals are never surfaced.
"""

import sys

import config
from advisor import generate_briefing
from calendar_reader import load_events
from weather import get_event_weather


def enrich_events(events):
    """Pair each event with its per-event weather (or ``None`` on failure)."""
    return [(event, get_event_weather(event)) for event in events]


def main():
    events = load_events(config.CALENDAR_PATH)
    events_with_weather = enrich_events(events)

    try:
        briefing = generate_briefing(events_with_weather)
    except Exception:
        # Degrade gracefully — never leak module names, stack traces, or API details.
        print(
            "CalBuddy couldn't put your briefing together right now. "
            "Please check your connection and try again in a moment."
        )
        return 1

    print(briefing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
