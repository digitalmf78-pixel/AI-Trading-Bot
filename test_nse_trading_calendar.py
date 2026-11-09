from datetime import date

import pytest

from nse_trading_calendar import (
    CalendarCoverageError,
    is_trading_session,
    session_status,
)


def test_regular_weekday_is_a_trading_session():
    assert session_status(date(2026, 11, 9)) == "REGULAR_SESSION"
    assert is_trading_session(date(2026, 11, 9))


def test_weekend_without_special_notice_is_closed():
    assert session_status(date(2026, 11, 7)) == "CLOSED_WEEKEND"
    assert not is_trading_session(date(2026, 11, 7))


def test_official_weekday_holiday_is_not_a_trading_session():
    assert session_status(date(2026, 11, 10)) == "HOLIDAY"
    assert not is_trading_session(date(2026, 11, 10))


def test_muhurat_sunday_overrides_weekend_and_holiday():
    assert session_status(date(2026, 11, 8)) == "SPECIAL_SESSION"
    assert is_trading_session(date(2026, 11, 8))


def test_2025_muhurat_session_is_included():
    assert is_trading_session(date(2025, 10, 21))


def test_unknown_year_fails_closed():
    with pytest.raises(CalendarCoverageError, match="not configured"):
        is_trading_session(date(2027, 1, 4))
