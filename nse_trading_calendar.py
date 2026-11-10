"""Single source of truth for NSE Capital Market (Equities) trading sessions.

Calendar dates are transcribed from official NSE Capital Market holiday notices.
Special sessions override holiday/weekend closure (e.g. Muhurat Trading).
Unknown calendar years fail closed: callers must not infer a trading session.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

CALENDAR_PATH = Path(__file__).resolve().parent / "data" / "inputs" / "nse_trading_calendar.json"


class CalendarCoverageError(RuntimeError):
    """Raised when the official NSE calendar for a date's year is not configured."""


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    # pandas.Timestamp and ISO strings are accepted without importing pandas.
    return date.fromisoformat(str(value)[:10])


def _load_calendar() -> dict:
    try:
        payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalendarCoverageError(f"Official NSE calendar unavailable: {exc}") from exc
    if payload.get("segment") != "Capital Market - Equities":
        raise CalendarCoverageError("Calendar segment mismatch; expected Capital Market - Equities")
    return payload


def session_status(value: Any) -> str:
    """Return SPECIAL_SESSION, REGULAR_SESSION, HOLIDAY, CLOSED_WEEKEND or UNKNOWN_YEAR."""
    day = _as_date(value)
    payload = _load_calendar()
    year_data = payload.get("years", {}).get(str(day.year))
    if not isinstance(year_data, dict):
        raise CalendarCoverageError(
            f"WAIT_FOR_DATA: official NSE calendar not configured for {day.year}"
        )
    token = day.isoformat()
    special = year_data.get("special_sessions", {})
    if token in special:
        return "SPECIAL_SESSION"
    if token in set(year_data.get("holidays", [])):
        return "HOLIDAY"
    if day.weekday() >= 5:
        return "CLOSED_WEEKEND"
    return "REGULAR_SESSION"


def is_trading_session(value: Any) -> bool:
    """True only for a regular NSE equity session or an officially listed special session."""
    return session_status(value) in {"REGULAR_SESSION", "SPECIAL_SESSION"}


def official_session_reason(value: Any) -> str:
    """Human-readable official-calendar reason for diagnostics."""
    day = _as_date(value)
    status = session_status(day)
    if status == "SPECIAL_SESSION":
        payload = _load_calendar()
        return str(payload["years"][str(day.year)]["special_sessions"][day.isoformat()])
    return status


def calendar_coverage_warnings(today: Any | None = None) -> list[str]:
    """Non-fatal warnings when the official calendar is about to expire.

    The scanner already fails closed (WAIT_FOR_DATA) when a year is missing.
    This helper makes the expiry visible in logs at least 60 days in advance
    instead of only failing on the first scan of the new year.
    """
    day = _as_date(today) if today is not None else date.today()
    try:
        payload = _load_calendar()
    except CalendarCoverageError as exc:
        return [str(exc)]

    years = payload.get("years", {})
    warnings: list[str] = []
    current_year = str(day.year)
    next_year = str(day.year + 1)

    if current_year not in years:
        warnings.append(
            f"[CALENDAR][ERROR] official NSE calendar not configured for {current_year}; "
            "scanning will fail closed with WAIT_FOR_DATA."
        )
    elif day.month >= 11 and next_year not in years:
        warnings.append(
            f"[CALENDAR][WARN] official NSE calendar for {next_year} is missing. "
            "Runs after 31-Dec will fail closed until the official NSE holiday list "
            "is added (60-day rule)."
        )
    return warnings
