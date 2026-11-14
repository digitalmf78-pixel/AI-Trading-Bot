from datetime import date
import pandas as pd
import pytest

from strategies.ecms.eod import calculate_rvol, _date_from_file

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
