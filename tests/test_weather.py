"""Tests for the Open-Meteo weather/geocoding layer.

Network calls are mocked so the suite is deterministic and offline.
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import weather  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_c_to_f():
    assert weather.c_to_f(0) == 32
    assert weather.c_to_f(100) == 212
    assert weather.c_to_f(27) == 81


def test_format_temp_us_is_fahrenheit_only():
    assert weather.format_temp(27, is_us=True) == "81°F"


def test_format_temp_non_us_shows_both():
    assert weather.format_temp(27, is_us=False) == "27°C / 81°F"


def test_format_temp_none():
    assert weather.format_temp(None, is_us=True) is None


def test_describe_weather_code():
    assert weather.describe_weather_code(0) == "clear sky"
    assert weather.describe_weather_code(2) == "partly cloudy"
    assert weather.describe_weather_code(12345) == "unknown conditions"


def test_geocode_falls_back_to_city(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params["name"])
        # The full gym string returns nothing; "Houston" resolves.
        if params["name"] == "Houston":
            return FakeResponse(
                {
                    "results": [
                        {
                            "latitude": 29.76,
                            "longitude": -95.36,
                            "name": "Houston",
                            "country": "United States",
                            "country_code": "US",
                        }
                    ]
                }
            )
        return FakeResponse({})

    monkeypatch.setattr(weather.requests, "get", fake_get)

    geo = weather.geocode("Life Time Gym - Champions, Houston")
    assert geo["name"] == "Houston"
    assert geo["country_code"] == "US"
    # It tried the full string before falling back to the city.
    assert calls[0] == "Life Time Gym - Champions, Houston"
    assert "Houston" in calls


def test_geocode_empty_location_returns_none():
    assert weather.geocode("") is None
    assert weather.geocode(None) is None


def test_geocode_network_error_returns_none(monkeypatch):
    def boom(*args, **kwargs):
        raise weather.requests.RequestException("down")

    monkeypatch.setattr(weather.requests, "get", boom)
    assert weather.geocode("Houston") is None


def test_get_event_weather_us(monkeypatch):
    geo = {
        "latitude": 29.76,
        "longitude": -95.36,
        "name": "Houston",
        "country": "United States",
        "country_code": "US",
    }
    forecast = {
        "temperature_c": 32.0,
        "apparent_temperature_c": 36.0,
        "humidity": 60,
        "precipitation_probability": 20,
        "weather_code": 2,
        "wind_speed_kmh": 10.0,
    }
    monkeypatch.setattr(weather, "geocode", lambda loc: geo)
    monkeypatch.setattr(weather, "fetch_forecast", lambda lat, lon, start: forecast)

    result = weather.get_event_weather(
        {"location": "Willowbrook Mall, Houston", "start": "2026-06-27T12:30:00"}
    )
    assert result["is_us"] is True
    assert result["temperature"] == "90°F"  # US -> Fahrenheit only
    assert result["conditions"] == "partly cloudy"
    assert result["humidity"] == 60


def test_get_event_weather_non_us_shows_both(monkeypatch):
    geo = {
        "latitude": 51.5,
        "longitude": -0.12,
        "name": "London",
        "country": "United Kingdom",
        "country_code": "GB",
    }
    forecast = {
        "temperature_c": 18.0,
        "apparent_temperature_c": 17.0,
        "humidity": 70,
        "precipitation_probability": 40,
        "weather_code": 3,
        "wind_speed_kmh": 15.0,
    }
    monkeypatch.setattr(weather, "geocode", lambda loc: geo)
    monkeypatch.setattr(weather, "fetch_forecast", lambda lat, lon, start: forecast)

    result = weather.get_event_weather(
        {"location": "Hyde Park, London", "start": "2026-06-27T09:00:00"}
    )
    assert result["is_us"] is False
    assert result["temperature"] == "18°C / 64°F"


def test_get_event_weather_skips_when_no_location(monkeypatch):
    monkeypatch.setattr(weather, "geocode", lambda loc: None)
    assert weather.get_event_weather({"location": "", "start": "2026-06-27T10:00:00"}) is None


def test_get_event_weather_skips_when_forecast_fails(monkeypatch):
    monkeypatch.setattr(weather, "geocode", lambda loc: {"latitude": 1, "longitude": 2,
                                                         "name": "X", "country_code": "US"})
    monkeypatch.setattr(weather, "fetch_forecast", lambda lat, lon, start: None)
    assert weather.get_event_weather({"location": "X", "start": "2026-06-27T10:00:00"}) is None


def test_fetch_forecast_picks_event_hour(monkeypatch):
    payload = {
        "hourly": {
            "time": ["2026-06-27T09:00", "2026-06-27T10:00", "2026-06-27T11:00"],
            "temperature_2m": [28.0, 30.0, 31.0],
            "apparent_temperature": [29.0, 33.0, 34.0],
            "relative_humidity_2m": [55, 60, 62],
            "precipitation_probability": [10, 20, 25],
            "weather_code": [1, 2, 3],
            "wind_speed_10m": [8.0, 10.0, 12.0],
        }
    }
    monkeypatch.setattr(
        weather.requests, "get", lambda url, params=None, timeout=None: FakeResponse(payload)
    )
    fc = weather.fetch_forecast(29.76, -95.36, "2026-06-27T10:00:00")
    # Picks the 10:00 index.
    assert fc["temperature_c"] == 30.0
    assert fc["humidity"] == 60
    assert fc["weather_code"] == 2


def test_fetch_forecast_network_error_returns_none(monkeypatch):
    def boom(*args, **kwargs):
        raise weather.requests.RequestException("down")

    monkeypatch.setattr(weather.requests, "get", boom)
    assert weather.fetch_forecast(1, 2, "2026-06-27T10:00:00") is None
