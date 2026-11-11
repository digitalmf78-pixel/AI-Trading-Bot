import csv
from datetime import date, timedelta

import pandas as pd

from signal_outcome_tracker import update_signal_outcomes
from nse_trading_calendar import is_trading_session


def test_outcomes_wait_until_each_horizon_is_complete_and_use_next_session_open(tmp_path):
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
                "OpnPric": 102.0, "HghPric": 110.0, "LwPric": 95.0, "ClsPric": 105.0,
            }]))
            session_count += 1
        day += timedelta(days=1)
    store = tmp_path / "signal_outcomes.csv"
    result = update_signal_outcomes(log, frames, outcome_store_path=store)
    assert result["new_outcomes"] == 3
    with store.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert all(row["EntryReferenceType"] == "NEXT_SESSION_OPEN" for row in rows)
    assert all(float(row["EntryReference"]) == 102.0 for row in rows)
    assert all(row["FeesSlippageAssumption"] == "NOT_CONFIGURED" for row in rows)
    assert all(int(row["ObservedSessionCount"]) == int(row["HorizonSessions"]) for row in rows)
    with log.open(newline="", encoding="utf-8") as handle:
        enriched = next(csv.DictReader(handle))
    assert enriched["Result5D"] == "2.94117647"
    assert enriched["Result10D"] == "2.94117647"
    assert enriched["Result20D"] == "2.94117647"
    assert enriched["MFE"] == "7.84313725"
    assert enriched["MAE"] == "-6.86274510"
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

def test_missing_whole_market_bhavcopy_session_does_not_shift_horizon(tmp_path):
    log = tmp_path / "signal_log.csv"
    columns = ["EODDate", "TckrSymb", "ClsPric", "Result5D", "Result10D", "Result20D", "MFE", "MAE"]
    with log.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({"EODDate": "2026-11-11", "TckrSymb": "ABC", "ClsPric": "100"})

    frames = []
    day = date(2026, 11, 12)
    session_dates = []
    while len(session_dates) < 20:
        if is_trading_session(day):
            session_dates.append(day)
        day += timedelta(days=1)

    # Simulate a missing whole-market Bhavcopy for the first future session.
    for session_day in session_dates[1:]:
        frames.append(pd.DataFrame([{
            "Date": pd.Timestamp(session_day), "TckrSymb": "ABC",
            "OpnPric": 102.0, "HghPric": 110.0, "LwPric": 95.0, "ClsPric": 105.0,
        }]))

    store = tmp_path / "signal_outcomes.csv"
    result = update_signal_outcomes(log, frames, outcome_store_path=store)
    assert result["new_outcomes"] == 0
    assert not store.exists()
    with log.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["Result5D"] == ""
    assert row["Result10D"] == ""
    assert row["Result20D"] == ""


def test_signal_day_prices_are_excluded_and_entry_uses_next_session_open(tmp_path):
    log = tmp_path / "signal_log.csv"
    columns = ["EODDate", "TckrSymb", "ClsPric", "Result5D", "Result10D", "Result20D", "MFE", "MAE"]
    with log.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({"EODDate": "2026-11-06", "TckrSymb": "ABC", "ClsPric": "100"})
    # Signal-day extremes are deliberately enormous; they must never leak into
    # entry, MFE, MAE, or forward returns.
    frames = [pd.DataFrame([{
        "Date": pd.Timestamp("2026-11-06"), "TckrSymb": "ABC",
        "OpnPric": 100.0, "HghPric": 999.0, "LwPric": 1.0, "ClsPric": 100.0,
    }])]
    day = date(2026, 11, 7)
    while sum(
        1 for frame in frames
        if frame.iloc[0]["Date"].date() > date(2026, 11, 6)
        and is_trading_session(frame.iloc[0]["Date"])
    ) < 5:
        if is_trading_session(day):
            frames.append(pd.DataFrame([{
                "Date": pd.Timestamp(day), "TckrSymb": "ABC",
                "OpnPric": 100.0, "HghPric": 105.0, "LwPric": 98.0, "ClsPric": 104.0,
            }]))
        day += timedelta(days=1)
    store = tmp_path / "signal_outcomes.csv"
    update_signal_outcomes(log, frames, outcome_store_path=store)
    with store.open(newline="", encoding="utf-8") as handle:
        first = next(csv.DictReader(handle))
    assert first["EntryReferenceType"] == "NEXT_SESSION_OPEN"
    assert float(first["EntryReference"]) == 100.0
    assert float(first["MFE_Pct"]) == 5.0
    assert float(first["MAE_Pct"]) == -2.0


def test_official_special_session_counts_but_holiday_does_not(tmp_path):
    log = tmp_path / "signal_log.csv"
    columns = ["EODDate", "TckrSymb", "ClsPric", "Result5D", "Result10D", "Result20D", "MFE", "MAE"]
    with log.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({"EODDate": "2026-11-06", "TckrSymb": "ABC", "ClsPric": "100"})
    # 08-Nov-2026 is an official Muhurat session despite being Sunday; 10-Nov
    # is an NSE holiday and must not consume a horizon session.
    expected = []
    day = date(2026, 11, 7)
    while len(expected) < 5:
        if is_trading_session(day):
            expected.append(day)
        day += timedelta(days=1)
    assert expected == [
        date(2026, 11, 8), date(2026, 11, 9), date(2026, 11, 11),
        date(2026, 11, 12), date(2026, 11, 13),
    ]
    frames = [pd.DataFrame([{
        "Date": pd.Timestamp(session_day), "TckrSymb": "ABC",
        "OpnPric": 100.0, "HghPric": 103.0, "LwPric": 99.0, "ClsPric": 102.0,
    }]) for session_day in expected]
    store = tmp_path / "signal_outcomes.csv"
    update_signal_outcomes(log, frames, outcome_store_path=store)
    with store.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["HorizonEndDate"] == "2026-11-13"
    assert row["ObservedSessionCount"] == "5"
    assert row["EntryReferenceType"] == "NEXT_SESSION_OPEN"
