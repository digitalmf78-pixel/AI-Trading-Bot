import csv
from datetime import date, timedelta

import pandas as pd

from signal_outcome_tracker import update_signal_outcomes
from nse_trading_calendar import is_trading_session


def test_outcomes_wait_until_each_horizon_is_complete_and_use_eod_close(tmp_path):
    log = tmp_path / "signal_log.csv"
    columns = ["EODDate", "TckrSymb", "ClsPric", "Result5D", "Result10D", "Result20D", "MFE", "MAE"]
    with log.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({"EODDate": "2026-11-11", "TckrSymb": "ABC", "ClsPric": "100"})
    frames = []
    day = date(2026, 11, 12)
    session_count = 0
    while session_count < 20:
        if is_trading_session(day):
            frames.append(pd.DataFrame([{
                "Date": pd.Timestamp(day), "TckrSymb": "ABC",
                "HghPric": 110.0, "LwPric": 95.0, "ClsPric": 105.0,
            }]))
            session_count += 1
        day += timedelta(days=1)
    store = tmp_path / "signal_outcomes.csv"
    result = update_signal_outcomes(log, frames, outcome_store_path=store)
    assert result["new_outcomes"] == 3
    with store.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert all(row["EntryReferenceType"] == "SIGNAL_EOD_CLOSE" for row in rows)
    assert all(row["FeesSlippageAssumption"] == "NOT_CONFIGURED" for row in rows)
    assert all(int(row["ObservedSessionCount"]) == int(row["HorizonSessions"]) for row in rows)
    with log.open(newline="", encoding="utf-8") as handle:
        enriched = next(csv.DictReader(handle))
    assert enriched["Result5D"] == "5.00000000"
    assert enriched["Result10D"] == "5.00000000"
    assert enriched["Result20D"] == "5.00000000"
    assert enriched["MFE"] == "10.00000000"
    assert enriched["MAE"] == "-5.00000000"
    assert update_signal_outcomes(log, frames, outcome_store_path=store)["new_outcomes"] == 0


def test_incomplete_horizon_is_not_written(tmp_path):
    log = tmp_path / "signal_log.csv"
    with log.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["EODDate", "TckrSymb", "ClsPric", "Result5D", "Result10D", "Result20D", "MFE", "MAE"])
        writer.writeheader()
        writer.writerow({"EODDate": "2026-11-11", "TckrSymb": "ABC", "ClsPric": "100"})
    frames = [pd.DataFrame([{"Date": pd.Timestamp("2026-11-12"), "TckrSymb": "ABC", "HghPric": 101, "LwPric": 99, "ClsPric": 100}])]
    store = tmp_path / "signal_outcomes.csv"
    result = update_signal_outcomes(log, frames, outcome_store_path=store)
    assert result["new_outcomes"] == 0
    assert not store.exists()
