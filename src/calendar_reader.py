"""Read and normalize the user's local schedule (calendar.json).

The reader is deliberately forgiving: a missing file, malformed JSON, or
unexpected shapes never raise — they degrade to an empty schedule so the rest of
CalBuddy can still produce a useful (empty-calendar) briefing.

Per the PRD, every event in the file is processed regardless of its date; there
is no filtering to "today".
"""

import json

# The exact, and only, fields defined by the calendar schema.
_FIELDS = ("title", "start", "end", "location")


def load_events(path):
    """Load events from ``path``.

    Returns a list of event dicts, each carrying exactly the schema fields
    (missing optional fields become ``None``). Returns ``[]`` for a missing
    file, invalid JSON, or any non-list top-level value.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        # Missing/unreadable file or invalid JSON — degrade gracefully.
        return []

    if not isinstance(data, list):
        return []

    events = []
    for item in data:
        if not isinstance(item, dict):
            # Skip anything that isn't an event object.
            continue
        events.append({field: item.get(field) for field in _FIELDS})
    return events
