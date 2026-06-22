"""Tests for the calendar reader's graceful handling of the schedule file."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import calendar_reader  # noqa: E402


def test_loads_valid_events(tmp_path):
    path = tmp_path / "calendar.json"
    path.write_text(
        json.dumps(
            [
                {
                    "title": "Morning Gym",
                    "start": "2026-06-27T10:00:00",
                    "end": "2026-06-27T12:00:00",
                    "location": "Life Time Gym - Champions, Houston",
                }
            ]
        )
    )
    events = calendar_reader.load_events(str(path))
    assert len(events) == 1
    assert events[0]["title"] == "Morning Gym"
    assert events[0]["location"] == "Life Time Gym - Champions, Houston"


def test_missing_file_returns_empty():
    assert calendar_reader.load_events("/no/such/calendar.json") == []


def test_invalid_json_returns_empty(tmp_path):
    path = tmp_path / "calendar.json"
    path.write_text("{not valid json")
    assert calendar_reader.load_events(str(path)) == []


def test_non_list_top_level_returns_empty(tmp_path):
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({"title": "oops"}))
    assert calendar_reader.load_events(str(path)) == []


def test_empty_array_returns_empty(tmp_path):
    path = tmp_path / "calendar.json"
    path.write_text("[]")
    assert calendar_reader.load_events(str(path)) == []


def test_missing_optional_fields_become_none(tmp_path):
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps([{"title": "No location event"}]))
    events = calendar_reader.load_events(str(path))
    assert events == [
        {"title": "No location event", "start": None, "end": None, "location": None}
    ]


def test_non_dict_entries_are_skipped(tmp_path):
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps([{"title": "Real"}, "garbage", 42]))
    events = calendar_reader.load_events(str(path))
    assert len(events) == 1
    assert events[0]["title"] == "Real"
