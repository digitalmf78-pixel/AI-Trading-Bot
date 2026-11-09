from datetime import date, timedelta
import pandas as pd

from potential_accumulation_analysis import build_potential_accumulation_report


def _history(symbol="AAA", periods=60):
    dates = pd.bdate_range("2026-08-01", periods=periods)
    lows = [100.0 + (i % 5) for i in range(periods)]
    highs = [v + 4 for v in lows]
    closes = [v + 2 for v in lows]
    volumes = [1000 + i * 10 for i in range(periods)]
    return pd.DataFrame({
        "TckrSymb": symbol, "Date": dates, "OpnPric": [value - 1 for value in closes],
        "HghPric": highs, "LwPric": lows, "ClsPric": closes,
        "TtlTradgVol": volumes,
    })


def _delivery_sessions(count=6):
    calendar = [date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 19),
                date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]
    dates = calendar[:count]
    sessions = []
    for i, day in enumerate(dates):
        pct = 60.0 if i % 2 == 0 else 55.0
        sessions.append((day, pd.DataFrame([{
            "SYMBOL": "AAA", "SERIES": "EQ", "DELIV_QTY": 500 + i * 10,
            "DELIV_PER": pct, "TTL_TRD_QNTY": 1000 + i * 20,
            "OPEN_PRICE": 110, "HIGH_PRICE": 112, "LOW_PRICE": 108,
            "CLOSE_PRICE": 111 + i, "PREV_CLOSE": 110 + i,
        }])))
    return sessions


def test_report_keeps_candidate_and_emits_20d_50d_200d_range_observations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidate = pd.DataFrame([{
        "TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 120,
        "OpnPric": 119, "HghPric": 122, "LwPric": 118,
        "TtlTradgVol": 2000, "DeliveryCategory": "A_ONLY",
        "RVOLBand": "LOW_RVOL_LE_1_5",
    }])
    report = build_potential_accumulation_report(
        candidate, [_history()], _delivery_sessions(), "2026-10-23"
    )
    row = report.iloc[0]
    assert row["TckrSymb"] == "AAA"
    assert row["PriceHistoryStatus"] == "COMPLETE_20D"
    assert row["PivotStructureStatus"] == "COMPLETE"
    assert row["PivotLowSeparationStatus"] == "OBSERVATION_AVAILABLE"
    assert pd.notna(row["PivotLowSeparationATR"])
    assert row["PriceRange20DStatus"] == "OBSERVATION_AVAILABLE"
    assert row["PriceRange50DStatus"] == "OBSERVATION_AVAILABLE"
    assert row["PriceRange200DStatus"] == "WAIT_FOR_DATA"
    assert row["DeliveryEvidenceStatus"] == "OBSERVATIONS_AVAILABLE"
    assert row["HighDeliverySessionCount"] == 3
    assert row["EvidenceStatus"] == "OBSERVATIONS_AVAILABLE"
    assert (tmp_path / "outputs/v8_potential_accumulation_observations_20261023.csv").exists()


def test_missing_delivery_quantity_data_is_wait_not_zero_and_candidate_is_retained(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sessions = [(day, pd.DataFrame([{
        "SYMBOL": "AAA", "SERIES": "EQ", "DELIV_PER": 65,
        "TTL_TRD_QNTY": 1000, "CLOSE_PRICE": 100, "PREV_CLOSE": 99,
    }])) for day, _ in _delivery_sessions()]
    report = build_potential_accumulation_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 120}]),
        [_history()], sessions, "2026-10-23"
    )
    assert len(report) == 1
    assert report.iloc[0]["DeliveryEvidenceStatus"] == "WAIT_FOR_DATA"
    assert pd.isna(report.iloc[0]["HighDeliveryQtyTotal"])


def test_insufficient_price_history_is_partial_not_a_rejection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = build_potential_accumulation_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 120}]),
        [_history(periods=10)], _delivery_sessions(), "2026-10-23"
    )
    assert len(report) == 1
    assert report.iloc[0]["PriceHistoryStatus"] == "WAIT_FOR_DATA"
    assert report.iloc[0]["EvidenceStatus"] == "PARTIAL_DATA"



def test_missing_symbol_row_in_a_market_session_waits_for_complete_price_window(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    full = _history()
    missing_day = full.iloc[-5]["Date"]
    symbol_history = full[full["Date"] != missing_day].copy()
    market_calendar = full.copy()
    market_calendar["TckrSymb"] = "OTHER"
    report = build_potential_accumulation_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 120}]),
        [symbol_history, market_calendar], _delivery_sessions(), "2026-10-23"
    )
    assert report.iloc[0]["PriceRange20DStatus"] == "WAIT_FOR_DATA"
    assert report.iloc[0]["PriceHistoryStatus"] == "WAIT_FOR_DATA"
    assert report.iloc[0]["PivotStructureStatus"] == "WAIT_FOR_DATA"
    assert len(report) == 1


def test_future_price_rows_are_excluded_from_asof_range(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    history = _history()
    future = history.iloc[[-1]].copy()
    future["Date"] = pd.Timestamp("2026-10-26")
    future["HghPric"] = 999999
    future["ClsPric"] = 999998
    history = pd.concat([history, future], ignore_index=True)
    report = build_potential_accumulation_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 120}]),
        [history], _delivery_sessions(), "2026-10-23"
    )
    assert report.iloc[0]["PriceRange20DHigh"] < 999999
    assert report.iloc[0]["AsOfDate"] == "2026-10-23"
