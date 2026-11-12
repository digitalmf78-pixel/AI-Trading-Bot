from datetime import date
import pandas as pd

from delivery_categories import apply_delivery_categories


def _sessions(values_by_symbol):
    days = [date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 19),
            date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]
    result = []
    for index, day in enumerate(days):
        rows = []
        for symbol, values in values_by_symbol.items():
            if values[index] is not None:
                rows.append({"SYMBOL": symbol, "SERIES": "EQ", "DELIV_PER": values[index]})
        result.append((day, pd.DataFrame(rows, columns=["SYMBOL", "SERIES", "DELIV_PER"])))
    return result


def test_delivery_b_passes_after_five_daily_qualifying_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-23", sessions=_sessions({"AAA": [50, 62, 62, 62, 62, 62]})
    )
    row = audit.iloc[0]
    assert len(qualified) == 1
    assert row["DeliverySessions"] == 6
    assert row["DeliveryARolling5DPassCount30D"] == 1
    assert row["DeliveryDailyPassCount"] == 5
    assert row["CategoryAStatus"] == "FAIL"
    assert row["CategoryBStatus"] == "PASS"
    assert row["AvgDelivery30D"] == 60
    assert (tmp_path / "outputs/v8_delivery_category_b_daily60_count5.csv").exists()


def test_category_b_counts_daily_sessions_not_all_sessions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "BBB", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-23", sessions=_sessions({"BBB": [60, 65, 61, 70, 63, 62]})
    )
    row = audit.iloc[0]
    assert len(qualified) == 1
    assert row["DeliveryARolling5DPassCount30D"] == 2
    assert row["DeliveryDailyPassCount"] == 6
    assert row["CategoryAStatus"] == "FAIL"
    assert row["CategoryBStatus"] == "PASS"


def test_both_categories_fail_when_fewer_than_five_qualifying_counts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "CCC", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-23", sessions=_sessions({"CCC": [50, 55, 60, 62, 58, 59]})
    )
    assert qualified.empty
    assert audit.iloc[0]["CategoryAStatus"] == "FAIL"
    assert audit.iloc[0]["CategoryBStatus"] == "FAIL"


def test_candidate_with_fewer_than_five_valid_reports_waits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "DDD", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-23",
        sessions=_sessions({"DDD": [60, None, None, None, 63, 70]}),
    )
    assert qualified.empty
    assert audit.iloc[0]["CategoryAStatus"] == "WAIT_FOR_DATA"
    assert audit.iloc[0]["CategoryBStatus"] == "WAIT_FOR_DATA"
