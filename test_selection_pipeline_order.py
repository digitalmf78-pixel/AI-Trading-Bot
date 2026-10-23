"""Regression tests for NSE V8.0 RVOL >1.5 and dual Delivery order."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent


def test_rvol_precedes_delivery_liquidity_fundamental_and_technical():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    rvol = source.index("STEP 3: LOAD HISTORY AND CALCULATE RVOL BEFORE DELIVERY")
    delivery = source.index("STEP 4: TWO DELIVERY CATEGORIES, AFTER RVOL > 1.5")
    liquidity = source.index("STEP 5: EXISTING LIQUIDITY FILTER")
    fundamental = source.index("STEP 6: EXISTING FUNDAMENTAL FILTER")
    technical = source.index("STEP 7: PRICE + VOLUME")
    assert rvol < delivery < liquidity < fundamental < technical


def test_rvol_has_no_top_50_or_top_20_cap():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    start = source.index("def select_rvol_above_threshold")
    end = source.index("# PRICE + VOLUME", start)
    selector = source[start:end]
    assert "minimum_rvol=1.5" in selector
    assert 'float(row.get("RVOL")) > float(minimum_rvol)' in selector
    assert ".head(20)" not in selector
    assert ".head(50)" not in selector


def test_dual_delivery_categories_are_written_separately():
    source = (ROOT / "delivery_filter.py").read_text(encoding="utf-8")
    assert "PASS_AVG_GE_60_PERCENT" in source
    assert "PASS_EACH_DAY_GE_60_PERCENT" in source
    assert "v8_delivery_category_a_avg60.csv" in source
    assert "v8_delivery_category_b_each_day60.csv" in source


def test_fundamental_pass_is_required_for_final_shortlist():
    source = (ROOT / "v8_layers_14_41.py").read_text(encoding="utf-8")
    assert 'row.get("FundamentalStatus", "WAIT_FOR_DATA")' in source
    assert 'row.get("FundamentalStatus") == "PASS"' in source
    assert 'head(4)' in source


def test_reports_and_input_template_are_wired():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    assert "v8_fundamental_report.csv" in source
    assert 'v8_technical_report.csv' in source
    assert 'v8_selection_status_report.csv' in source


def test_empty_eligible_universe_still_writes_empty_final_shortlist():
    import os, tempfile
    import pandas as pd
    from v8_layers_14_41 import run_eod_layers
    columns = ["TckrSymb", "Open", "High", "Low", "Close", "Volume", "DeliveryFilterStatus", "FundamentalStatus"]
    empty = pd.DataFrame(columns=columns)
    original_cwd = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            output = run_eod_layers(empty, [], empty, pd.DataFrame(columns=["Date", "NiftyClose"]), "2026-10-19")
            assert output.empty
            assert Path("outputs/v8_final_shortlist.csv").exists()
    finally:
        os.chdir(original_cwd)


def test_rvol_selector_keeps_all_qualifying_stocks_without_top_cap(tmp_path, monkeypatch):
    import pandas as pd
    import volume_gainer as scanner
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({
        "TckrSymb": [f"STK{i:03d}" for i in range(75)],
        "RVOL": [1.51 + i / 100 for i in range(75)],
        "RVOLStatus": ["PASS"] * 75,
    })
    selected = scanner.select_rvol_above_threshold(frame, "2026-10-22", minimum_rvol=1.5)
    assert len(selected) == 75
    assert selected["RVOL"].min() > 1.5
    assert selected["RVOLRank"].tolist() == list(range(1, 76))
