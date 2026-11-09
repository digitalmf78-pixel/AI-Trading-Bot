from datetime import date, timedelta
import pandas as pd

from vcp_observation_analysis import build_vcp_observation_report


def _history():
    dates = pd.bdate_range(end="2026-10-22", periods=60)
    highs, lows, volumes, closes = [], [], [], []
    for block in range(3):
        if block == 0:
            high, low, volume = 120.0, 100.0, 1000.0
        elif block == 1:
            high, low, volume = 115.0, 105.0, 700.0
        else:
            high, low, volume = 112.0, 108.0, 300.0
        for _ in range(20):
            highs.append(high)
            lows.append(low)
            volumes.append(volume)
            closes.append((high + low) / 2)
    return pd.DataFrame({
        "TckrSymb": "AAA", "SctySrs": "EQ", "Date": dates,
        "HghPric": highs, "LwPric": lows, "ClsPric": closes,
        "TtlTradgVol": volumes,
    })


def test_three_block_contraction_and_volume_dryup_are_observational_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = build_vcp_observation_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 110,
                       "HghPric": 112, "LwPric": 108, "TtlTradgVol": 300}]),
        [_history()], "2026-10-23"
    )
    row = report.iloc[0]
    assert row["VCPObservationStatus"] == "COMPLETE"
    assert row["ContractionTransitionsObserved"] == 2
    assert row["ContractionSequenceObservation"] == "TWO_CONTRACTION_STEPS_OBSERVED"
    assert row["RangeContractionRatio2vs1"] < 1
    assert row["RangeContractionRatio3vs2"] < 1
    assert row["VolumeDryUpRatio3vs2"] < 0.5
    assert row["VolumeDryUpFlag"] == "OBSERVATIONAL_BELOW_0_5X"
    assert row["VCPStatus"] == "NOT_CLASSIFIED"
    assert (tmp_path / "outputs/v8_vcp_contraction_observations_20261023.csv").exists()


def test_missing_symbol_session_waits_without_reaching_back(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    history = _history()
    missing_date = history.iloc[-8]["Date"]
    symbol_history = history[history["Date"] != missing_date].copy()
    market_calendar = history.copy()
    market_calendar["TckrSymb"] = "OTHER"
    report = build_vcp_observation_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 110,
                       "HghPric": 112, "LwPric": 108, "TtlTradgVol": 300}]),
        [symbol_history, market_calendar], "2026-10-23"
    )
    assert len(report) == 1
    assert report.iloc[0]["VCPRangeObservationStatus"] == "WAIT_FOR_DATA"
    assert report.iloc[0]["VCPObservationStatus"] == "WAIT_FOR_DATA"
    assert report.iloc[0]["VCPStatus"] == "WAIT_FOR_DATA"


def test_future_history_rows_are_excluded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    history = _history()
    future = history.iloc[[-1]].copy()
    future["Date"] = pd.Timestamp("2026-10-26")
    future["HghPric"] = 999999
    history = pd.concat([history, future], ignore_index=True)
    report = build_vcp_observation_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 110,
                       "HghPric": 112, "LwPric": 108, "TtlTradgVol": 300}]),
        [history], "2026-10-23"
    )
    assert report.iloc[0]["RangeWidthBlock3Pct"] < 999999



def test_duplicate_symbol_session_rows_wait_instead_of_last_row_wins(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    history = _history()
    duplicate = history.iloc[[-5]].copy()
    history = pd.concat([history, duplicate], ignore_index=True)
    report = build_vcp_observation_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 110,
                       "HghPric": 112, "LwPric": 108, "TtlTradgVol": 300}]),
        [history], "2026-10-23"
    )
    row = report.iloc[0]
    assert row["VCPRangeObservationStatus"] == "WAIT_FOR_DATA"
    assert row["VCPObservationStatus"] == "WAIT_FOR_DATA"
    assert row["VCPStatus"] == "WAIT_FOR_DATA"


def test_missing_volume_in_one_session_is_partial_not_a_full_vcp_observation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    history = _history()
    history.loc[history.index[-5], "TtlTradgVol"] = float("nan")
    report = build_vcp_observation_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 110,
                       "HghPric": 112, "LwPric": 108, "TtlTradgVol": 300}]),
        [history], "2026-10-23"
    )
    row = report.iloc[0]
    assert row["VCPRangeObservationStatus"] == "COMPLETE"
    assert row["VCPVolumeObservationStatus"] == "WAIT_FOR_DATA"
    assert row["VCPObservationStatus"] == "PARTIAL_DATA"
