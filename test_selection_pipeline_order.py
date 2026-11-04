"""Regression tests for NSE V8.0 RVOL >1.5 and dual Delivery order."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent


def test_rvol_delivery_fundamental_collection_precedes_liquidity_and_technical():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    rvol = source.index("STEP 3: LOAD HISTORY AND CALCULATE RVOL BEFORE DELIVERY")
    delivery = source.index("STEP 4: TWO DELIVERY CATEGORIES, AFTER RVOL > 1.5")
    fundamental = source.index("STEP 5: FUNDAMENTAL DATA COLLECTION FOR ALL DELIVERY A/B STOCKS")
    liquidity = source.index("STEP 6: EXISTING LIQUIDITY FILTER")
    technical = source.index("STEP 7: PRICE + VOLUME")
    assert rvol < delivery < fundamental < liquidity < technical


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


def test_fundamental_hard_gate_follows_full_collection_and_metric_verification():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    collection = source.index("STEP 5: FUNDAMENTAL DATA COLLECTION FOR ALL DELIVERY A/B STOCKS")
    audit = source.index("run_fundamental_metric_audit()", collection)
    assessment = source.index("metric_verification=metric_verification", audit)
    liquidity = source.index("STEP 6: EXISTING LIQUIDITY FILTER", assessment)
    block = source[assessment:liquidity]
    assert collection < audit < assessment < liquidity
    assert '"FundamentalShortlistStatus", pd.Series("WAIT_FOR_DATA"' in block
    assert '.astype(str).eq("PASS")' in block
    assert "all A/B records remain in their audit reports" in block
    layer = (ROOT / "v8_layers_14_41.py").read_text(encoding="utf-8")
    assert 'row.get("FundamentalStatus") == "PASS"' not in layer
    assert 'head(4)' in layer


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


def test_fundamental_collection_covers_delivery_a_and_b_before_selection_gate():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    assert "DeliveryCategoryAStatus" in source and "DeliveryCategoryBStatus" in source
    assert "v8_delivery_a_fundamentals.csv" in source
    assert "v8_delivery_b_fundamentals.csv" in source
    assert "v8_delivery_ab_combined_fundamentals.csv" in source
    assert "every unique symbol in Delivery A/B" in source
    assert "all A/B records remain in their audit reports" in source
    fundamental = (ROOT / "fundamental_filter.py").read_text(encoding="utf-8")
    assert "never remove a row" in fundamental
    assert '"NOT_SHORTLISTED_YET"' in fundamental


def test_fundamental_gate_waits_for_verified_metrics_and_pass_status():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    collection = source.index("STEP 5: FUNDAMENTAL DATA COLLECTION FOR ALL DELIVERY A/B STOCKS")
    assessment = source.index('fundamental_audit["FundamentalAssessmentStatus"] = fundamental_audit["FundamentalShortlistStatus"].astype(str)')
    liquidity = source.index("STEP 6: EXISTING LIQUIDITY FILTER")
    block = source[source.index("# Preserve all A/B fundamentals in the collection reports."):liquidity]
    assert collection < assessment < liquidity
    assert 'current = fundamental_audit.loc[fundamental_pass_mask].copy()' in block
    assert "run_fundamental_metric_audit()" in source
    assert "require_explicit_thresholds=True" in source
    assert 'fallback_pass_mask' in source
    assert 'current = fundamental_audit.loc[fallback_pass_mask].copy()' in source
    # Collection reports preserve every A/B candidate and statuses.
    assert 'fundamental_audit.to_csv("outputs/v8_fundamental_report.csv", index=False)' in source

