from datetime import date

import pandas as pd

from delivery_ab_history_cache import build_ab_qualified_history, persist_ab_qualified_history


def _report(day, rows):
    return day, pd.DataFrame({
        "DATE1": [day.strftime("%d-%b-%Y")] * len(rows),
        "SYMBOL": [r[0] for r in rows],
        "SERIES": [r[1] for r in rows],
        "DELIV_QTY": [r[2] for r in rows],
        "DELIV_PER": [r[3] for r in rows],
    })


def _audit():
    return pd.DataFrame([
        {
            "TckrSymb": "AAA", "SctySrs": "EQ",
            "DeliveryCategoryAStatus": "PASS_ROLLING_5D_AVG_GE_60_AT_LEAST_5",
            "DeliveryCategoryBStatus": "FILTERED_OUT_DAILY_DELIVERY_LT_5",
            "DeliverySessions": 8, "DeliveryACount30DDisplay": "5/30",
            "DeliveryBCount30DDisplay": "4/30",
        },
        {
            "TckrSymb": "BBB", "SctySrs": "EQ",
            "DeliveryCategoryAStatus": "PASS_ROLLING_5D_AVG_GE_60_AT_LEAST_5",
            "DeliveryCategoryBStatus": "PASS_DAILY_DELIVERY_GE_60_AT_LEAST_5",
            "DeliverySessions": 8, "DeliveryACount30DDisplay": "6/30",
            "DeliveryBCount30DDisplay": "7/30",
        },
        {
            "TckrSymb": "CCC", "SctySrs": "EQ",
            "DeliveryCategoryAStatus": "FILTERED_OUT_ROLLING_5D_AVG_LT_5",
            "DeliveryCategoryBStatus": "FILTERED_OUT_DAILY_DELIVERY_LT_5",
            "DeliverySessions": 8, "DeliveryACount30DDisplay": "2/30",
            "DeliveryBCount30DDisplay": "3/30",
        },
    ])


def test_history_keeps_all_available_days_for_a_or_b_members_only():
    d1, d2 = date(2026, 11, 10), date(2026, 11, 11)
    sessions = [
        _report(d1, [("AAA", "EQ", "100", "55"), ("BBB", "EQ", "200", "70"), ("CCC", "EQ", "300", "80")]),
        _report(d2, [("AAA", "EQ", "110", "75"), ("BBB", "EQ", "-", "61"), ("CCC", "EQ", "310", "90")]),
    ]
    result = build_ab_qualified_history(_audit(), sessions, date(2026, 11, 11))
    assert set(result["Symbol"]) == {"AAA", "BBB"}
    assert len(result) == 4
    assert set(result.loc[result.Symbol.eq("AAA"), "DELIV_PER"]) == {55.0, 75.0}
    assert result.loc[(result.Symbol == "BBB") & (result.ReportDate == "2026-11-11"), "DELIV_QTY"].isna().all()
    assert set(result.loc[result.Symbol.eq("AAA"), "DeliveryMembership"]) == {"A_ONLY"}
    assert set(result.loc[result.Symbol.eq("BBB"), "DeliveryMembership"]) == {"A_AND_B"}
    assert result["AsOfDate"].eq("2026-11-11").all()


def test_history_excludes_observations_outside_30_calendar_day_window():
    old = date(2026, 10, 12)
    recent = date(2026, 10, 13)
    sessions = [
        _report(old, [("AAA", "EQ", "10", "65")]),
        _report(recent, [("AAA", "EQ", "20", "66")]),
    ]
    result = build_ab_qualified_history(_audit().iloc[[0]], sessions, date(2026, 11, 11))
    assert result["ReportDate"].tolist() == ["2026-10-13"]


def test_persist_replaces_snapshot_idempotently(tmp_path):
    d = date(2026, 11, 11)
    sessions = [_report(d, [("AAA", "EQ", "100", "65")])]
    path = tmp_path / "ab_qualified_delivery_history.csv"
    first = persist_ab_qualified_history(_audit().iloc[[0]], sessions, d, path)
    second = persist_ab_qualified_history(_audit().iloc[[0]], sessions, d, path)
    disk = pd.read_csv(path)
    assert len(first) == len(second) == len(disk) == 1
    assert disk.loc[0, "Symbol"] == "AAA"


def test_internal_report_date_mismatch_is_rejected():
    requested = date(2026, 11, 11)
    # The cache key says Nov 11, but the official report's DATE1 says Nov 10.
    _, wrong_frame = _report(date(2026, 11, 10), [("AAA", "EQ", "100", "65")])
    wrong = (requested, wrong_frame)
    try:
        build_ab_qualified_history(_audit().iloc[[0]], [wrong], requested)
    except ValueError as exc:
        assert "DATE1 mismatch" in str(exc)
    else:
        raise AssertionError("Mismatched official report date must fail closed")
