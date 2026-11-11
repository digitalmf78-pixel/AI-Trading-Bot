"""Tests for append-only EOD signal logging."""
import csv

import pandas as pd

from signal_log import SIGNAL_LOG_COLUMNS, append_signal_log


def _rows():
    return pd.DataFrame([
        {"TckrSymb": "abc", "EODWatchlistStatus": "WATCH", "DeliveryCategoryAStatus": "PASS_AVG_GE_60_PERCENT", "DeliveryCategoryBStatus": "PASS_EACH_DAY_GE_60_PERCENT", "LiquidityTier": "STRONG", "RVOL": 1.8, "SetupType": "Breakout", "TrendClassification": "Bullish", "V8Score": 82, "EntryZoneLow": 100, "EntryZoneHigh": 102, "EntryPricePlan": 102, "StopLossPlan": 96, "TargetPricePlan": 114, "RiskReward": 2.0, "SectorStrengthStatus": "PASS", "MarketRegimeStatus": "PASS", "ClsPric": 101},
        {"TckrSymb": "xyz", "EODWatchlistStatus": "WAIT_FOR_DATA", "RVOL": float("nan"), "V8Score": float("nan"), "EntryZoneLow": float("nan"), "StopLossPlan": float("nan"), "ClsPric": float("nan")},
    ])


def test_signal_log_append_no_duplicate_and_blank_handling(tmp_path):
    path = tmp_path / "outputs" / "signal_log.csv"
    rows = _rows()
    assert append_signal_log(rows, "2026-11-11", path) == 2
    # Same date/symbol keys are not appended a second time, even on rerun.
    assert append_signal_log(rows, "2026-11-11", path) == 0
    # A new symbol on the same date is appended, while existing rows stay intact.
    assert append_signal_log(pd.DataFrame([{"TckrSymb": "NEW", "EODWatchlistStatus": "SKIP"}]), "2026-11-11", path) == 1
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        saved = list(reader)
        assert reader.fieldnames == SIGNAL_LOG_COLUMNS
    assert len(saved) == 3
    assert saved[0]["TckrSymb"] == "ABC" and saved[0]["EODWatchlistStatus"] == "WATCH"
    assert saved[1]["TckrSymb"] == "XYZ" and saved[1]["EODWatchlistStatus"] == "WAIT_FOR_DATA"
    assert saved[1]["RVOL"] == "" and saved[1]["V8Score"] == "" and saved[1]["ClsPric"] == ""
    assert saved[1]["Result5D"] == saved[1]["Result10D"] == saved[1]["Result20D"] == ""
    assert saved[1]["MFE"] == saved[1]["MAE"] == ""


def test_signal_log_preserves_existing_rows_and_writes_header_once(tmp_path):
    path = tmp_path / "signal_log.csv"
    assert append_signal_log(_rows().iloc[:1], "2026-11-10", path) == 1
    original = path.read_text(encoding="utf-8")
    assert append_signal_log(_rows().iloc[:1], "2026-11-11", path) == 1
    contents = path.read_text(encoding="utf-8")
    assert contents.startswith(original)
    assert contents.count("EODDate,") == 1


def test_signal_log_creates_header_when_watchlist_is_empty(tmp_path):
    path = tmp_path / "empty" / "signal_log.csv"
    assert append_signal_log(pd.DataFrame(), "2026-11-11", path) == 0
    with path.open("r", newline="", encoding="utf-8") as handle:
        assert next(csv.reader(handle)) == SIGNAL_LOG_COLUMNS
