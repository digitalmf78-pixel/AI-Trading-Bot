"""CI test: NSE trading calendar must cover current and next year.

Fails if the calendar does not cover:
- The current year (always required)
- The next year (required after 1 November)
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

CALENDAR_PATH = Path("data") / "inputs" / "nse_trading_calendar.json"


def _load_calendar() -> dict:
    return json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))


def test_calendar_file_exists():
    assert CALENDAR_PATH.exists(), "NSE trading calendar file is missing"


def test_calendar_covers_current_year():
    cal = _load_calendar()
    current_year = str(date.today().year)
    assert current_year in cal.get("years", {}), (
        f"NSE trading calendar does not cover current year {current_year}. "
        f"Available years: {list(cal.get('years', {}).keys())}"
    )


def test_calendar_covers_next_year_after_november():
    """After 1 November, the next year's calendar must be present."""
    today = date.today()
    if today.month >= 11:
        cal = _load_calendar()
        next_year = str(today.year + 1)
        assert next_year in cal.get("years", {}), (
            f"NSE trading calendar does not cover next year {next_year} "
            f"(required after 1 November). "
            f"Available years: {list(cal.get('years', {}).keys())}"
        )


def test_calendar_has_holidays_for_each_year():
    cal = _load_calendar()
    for year, data in cal.get("years", {}).items():
        holidays = data.get("holidays", [])
        assert isinstance(holidays, list), f"Year {year} holidays is not a list"
        assert len(holidays) >= 10, f"Year {year} has only {len(holidays)} holidays (expected >= 10)"


def test_calendar_holidays_are_valid_dates():
    cal = _load_calendar()
    for year, data in cal.get("years", {}).items():
        for h in data.get("holidays", []):
            try:
                date.fromisoformat(h)
            except ValueError:
                pytest.fail(f"Invalid holiday date in year {year}: {h}")


def test_calendar_special_sessions_are_valid_dates():
    cal = _load_calendar()
    for year, data in cal.get("years", {}).items():
        special = data.get("special_sessions", {})
        if special:
            for d in special:
                try:
                    date.fromisoformat(d)
                except ValueError:
                    pytest.fail(f"Invalid special session date in year {year}: {d}")
