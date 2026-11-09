import pandas as pd
import pytest

from volume_gainer import validate_bhavcopy_date


def test_validate_bhavcopy_date_accepts_matching_business_date():
    frame = pd.DataFrame({
        "BizDt": ["2026-11-06", "2026-11-06"],
        "TckrSymb": ["AAA", "BBB"],
    })
    assert validate_bhavcopy_date(frame, pd.Timestamp("2026-11-06").date()) is frame


def test_validate_bhavcopy_date_rejects_wrong_business_date():
    frame = pd.DataFrame({"BizDt": ["2026-11-07"], "TckrSymb": ["AAA"]})
    with pytest.raises(ValueError, match="does not match"):
        validate_bhavcopy_date(frame, pd.Timestamp("2026-11-06").date())


def test_validate_bhavcopy_date_rejects_mixed_business_dates():
    frame = pd.DataFrame({"BizDt": ["2026-11-06", "2026-11-07"]})
    with pytest.raises(ValueError, match="does not match"):
        validate_bhavcopy_date(frame, pd.Timestamp("2026-11-06").date())


def test_validate_bhavcopy_date_fails_closed_without_date_column():
    frame = pd.DataFrame({"TckrSymb": ["AAA"]})
    with pytest.raises(ValueError, match="no recognized internal date column"):
        validate_bhavcopy_date(frame, pd.Timestamp("2026-11-06").date())


def test_validate_bhavcopy_date_rejects_empty_file():
    with pytest.raises(ValueError, match="empty Bhavcopy"):
        validate_bhavcopy_date(pd.DataFrame(), pd.Timestamp("2026-11-06").date())


def test_validate_bhavcopy_date_rejects_official_nse_holiday_even_when_file_date_matches():
    frame = pd.DataFrame({"BizDt": ["2026-11-10"], "TckrSymb": ["AAA"]})
    with pytest.raises(ValueError, match="not an official NSE equity trading session"):
        validate_bhavcopy_date(frame, pd.Timestamp("2026-11-10").date())


def test_validate_bhavcopy_date_accepts_sunday_muhurat_special_session():
    frame = pd.DataFrame({"BizDt": ["2026-11-08"], "TckrSymb": ["AAA"]})
    assert validate_bhavcopy_date(frame, pd.Timestamp("2026-11-08").date()) is frame
