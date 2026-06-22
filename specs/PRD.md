# Product Requirements Document

## Purpose
A CLI personal assistant that fetches weather from the Open-Meteo API for each scheduled event and cross-references the user's local schedule to deliver context-aware, actionable daily advice.

## Target User
A professional who wants to stay consistent with their goals and want a single morning briefing. 

## Input 
- Live weather data: Open-Meteo API (free, no key required)
- Geocoding: Open-Meteo Geocoding API (free, no key required) — converts each event's `location` string into coordinates
- Schedule: `calendar.json` — local file, user-maintained
  - Schema: list of events with `title`, `start`, `end`, `location`
  - `location` is a free-text place string (e.g., `"Central Park"`, `"Blue Bottle, SF"`) used to geocode coordinates for that event's weather lookup

## Outputs
A plain-text briefing printed to the terminal, e.g.:
> "You have an outdoor run at 7am. Forecast temperature is 81°F
>  with 70% humidity — bring water and sunscreen.
>  Your 12pm lunch is nearby, expect partly cloudy skies.
>  Best time to leave for lunch is 11:35am."

## Advice Engine
LLM-powered via Anthropic Claude API.
The `advisor.py` module sends weather + schedule as context
and asks the model to produce a concise, friendly briefing.

## Constraints
- Only use weather data from Open-Meteo
- Geocoding uses the Open-Meteo Geocoding API (free, no key)
- Must handle missing/invalid calendar.json gracefully
- Response must be under 250 words
- **Per-event weather:** There is no single user location. For each event, geocode its `location` field into coordinates and fetch that event's weather from Open-Meteo as the forecast at the event's start time. Weather advice in the briefing is location-specific per event.
- If an event's `location` is missing or cannot be geocoded, skip the weather lookup for that event and note it gracefully in the briefing rather than failing.
- **Temperature units (per event):** US locations show Fahrenheit only; non-US locations show both Celsius and Fahrenheit (e.g., `27°C / 81°F`). The unit choice is driven by the geocoded location's country.
- **Event scope:** Process all events present in `calendar.json` regardless of date — there is no filtering to the current date. Each event's weather is the forecast at its own `start` datetime.
