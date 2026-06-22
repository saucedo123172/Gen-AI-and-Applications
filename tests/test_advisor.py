"""Tests for the advice engine's context building and briefing generation.

The Claude client is faked so no real API call is made.
"""

import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import advisor  # noqa: E402


class FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeMessages:
    def __init__(self, reply):
        self._reply = reply
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return types.SimpleNamespace(content=[FakeTextBlock(self._reply)])


class FakeClient:
    def __init__(self, reply):
        self.messages = FakeMessages(reply)


def _event(title, start, end, location):
    return {"title": title, "start": start, "end": end, "location": location}


def test_build_context_empty_calendar():
    context = advisor.build_context([])
    assert "no events" in context.lower()


def test_build_context_includes_event_and_weather():
    event = _event("Morning Gym", "2026-06-27T10:00:00", "2026-06-27T12:00:00",
                   "Life Time Gym - Champions, Houston")
    weather = {
        "conditions": "partly cloudy",
        "temperature": "90°F",
        "feels_like": "97°F",
        "humidity": 60,
        "precipitation_probability": 20,
        "wind_speed_kmh": 10.0,
    }
    context = advisor.build_context([(event, weather)])
    assert "Morning Gym" in context
    assert "10:00–12:00" in context
    assert "partly cloudy" in context
    assert "90°F" in context
    assert "humidity 60%" in context


def test_build_context_marks_unavailable_weather():
    event = _event("Mystery", "2026-06-27T10:00:00", "2026-06-27T11:00:00", None)
    context = advisor.build_context([(event, None)])
    assert "unavailable" in context.lower()


def test_generate_briefing_returns_text_and_uses_config():
    client = FakeClient("Good morning! Your day looks clear.")
    event = _event("Morning Gym", "2026-06-27T10:00:00", "2026-06-27T12:00:00", "Houston")
    weather = {
        "conditions": "clear sky",
        "temperature": "85°F",
        "feels_like": "88°F",
        "humidity": 50,
        "precipitation_probability": 0,
        "wind_speed_kmh": 5.0,
    }

    briefing = advisor.generate_briefing([(event, weather)], client=client)

    assert briefing == "Good morning! Your day looks clear."
    kwargs = client.messages.last_kwargs
    assert kwargs["model"] == advisor.config.ANTHROPIC_MODEL
    assert kwargs["system"] == advisor.config.SYSTEM_PROMPT
    assert kwargs["messages"][0]["role"] == "user"
    assert "Morning Gym" in kwargs["messages"][0]["content"]


def test_generate_briefing_empty_calendar_path():
    client = FakeClient("Your calendar is clear today. Stay hydrated!")
    briefing = advisor.generate_briefing([], client=client)
    assert "clear" in briefing.lower()
    assert "no events" in client.messages.last_kwargs["messages"][0]["content"].lower()
