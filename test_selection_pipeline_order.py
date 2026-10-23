"""Structural regression tests for the approved NSE V8 selection sequence."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_mainboard_rvol_top50_delivery_categories_fundamental_then_technical():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    board = source.index("STEP 1B: OFFICIAL MAIN BOARD ONLY")
    rvol = source.index("result = select_top50_by_rvol(result, eod_date)")
    delivery = source.index("STEP 4: TWO INDEPENDENT DELIVERY CATEGORIES")
    fundamental = source.index("STEP 5: FUNDAMENTAL CHECK AND RANKING")
    technical = source.index("STEP 7: PRICE + VOLUME")
    assert board < rvol < delivery < fundamental < technical
    assert "v8_primary_shortlist_top50.csv" in source
    assert "v8_delivery_category_a_avg60.csv" in source or "apply_delivery_categories" in source
    assert "v8_fundamental_ranked_candidates.csv" in source


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
    import os
    import tempfile
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
