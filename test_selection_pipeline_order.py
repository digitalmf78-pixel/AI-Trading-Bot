"""Structural regression tests for the agreed NSE V8 EOD selection order."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_delivery_liquidity_fundamental_precede_rvol_and_technical():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    delivery = source.index("STEP 2A: MANDATORY DELIVERY-FIRST GATE")
    liquidity = source.index("STEP 3A: LIQUIDITY GATE")
    fundamental = source.index("STEP 3B: FUNDAMENTAL QUALITY GATE")
    rvol = source.index("result = select_top20_by_rvol(result, eod_date)")
    technical = source.index("STEP 7: PRICE + VOLUME")
    assert delivery < liquidity < fundamental < rvol < technical


def test_fundamental_pass_is_required_for_final_shortlist():
    source = (ROOT / "v8_layers_14_41.py").read_text(encoding="utf-8")
    assert 'row.get("FundamentalStatus", "WAIT_FOR_DATA")' in source
    assert 'row.get("FundamentalStatus") == "PASS"' in source
    assert 'head(4)' in source


def test_reports_and_input_template_are_wired():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    assert "v8_fundamental_report.csv" in source
    assert 'v8_technical_report.csv' in source
    assert "v8_selection_status_report.csv" in source


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
