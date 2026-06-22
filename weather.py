"""Per-event weather via the Open-Meteo APIs (the only permitted source).

For each event we:
  1. Geocode its free-text ``location`` into coordinates + country
     (Open-Meteo Geocoding API).
  2. Fetch the forecast for that location at the event's start time
     (Open-Meteo Forecast API).
  3. Format temperatures per the unit rule: US -> Fahrenheit only,
     non-US -> both Celsius and Fahrenheit.

Any failure (missing location, no geocoding match, network/API error) returns
``None`` for that event so the briefing can skip it gracefully. No data is
cached and no weather source other than Open-Meteo is used.
"""

import requests

import config

# WMO weather interpretation codes -> short, plain-English descriptions.
WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "freezing drizzle",
    57: "heavy freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "heavy freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light rain showers",
    81: "rain showers",
    82: "violent rain showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}


def describe_weather_code(code):
    """Map a WMO weather code to a short description."""
    return WEATHER_CODES.get(code, "unknown conditions")


def c_to_f(celsius):
    """Convert Celsius to Fahrenheit, rounded to a whole degree."""
    return round(celsius * 9 / 5 + 32)


def format_temp(celsius, is_us):
    """Format a temperature per the unit rule.

    US locations -> Fahrenheit only ("81°F").
    Non-US locations -> both ("27°C / 81°F").
    """
    if celsius is None:
        return None
    fahrenheit = c_to_f(celsius)
    if is_us:
        return f"{fahrenheit}°F"
    return f"{round(celsius)}°C / {fahrenheit}°F"


def geocode(location):
    """Resolve a free-text location into coordinates and country.

    Tries the full string first, then falls back to each comma-separated
    component (city-last, so "Some Gym, Houston" still resolves via "Houston").
    Returns ``None`` if nothing matches or the request fails.
    """
    if not location:
        return None

    candidates = [location]
    if "," in location:
        parts = [p.strip() for p in location.split(",") if p.strip()]
        for part in reversed(parts):  # last component (the city) first
            if part not in candidates:
                candidates.append(part)

    for name in candidates:
        try:
            resp = requests.get(
                config.GEOCODING_URL,
                params={"name": name, "count": 1, "format": "json"},
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            results = resp.json().get("results")
        except (requests.RequestException, ValueError):
            continue
        if results:
            top = results[0]
            return {
                "latitude": top.get("latitude"),
                "longitude": top.get("longitude"),
                "name": top.get("name"),
                "country": top.get("country"),
                "country_code": top.get("country_code"),
            }
    return None


def _hour_index(times, start_iso):
    """Return the index into ``times`` closest to the event's start hour."""
    if not times:
        return None
    date = start_iso.split("T")[0]
    hour = "12"
    if "T" in start_iso:
        hour = start_iso.split("T")[1][:2]
    target = f"{date}T{hour}:00"
    if target in times:
        return times.index(target)
    # Fall back to the entry on the same date with the nearest hour.
    try:
        target_hour = int(hour)
    except ValueError:
        return 0
    best_idx, best_diff = None, None
    for idx, stamp in enumerate(times):
        if not stamp.startswith(date) or "T" not in stamp:
            continue
        try:
            this_hour = int(stamp.split("T")[1][:2])
        except ValueError:
            continue
        diff = abs(this_hour - target_hour)
        if best_diff is None or diff < best_diff:
            best_idx, best_diff = idx, diff
    return best_idx if best_idx is not None else 0


def fetch_forecast(latitude, longitude, start_iso):
    """Fetch the Open-Meteo forecast at the event's start time.

    Returns a dict of raw values (temperatures in Celsius) or ``None`` on
    failure.
    """
    if not start_iso:
        return None
    date = start_iso.split("T")[0]
    try:
        resp = requests.get(
            config.FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "hourly": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "precipitation_probability,weather_code,wind_speed_10m"
                ),
                "start_date": date,
                "end_date": date,
                "timezone": "auto",
            },
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        hourly = resp.json().get("hourly") or {}
    except (requests.RequestException, ValueError):
        return None

    times = hourly.get("time") or []
    idx = _hour_index(times, start_iso)
    if idx is None:
        return None

    def at(key):
        values = hourly.get(key) or []
        return values[idx] if idx < len(values) else None

    return {
        "temperature_c": at("temperature_2m"),
        "apparent_temperature_c": at("apparent_temperature"),
        "humidity": at("relative_humidity_2m"),
        "precipitation_probability": at("precipitation_probability"),
        "weather_code": at("weather_code"),
        "wind_speed_kmh": at("wind_speed_10m"),
    }


def get_event_weather(event):
    """Resolve the forecast for a single event.

    Returns a formatted weather dict, or ``None`` if the event has no usable
    location or any lookup fails (the briefing then skips its weather).
    """
    location = event.get("location")
    geo = geocode(location)
    if not geo:
        return None

    forecast = fetch_forecast(geo["latitude"], geo["longitude"], event.get("start") or "")
    if not forecast:
        return None

    is_us = geo.get("country_code") == "US"
    return {
        "location_name": geo.get("name"),
        "country": geo.get("country"),
        "is_us": is_us,
        "temperature": format_temp(forecast.get("temperature_c"), is_us),
        "feels_like": format_temp(forecast.get("apparent_temperature_c"), is_us),
        "humidity": forecast.get("humidity"),
        "precipitation_probability": forecast.get("precipitation_probability"),
        "wind_speed_kmh": forecast.get("wind_speed_kmh"),
        "conditions": describe_weather_code(forecast.get("weather_code")),
    }
