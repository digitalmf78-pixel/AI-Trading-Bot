from datetime import date
import pandas as pd
import pytest

from strategies.ecms.eod import (calculate_rvol, _date_from_file, _equity_rows,\n                                 expected_latest_completed_session)

def _frame(symbols, volumes):
    return pd.DataFrame({
        "TckrSymb": symbols, "SctySrs": ["EQ"] * len(symbols),
        "TtlTradgVol": volumes, "ClsPric": [100] * len(symbols),
        "BizDt": ["2026-11-13"] * len(symbols),
    })

def test_rvol_uses_twenty_prior_sessions_and_passes_threshold():
    current = _frame(["AAA", "BBB"], [1500, 1499])
    history = [_frame(["AAA", "BBB"], [1000, 1000]) for _ in range(20)]
    result = calculate_rvol(current, history).set_index("TckrSymb")
    assert result.loc["AAA", "RVOL"] == 1.5
    assert result.loc["AAA", "VolumeScreenStatus"] == "PASS_RVOL_GE_1_5"
    assert result.loc["BBB", "VolumeScreenStatus"] == "BELOW_RVOL_THRESHOLD"

def test_rvol_missing_symbol_baseline_waits_not_passes():
    current = _frame(["AAA"], [5000])
    history = [_frame(["BBB"], [1000]) for _ in range(20)]
    result = calculate_rvol(current, history)
    assert pd.isna(result.loc[0, "RVOL"])
    assert result.loc[0, "VolumeScreenStatus"] == "WAIT_FOR_DATA"

def test_rvol_requires_full_twenty_sessions():
    with pytest.raises(ValueError, match="Need 20 historical sessions"):
        calculate_rvol(_frame(["AAA"], [100]), [_frame(["AAA"], [50])])

def test_filename_date_parser_is_strict():
    from pathlib import Path
    assert _date_from_file(Path("bhavcopy_20261113.csv")) == date(2026, 11, 13)
    assert _date_from_file(Path("bhavcopy_latest.csv")) is None

def test_equity_rows_keeps_supported_listed_equity_series_and_excludes_etfs():
    frame = pd.DataFrame({
        "TckrSymb": ["AAA", "BBB", "FUND"],
        "SctySrs": ["EQ", "BE", "EQ"],
        "TtlTradgVol": [1000, 2000, 3000],
        "ClsPric": [100, 200, 10],
        "ISIN": ["INE000A01001", "INE000B01001", "INF000000001"],
        "FinInstrmNm": ["AAA LTD", "BBB LTD", "AMC - FUND"],
    })
    result = _equity_rows(frame)
    assert set(result["TckrSymb"]) == {"AAA", "BBB"}

def test_expected_latest_completed_session_uses_ist_market_close():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    assert expected_latest_completed_session(datetime(2026, 11, 13, 15, 0, tzinfo=ist)) == date(2026, 11, 12)
    assert expected_latest_completed_session(datetime(2026, 11, 13, 17, 0, tzinfo=ist)) == date(2026, 11, 13)
    assert expected_latest_completed_session(datetime(2026, 11, 14, 10, 0, tzinfo=ist)) == date(2026, 11, 13)
