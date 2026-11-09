from datetime import date
import pandas as pd
import pytest

from delivery_filter import validate_delivery_report_date


def test_delivery_report_accepts_matching_date1_formats():
    frame = pd.DataFrame({"DATE1": ["09-Nov-2026", "09-Nov-2026"], "SYMBOL": ["AAA", "BBB"]})
    assert validate_delivery_report_date(frame, date(2026, 11, 9)) is frame


def test_delivery_report_rejects_previous_session_returned_for_requested_date():
    frame = pd.DataFrame({"DATE1": ["06-Nov-2026"], "SYMBOL": ["AAA"]})
    with pytest.raises(ValueError, match="do not match requested"):
        validate_delivery_report_date(frame, date(2026, 11, 9))


def test_delivery_report_rejects_mixed_internal_dates():
    frame = pd.DataFrame({"DATE1": ["09-Nov-2026", "06-Nov-2026"]})
    with pytest.raises(ValueError, match="do not match requested"):
        validate_delivery_report_date(frame, date(2026, 11, 9))


def test_delivery_report_rejects_missing_or_invalid_date1():
    with pytest.raises(ValueError, match="missing internal DATE1"):
        validate_delivery_report_date(pd.DataFrame({"SYMBOL": ["AAA"]}), date(2026, 11, 9))
    with pytest.raises(ValueError, match="unparseable"):
        validate_delivery_report_date(pd.DataFrame({"DATE1": ["-"]}), date(2026, 11, 9))
