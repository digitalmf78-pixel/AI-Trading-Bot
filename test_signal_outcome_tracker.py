import csv
from datetime import date, timedelta

import pandas as pd

from signal_outcome_tracker import OUTCOME_COLUMNS, update_signal_outcomes


def test_outcomes_wait_until_each_horizon_is_complete_and_use_eod_close(tmp_path):
    log = tmp_path / "signal_log.csv"
    columns = ["EODDate", "TckrSymb", "ClsPric", "Result5D", "Result10D", "Result20D", "MFE", "MAE"]
    with log.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({"EODDate": "2026-01-01", "TckrSymb": "ABC", "ClsPric": "100"})
    frames = []
    start = date(2026, 1, 2)
    for i in range(20):
        day = start + timedelta(days=i)
        if day.weekday() >= 5:
            continue
        frames.append(pd.DataFrame([{
            "Date": pd.Timestamp(day), "TckrSymb": "ABC",
            "HghPric": 110.0, "LwPric": 95.0, "ClsPric": 105.0,
        }]))
    store = tmp_path / "signal_outcomes.csv"
    result = update_signal_outcomes(log, frames, outcome_store_path=store)
    assert result["new_outcomes"] == 3
    with store.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert all(row["EntryReferenceType"] == "SIGNAL_EOD_CLOSE" for row in rows)
    assert all(row["FeesSlippageAssumption"] == "NOT_CONFIGURED" for row in rows)
    assert all(int(row["ObservedSessionCount"]) == int(row["HorizonSessions"]) for row in rows)


def test_incomplete_horizon_is_not_written(tmp_path):
    log = tmp_path / "signal_log.csv"
    with log.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["EODDate", "TckrSymb", "ClsPric", "Result5D", "Result10D", "Result20D", "MFE", "MAE"])
        writer.writeheader()
        writer.writerow({"EODDate": "2026-01-01", "TckrSymb": "ABC", "ClsPric": "100"})
    frames = [pd.DataFrame([{"Date": pd.Timestamp("2026-01-02"), "TckrSymb": "ABC", "HghPric": 101, "LwPric": 99, "ClsPric": 100}])]
    store = tmp_path / "signal_outcomes.csv"
    result = update_signal_outcomes(log, frames, outcome_store_path=store)
    assert result["new_outcomes"] == 0
    assert not store.exists()
