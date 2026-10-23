from datetime import date, timedelta
import pandas as pd

from delivery_categories import apply_delivery_categories


def sessions(values_by_symbol):
    result = []
    days = [date(2026, 10, 16) + timedelta(days=i) for i in range(5)]
    for idx, day in enumerate(days):
        rows = []
        for symbol, values in values_by_symbol.items():
            rows.append({"SYMBOL": symbol, "SERIES": "EQ", "DELIV_PER": values[idx]})
        result.append((day, pd.DataFrame(rows)))
    return result


def test_average_category_can_pass_when_one_day_is_below_60(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-20", sessions=sessions({"AAA": [55, 65, 58, 70, 62]})
    )
    assert len(qualified) == 1
    assert audit.iloc[0]["CategoryAStatus"] == "PASS"
    assert audit.iloc[0]["DeliveryFilterStatus"] == "PASS_GE_60_PERCENT"
    assert audit.iloc[0]["DeliveryStatus"] == "PASS"
    assert audit.iloc[0]["CategoryBStatus"] == "FAIL"
    assert audit.iloc[0]["AvgDelivery5D"] >= 60
    assert (tmp_path / "outputs/v8_delivery_category_a_avg60.csv").exists()
    assert (tmp_path / "outputs/v8_delivery_category_b_each_day60.csv").exists()


def test_both_categories_pass_when_every_day_is_at_least_60(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "BBB", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-20", sessions=sessions({"BBB": [60, 65, 61, 70, 63]})
    )
    assert len(qualified) == 1
    assert audit.iloc[0]["CategoryAStatus"] == "PASS"
    assert audit.iloc[0]["CategoryBStatus"] == "PASS"


def test_average_below_60_fails_both_categories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "CCC", "SctySrs": "EQ"}])
    qualified, audit = apply_delivery_categories(
        candidates, "2026-10-20", sessions=sessions({"CCC": [50, 55, 60, 62, 58]})
    )
    assert qualified.empty
    assert audit.iloc[0]["CategoryAStatus"] == "FAIL"
    assert audit.iloc[0]["CategoryBStatus"] == "FAIL"


def test_missing_session_symbol_is_wait_for_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([{"TckrSymb": "DDD", "SctySrs": "EQ"}])
    supplied = sessions({"DDD": [60, 65, 61, 70, 63]})
    supplied[2] = (supplied[2][0], pd.DataFrame(columns=["SYMBOL", "SERIES", "DELIV_PER"]))
    qualified, audit = apply_delivery_categories(candidates, "2026-10-20", sessions=supplied)
    assert qualified.empty
    assert audit.iloc[0]["CategoryAStatus"] == "WAIT_FOR_DATA"
    assert audit.iloc[0]["CategoryBStatus"] == "WAIT_FOR_DATA"
