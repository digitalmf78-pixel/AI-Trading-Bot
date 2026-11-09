from datetime import date, timedelta
import pandas as pd

from delivery_quantity_analysis import build_delivery_quantity_report


def _reports(qty_values, close_values=None):
    start = date(2026, 10, 1)
    reports = []
    for index, qty in enumerate(qty_values):
        close = close_values[index] if close_values else 100 + index
        reports.append((start + timedelta(days=index), pd.DataFrame([{
            "SYMBOL": "AAA", "SERIES": "EQ", "DELIV_QTY": qty,
            "DELIV_PER": 60 + index / 10, "TTL_TRD_QNTY": qty * 2,
            "CLOSE_PRICE": close,
        }])))
    return reports


def test_quantity_windows_are_observational_and_calculated_for_5_10_20_sessions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    enriched, audit = build_delivery_quantity_report(
        candidates, "2026-10-20", _reports(list(range(100, 120)))
    )
    row = enriched.iloc[0]
    assert row["DeliveryQty5DStatus"] == "COMPLETE"
    assert row["DeliveryQty10DStatus"] == "COMPLETE"
    assert row["DeliveryQty20DStatus"] == "COMPLETE"
    assert row["DeliveryQty5DTotal"] == sum(range(115, 120))
    assert row["DeliveryQty5DFirst"] == 115
    assert row["DeliveryQty5DLast"] == 119
    assert row["DeliveryQuantityStatus"] == "COMPLETE_5_10_20D"
    assert len(audit) == 1


def test_missing_symbol_session_is_wait_for_data_not_a_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reports = _reports(list(range(20)))
    reports[10] = (reports[10][0], pd.DataFrame(columns=[
        "SYMBOL", "SERIES", "DELIV_QTY", "DELIV_PER", "TTL_TRD_QNTY", "CLOSE_PRICE"
    ]))
    enriched, _ = build_delivery_quantity_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}]), "2026-10-20", reports
    )
    row = enriched.iloc[0]
    assert row["DeliveryQty20DStatus"] == "WAIT_FOR_DATA"
    assert row["DeliveryQuantityStatus"] == "WAIT_FOR_DATA"


def test_missing_delivery_quantity_column_waits_without_dropping_candidate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reports = _reports(list(range(20)))
    reports[19] = (reports[19][0], pd.DataFrame([{
        "SYMBOL": "AAA", "SERIES": "EQ", "DELIV_PER": 65
    }]))
    enriched, _ = build_delivery_quantity_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}]), "2026-10-20", reports
    )
    assert len(enriched) == 1
    assert enriched.iloc[0]["DeliveryQty5DStatus"] == "WAIT_FOR_DATA"


def test_duplicate_symbol_series_is_ambiguous_and_waits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reports = _reports(list(range(20)))
    duplicate = pd.concat([reports[-1][1], reports[-1][1]], ignore_index=True)
    reports[-1] = (reports[-1][0], duplicate)
    enriched, _ = build_delivery_quantity_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}]), "2026-10-20", reports
    )
    assert enriched.iloc[0]["DeliveryQty5DStatus"] == "WAIT_FOR_DATA"
    assert enriched.iloc[0]["DeliveryQty5DReason"] == "AMBIGUOUS_DUPLICATE_SYMBOL_SERIES"


def test_future_reports_are_excluded_and_price_response_is_descriptive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reports = _reports(list(range(20)), [100 + i for i in range(20)])
    reports.append((date(2026, 10, 21), pd.DataFrame([{
        "SYMBOL": "AAA", "SERIES": "EQ", "DELIV_QTY": 999999,
        "DELIV_PER": 99, "TTL_TRD_QNTY": 999999, "CLOSE_PRICE": 999,
    }])))
    enriched, _ = build_delivery_quantity_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}]), "2026-10-20", reports
    )
    row = enriched.iloc[0]
    assert row["DeliveryQty5DLast"] == 19
    assert row["DeliveryQty5DCloseFirst"] == 115
    assert row["DeliveryQty5DCloseLast"] == 119
    assert row["DeliveryQty5DCloseChangePct"] > 0


def test_quantity_zero_is_valid_and_change_percentage_is_nan_when_start_is_zero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    values = list(range(20))
    values[15] = 0
    enriched, _ = build_delivery_quantity_report(
        pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}]), "2026-10-20", _reports(values)
    )
    assert enriched.iloc[0]["DeliveryQty5DFirst"] == 0
    assert pd.notna(enriched.iloc[0]["DeliveryQty5DChangePct"])
