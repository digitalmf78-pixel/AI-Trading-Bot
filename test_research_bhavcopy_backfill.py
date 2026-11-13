from datetime import date
import io
import zipfile

import pandas as pd
import pytest

from scripts.research_bhavcopy_backfill import (
    expected_sessions, read_archive_csv, validate_bhavcopy,
)


def sample_frame(day="2026-11-13"):
    return pd.DataFrame({
        "BizDt": [day, day],
        "TckrSymb": ["ABC", "XYZ"],
        "SctySrs": ["EQ", "EQ"],
        "OpnPric": [100, 50],
        "HghPric": [110, 55],
        "LwPric": [95, 48],
        "ClsPric": [105, 52],
        "TtlTradgVol": [10000, 20000],
    })


def zipped(frame):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("BhavCopy_NSE_CM.csv", frame.to_csv(index=False))
    return payload.getvalue()


def test_expected_sessions_returns_exact_official_count():
    dates = expected_sessions(date(2026, 11, 13), 220)
    assert len(dates) == 220
    assert dates == sorted(set(dates))
    assert dates[-1] == date(2026, 11, 13)


def test_valid_internal_date_and_eq_rows_pass():
    validate_bhavcopy(sample_frame(), date(2026, 11, 13))


def test_internal_date_mismatch_rejected():
    with pytest.raises(ValueError, match="internal date mismatch"):
        validate_bhavcopy(sample_frame("2026-11-12"), date(2026, 11, 13))


def test_duplicate_eq_symbol_rejected():
    frame = sample_frame()
    frame.loc[1, "TckrSymb"] = "ABC"
    with pytest.raises(ValueError, match="duplicate EQ"):
        validate_bhavcopy(frame, date(2026, 11, 13))


def test_bad_ohlc_rejected():
    frame = sample_frame()
    frame.loc[0, "HghPric"] = 90
    with pytest.raises(ValueError, match="OHLC"):
        validate_bhavcopy(frame, date(2026, 11, 13))


def test_missing_required_column_rejected():
    frame = sample_frame().drop(columns=["TtlTradgVol"])
    with pytest.raises(ValueError, match="missing required"):
        validate_bhavcopy(frame, date(2026, 11, 13))


def test_valid_nse_zip_decodes_and_checks():
    frame = read_archive_csv(zipped(sample_frame()), date(2026, 11, 13))
    assert len(frame) == 2


def test_non_zip_response_rejected():
    with pytest.raises(ValueError, match="valid ZIP"):
        read_archive_csv(b"not a zip", date(2026, 11, 13))
