import pandas as pd

from volume_gainer import (
    calculate_average_volume,
    calculate_rvol,
    classify_rvol_for_delivery_candidates,
)


def _sessions(count=20):
    frames = []
    dates = pd.bdate_range(end="2026-10-23", periods=count)
    for date in dates:
        frames.append(pd.DataFrame([{
            "TckrSymb": "AAA", "TtlTradgVol": 1000.0, "Date": date,
        }]))
    return frames


def test_average_volume_requires_twenty_distinct_prior_sessions():
    result = calculate_average_volume(_sessions(20))
    row = result[result["TckrSymb"] == "AAA"].iloc[0]
    assert row["AvgVolume20D"] == 1000.0
    assert row["AvgVolumeSessions"] == 20
    assert calculate_average_volume(_sessions(19)).empty


def test_duplicate_session_dates_do_not_count_as_twenty_sessions():
    history = _sessions(20)
    history[-1]["Date"] = history[-2]["Date"]
    assert calculate_average_volume(history).empty


def test_duplicate_symbol_rows_in_one_session_are_ambiguous_wait():
    history = _sessions(20)
    history[7] = pd.DataFrame([
        {"TckrSymb": "AAA", "TtlTradgVol": 1000.0, "Date": history[7]["Date"].iloc[0]},
        {"TckrSymb": "AAA", "TtlTradgVol": 9000.0, "Date": history[7]["Date"].iloc[0]},
    ])
    result = calculate_average_volume(history)
    row = result[result["TckrSymb"] == "AAA"].iloc[0]
    assert row["AvgVolumeSessions"] == 19
    assert pd.isna(row["AvgVolume20D"])


def test_missing_symbol_session_does_not_backfill_an_older_volume_row():
    history = _sessions(20)
    missing_date = history[7]["Date"].iloc[0]
    history[7] = pd.DataFrame([{
        "TckrSymb": "OTHER", "TtlTradgVol": 500.0, "Date": missing_date,
    }])
    result = calculate_average_volume(history)
    row = result[result["TckrSymb"] == "AAA"].iloc[0]
    assert row["AvgVolumeSessions"] == 19
    assert pd.isna(row["AvgVolume20D"])


def test_rvol_uses_verified_baseline_and_rejects_invalid_current_volume():
    current = pd.DataFrame([{
        "TckrSymb": "AAA", "TtlTradgVol": 1500.0,
        "AvgVolume20D": 999.0, "AvgVolumeSessions": 10,
    }])
    baseline = pd.DataFrame([{
        "TckrSymb": "AAA", "AvgVolume20D": 1000.0, "AvgVolumeSessions": 20,
    }])
    result = calculate_rvol(current, baseline)
    assert result.iloc[0]["RVOL"] == 1.5
    assert result.iloc[0]["RVOLStatus"] == "PASS"

    current.loc[0, "TtlTradgVol"] = -1
    invalid = calculate_rvol(current, baseline)
    assert invalid.iloc[0]["RVOLStatus"] == "WAIT_FOR_DATA"


def test_rvol_requires_complete_twenty_session_baseline():
    current = pd.DataFrame([{"TckrSymb": "AAA", "TtlTradgVol": 1500.0}])
    baseline = pd.DataFrame([{
        "TckrSymb": "AAA", "AvgVolume20D": 1000.0, "AvgVolumeSessions": 19,
    }])
    result = calculate_rvol(current, baseline)
    assert result.iloc[0]["RVOLStatus"] == "WAIT_FOR_DATA"


def test_rvol_threshold_is_strictly_greater_than_1_5_and_never_rejects_delivery_rows():
    current = pd.DataFrame([
        {"TckrSymb": "AAA", "RVOL": 1.5, "RVOLStatus": "PASS"},
        {"TckrSymb": "BBB", "RVOL": 1.5001, "RVOLStatus": "PASS"},
        {"TckrSymb": "CCC", "RVOL": float("nan"), "RVOLStatus": "WAIT_FOR_DATA"},
    ])
    result = classify_rvol_for_delivery_candidates(current, "2026-10-23").set_index("TckrSymb")
    assert result.loc["AAA", "RVOLBand"] == "LOW_RVOL_LE_1_5"
    assert result.loc["BBB", "RVOLBand"] == "HIGH_RVOL_GT_1_5"
    assert result.loc["CCC", "RVOLBand"] == "WAIT_FOR_DATA"
    assert len(result) == 3
