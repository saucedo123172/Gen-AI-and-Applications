# Gen-AI-and-Applications
EDS 6397 18952 - Generative AI and Applications - Coursework

---

# CalBuddy

A CLI personal assistant that fetches weather from the **Open-Meteo API** for
each event on your local schedule and produces a single, friendly morning
briefing — powered by the **Anthropic Claude API**.

## What it does

- Reads your schedule from `calendar.json` (a list of events with `title`,
  `start`, `end`, `location`).
- For **each event**, geocodes its `location` (Open-Meteo Geocoding API) and
  fetches the **forecast at that event's start time** (Open-Meteo Forecast API).
- Sends the schedule + per-event weather to Claude, which writes a concise
  (under 250 words), actionable briefing as **CalBuddy**.

## Project structure

```
├── src/
│   ├── main.py            # CLI entry point
│   ├── weather.py         # Open-Meteo geocoding + forecast (per event)
│   ├── calendar_reader.py # Reads/validates calendar.json gracefully
│   ├── advisor.py         # Claude-powered advice engine
│   └── config.py          # Config + CalBuddy persona/rules system prompt
├── specs/
│   └── PRD.md             # Product requirements (source of truth)
├── docs/
│   └── rules.md           # Persona & constraint rules
├── tests/
│   ├── test_weather.py
│   ├── test_calendar.py
│   └── test_advisor.py
├── calendar.json          # Your schedule (user-maintained)
├── requirements.txt
└── README.md
```

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your_api_key_here"
```

## Usage

```bash
python src/main.py
```

By default it reads `calendar.json` from the current directory. Point it
elsewhere with the `CALBUDDY_CALENDAR` environment variable:

```bash
CALBUDDY_CALENDAR=/path/to/calendar.json python src/main.py
```

### Example `calendar.json`

```json
[
  {
    "title": "Morning Gym",
    "start": "2026-06-27T10:00:00",
    "end": "2026-06-27T12:00:00",
    "location": "Life Time Gym - Champions, Houston"
  }
]
```

## Behavior notes

- **Per-event weather.** There is no single location — every event's weather is
  for its own place and start time.
- **Units.** US locations show Fahrenheit only; non-US locations show both
  Celsius and Fahrenheit (e.g. `27°C / 81°F`), driven by the geocoded country.
- **All events are processed** regardless of date — there is no filtering to
  "today".
- **Graceful degradation.** A missing/invalid `calendar.json`, an event without
  a resolvable location, or a weather API failure never crashes the app — that
  event's weather is simply skipped, and an empty calendar yields a clear-day
  briefing with a general tip.

## Running the tests

```bash
pip install -r requirements.txt
pytest
```

The tests mock all network and API calls, so they run offline and without an
API key.
