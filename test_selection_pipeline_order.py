"""Regression tests for NSE V8.0 RVOL >1.5 and dual Delivery order."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent


def test_delivery_pass_union_is_retained_and_rvol_only_classifies_before_liquidity():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    delivery = source.index("STEP 4: DELIVERY A/B ELIGIBILITY, THEN RVOL CLASSIFICATION")
    rvol_classification = source.index("current = classify_rvol_for_delivery_candidates")
    liquidity = source.index("STEP 6: EXISTING LIQUIDITY FILTER")
    fundamental = source.index("STEP 7: FUNDAMENTALS FOR LIQUIDITY-QUALIFIED STOCKS ONLY")
    technical = source.index("STEP 7: PRICE + VOLUME")
    assert delivery < rvol_classification < liquidity < fundamental < technical
    assert "category_a_all" in source and "category_b_all" in source
    assert "A_AND_B" in source
    assert 'delivery_candidates["DeliveryFilterStatus"] = "PASS_GE_60_PERCENT"' in source
    assert 'delivery_candidates["DeliveryStatus"] = "PASS"' in source
    assert "v8_delivery_qualified_all_rvol_classified.csv" in source
    assert "v8_rvol_gt_1_5_candidates.csv" in source
    assert "v8_rvol_le_1_5_delivery_candidates.csv" in source
    assert "No Delivery-qualified stock is rejected by RVOL." in source



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


def test_fundamental_score_is_informational_not_a_hard_gate():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    collection = source.index("STEP 7: FUNDAMENTALS FOR LIQUIDITY-QUALIFIED STOCKS ONLY")
    technical = source.index("STEP 7: PRICE + VOLUME")
    block = source[collection:technical]
    assert "collect_missing_fundamentals(liquidity_pass_candidates" in block
    assert "no score-based rejection" in block
    assert "current = fundamental_audit.loc[fundamental_pass_mask]" not in source
    assert "fallback_pass_mask" not in source
    assert "Fundamental65PlusStatus" in (ROOT / "fundamental_filter.py").read_text(encoding="utf-8")



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


def test_fundamentals_only_fetch_after_liquidity_pass():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    liquidity = source.index("STEP 6: EXISTING LIQUIDITY FILTER")
    collection = source.index("STEP 7: FUNDAMENTALS FOR LIQUIDITY-QUALIFIED STOCKS ONLY")
    assert liquidity < collection
    assert "liquidity_pass_candidates = current.copy()" in source
    assert "v8_liquidity_fundamental_candidates.csv" in source
    assert "never remove a row" in (ROOT / "fundamental_filter.py").read_text(encoding="utf-8")


def test_technical_parameter_audit_shows_values_rules_and_statuses(tmp_path, monkeypatch):
    import pandas as pd
    import volume_gainer as scanner

    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([
        {
            "TckrSymb": "BREAK", "DeliveryFilterStatus": "PASS_GE_60_PERCENT",
            "RVOLStatus": "PASS", "RVOL": 2.2, "SetupType": "Breakout",
            "TrendClassification": "Sideways / Mixed", "CLV": 0.91,
            "PriceVolumeRelationship": "Strong Bullish", "RelativeStrengthNifty": 2.4,
            "SRSupport": 98.0, "SRResistance": 120.0, "BreakoutStatus": "Breakout",
            "PullbackStatus": "No Pullback", "PriceChangePct": 7.6,
            "RSI14": 70.6, "EMA20": 968.4, "EMA44": 986.3,
            "CandidateScreenStatus": "REJECT", "CandidateScreenReasons": "TREND_NOT_BULLISH",
        },
        {
            "TckrSymb": "POSSIBLE", "DeliveryFilterStatus": "PASS_GE_60_PERCENT",
            "RVOLStatus": "PASS", "RVOL": 2.7, "SetupType": "Possible Pullback",
            "TrendClassification": "Strong Bullish Trend", "CLV": 0.006,
            "PriceVolumeRelationship": "Possible Accumulation/Event", "RelativeStrengthNifty": -10.6,
            "SRSupport": 540.0, "SRResistance": 559.8, "BreakoutStatus": "No Breakout",
            "PullbackStatus": "Possible Pullback", "PriceChangePct": 0.0, "LowVolumeDays5D": 3,
            "RSI14": 53.9, "EMA20": 539.8, "EMA44": 521.6,
            "CandidateScreenStatus": "REJECT", "CandidateScreenReasons": "NO_CONFIRMED_BREAKOUT_OR_PULLBACK_SETUP",
        },
    ])

    details, summary = scanner.write_technical_parameter_audit(candidates, "2026-11-05")
    indexed = details.set_index(["TckrSymb", "Parameter"])

    assert indexed.loc[("BREAK", "Trend"), "Status"] == "FAIL"
    assert indexed.loc[("BREAK", "Breakout confirmation"), "Status"] == "PASS"
    assert indexed.loc[("BREAK", "Candle quality (CLV)"), "RequiredRule"] == "Breakout CLV must be >0.75."
    assert indexed.loc[("POSSIBLE", "Confirmed setup"), "Status"] == "FAIL"
    assert indexed.loc[("POSSIBLE", "Pullback confirmation"), "Status"] == "FAIL"
    assert indexed.loc[("POSSIBLE", "Relative strength vs Nifty"), "Status"] == "INFO"
    assert {"ObservedValue", "RequiredRule", "Reason", "OverallTechnicalStatus"}.issubset(details.columns)
    assert summary.loc[summary["Parameter"] == "Trend", "FailCount"].iloc[0] == 1
    assert (tmp_path / "outputs/v8_technical_parameter_audit.csv").exists()
    assert (tmp_path / "outputs/v8_technical_parameter_summary.csv").exists()




def test_rvol_classification_retains_high_low_and_missing_delivery_candidates(tmp_path, monkeypatch):
    import pandas as pd
    import volume_gainer as scanner

    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({
        "TckrSymb": ["HIGH", "BOUNDARY", "LOW", "WAIT", "MISSING"],
        "RVOL": [1.5001, 1.5, 0.82, 2.4, None],
        "RVOLStatus": ["PASS", "PASS", "PASS", "WAIT_FOR_DATA", "PASS"],
        "DeliveryFilterStatus": ["PASS_GE_60_PERCENT"] * 5,
    })

    classified = scanner.classify_rvol_for_delivery_candidates(frame, "2026-11-07", 1.5)

    assert len(classified) == 5
    assert classified.set_index("TckrSymb").loc["HIGH", "RVOLBand"] == "HIGH_RVOL_GT_1_5"
    assert classified.set_index("TckrSymb").loc["BOUNDARY", "RVOLBand"] == "LOW_RVOL_LE_1_5"
    assert classified.set_index("TckrSymb").loc["LOW", "RVOLBand"] == "LOW_RVOL_LE_1_5"
    assert classified.set_index("TckrSymb").loc["WAIT", "RVOLBand"] == "WAIT_FOR_DATA"
    assert classified.set_index("TckrSymb").loc["MISSING", "RVOLBand"] == "WAIT_FOR_DATA"



def test_accumulation_and_vcp_observations_run_before_liquidity_without_gating():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    delivery = source.index("STEP 4: DELIVERY A/B ELIGIBILITY, THEN RVOL CLASSIFICATION")
    rvol = source.index("current = classify_rvol_for_delivery_candidates")
    accumulation = source.index("accumulation_report = build_potential_accumulation_report")
    vcp = source.index("vcp_report = build_vcp_observation_report")
    liquidity = source.index("STEP 6: EXISTING LIQUIDITY FILTER")
    assert delivery < rvol < accumulation < vcp < liquidity
    early_block = source[accumulation:liquidity]
    assert "current, historical, delivery_sessions, eod_date" in early_block
    assert "current, historical, eod_date" in early_block
    assert "no gating applied" in early_block
    assert "except Exception as accumulation_exc" in early_block
    assert "except Exception as vcp_exc" in early_block
    assert "current = accumulation_report" not in source
    assert "current = vcp_report" not in source



def test_four_hybrid_watchlists_are_independent_and_stage_ordered():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    early_reports = source.index("write_early_hybrid_watchlists(\n            accumulation_report, vcp_report")
    liquidity = source.index("STEP 6: EXISTING LIQUIDITY FILTER")
    run_layers = source.index("result = run_eod_layers(")
    breakout_watchlist = source.index("write_breakout_ready_watchlist(result)")
    entry_watchlist = source.index("write_confirmed_entry_watchlist(result)")
    assert early_reports < liquidity < run_layers < breakout_watchlist < entry_watchlist
    assert "current = accumulation_report" not in source
    assert "current = vcp_report" not in source
    assert "result = write_breakout_ready_watchlist" not in source
    assert "result = write_confirmed_entry_watchlist" not in source



def test_accumulation_engine_failure_keeps_delivery_ab_candidates_for_wait_watchlist():
    source = (ROOT / "volume_gainer.py").read_text(encoding="utf-8")
    marker = "except Exception as accumulation_exc:"
    start = source.index(marker)
    end = source.index("# VCP measurements", start)
    fallback = source[start:end]
    assert 'accumulation_report = current.drop_duplicates("TckrSymb", keep="first").copy()' in fallback
    assert 'accumulation_report["DeliveryEvidenceStatus"] = "WAIT_FOR_DATA"' in fallback
    assert 'accumulation_report["EvidenceStatus"] = "WAIT_FOR_DATA"' in fallback
