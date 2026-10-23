"""Regression tests for the NSE Swing Trading V8 safety gates.
Run: python test_v8_regression.py
"""
from datetime import date, timedelta
from pathlib import Path
import tempfile
import os

import pandas as pd

import delivery_filter as delivery
import sector_data
import v8_layers_14_41 as layers
import volume_gainer as scanner
import news_catalyst


def test_3_confirmations_plus_separate_primary_source_gate():
    base = pd.Series({
        "TrendClassification": "Strong Bullish Trend",
        "RelativeStrengthNifty": 3.0,
        "RVOL": 2.0,
        "CLV": 0.8,
        "SectorStrengthStatus": "PASS",
        "SectorStrengthNifty": 1.2,
        "AccumulationDistributionStatus": "PASS",
        "AccumulationDistribution": "Accumulation",
        "NewsEvidenceStatus": "PRIMARY_CONFIRMED",
        "NewsCatalyst": "Verified company order filing",
        "NewsPrimarySourceVerified": True,
        "NewsNegativePrimary": False,
    })
    # Three confirmation categories pass; primary source is a separate qualifier.
    base["AccumulationDistribution"] = "Neutral"
    count, labels, status = layers._independent_confirmation_evaluation(base)
    assert count == 3, (count, labels, status)
    assert status == "PASS", (count, labels, status)
    assert "CATALYST" in labels and "CATALYST_PRIMARY_SOURCE" not in labels

    # A primary source by itself cannot count as one of the three confirmations.
    base["SectorStrengthStatus"] = "FAIL"
    base["NewsCatalyst"] = ""
    count, labels, status = layers._independent_confirmation_evaluation(base)
    assert count == 1, (count, labels, status)
    assert status == "FAIL", (count, labels, status)


def test_three_secondary_reposts_do_not_create_three_confirmations():
    rows = [
        {"TckrSymb": "ABC", "PublishedAt": "2026-10-09T10:00:00Z", "Headline": "ABC wins order", "Source": "NSE India", "SourceType": "primary", "URL": "https://nsearchives.nseindia.com/abc", "Impact": "positive", "EventID": "order-1", "SourceDomain": "nsearchives.nseindia.com"},
        {"TckrSymb": "ABC", "PublishedAt": "2026-10-09T10:01:00Z", "Headline": "ABC wins order", "Source": "Publisher One", "SourceType": "secondary", "URL": "https://one.example/a", "Impact": "positive", "EventID": "order-1", "SourceDomain": "one.example"},
        {"TckrSymb": "ABC", "PublishedAt": "2026-10-09T10:02:00Z", "Headline": "ABC wins order", "Source": "Publisher Two", "SourceType": "secondary", "URL": "https://two.example/a", "Impact": "positive", "EventID": "order-1", "SourceDomain": "two.example"},
        {"TckrSymb": "ABC", "PublishedAt": "2026-10-09T10:03:00Z", "Headline": "ABC wins order", "Source": "Publisher Three", "SourceType": "secondary", "URL": "https://three.example/a", "Impact": "positive", "EventID": "order-1", "SourceDomain": "three.example"},
    ]
    news = layers._news_for_symbol(
        pd.DataFrame(rows), "ABC", pd.Timestamp("2026-10-09T23:59:00+05:30"),
        start=pd.Timestamp("2026-10-09T00:00:00+05:30"),
    )
    assert news["NewsEvidenceStatus"] == "PRIMARY_CONFIRMED"
    assert news["NewsPrimarySourceVerified"] is True
    assert news["NewsIndependentSources"] == 3
    row = pd.Series({
        **news,
        "TrendClassification": "Sideways", "RelativeStrengthNifty": 0.0,
        "RVOL": 1.0, "CLV": 0.4,
        "SectorStrengthStatus": "FAIL", "SectorStrengthNifty": -3.0,
        "AccumulationDistributionStatus": "PASS", "AccumulationDistribution": "Neutral",
    })
    count, labels, status = layers._independent_confirmation_evaluation(row)
    assert count == 1 and status == "FAIL", (count, labels, status)


def test_untrusted_domain_cannot_be_primary_just_because_of_label():
    row = pd.Series({
        "SourceType": "primary", "SourceDomain": "fake-example.com",
        "URL": "https://fake-example.com/filing",
    })
    assert layers._is_primary(row) is False
    official = pd.Series({
        "SourceType": "primary", "SourceDomain": "nsearchives.nseindia.com",
        "URL": "https://nsearchives.nseindia.com/filing",
    })
    assert layers._is_primary(official) is True



def test_sector_mapping_uses_exact_official_nse_industry_fallbacks():
    with tempfile.TemporaryDirectory() as tmp:
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            rows = sector_data._targeted_shortlist_mappings(
                candidate_symbols=["ABC", "UNKNOWN"],
                existing_mapping_by_symbol={},
                nifty500_industries={},
                asof=pd.Timestamp("2026-10-13"),
                nse_classifications={
                    "ABC": {
                        "macro": "HEALTHCARE",
                        "sector": "",
                        "industry": "PHARMACEUTICALS",
                        "basicIndustry": "PHARMACEUTICALS",
                    },
                    "UNKNOWN": {
                        "macro": "",
                        "sector": "",
                        "industry": "UNMAPPED INDUSTRY",
                        "basicIndustry": "UNMAPPED INDUSTRY",
                    },
                },
                etf_symbols=set(),
            )
            assert rows == [{
                "TckrSymb": "ABC",
                "Sector": "Nifty Pharma",
                "SectorIndexSymbol": "NIFTY PHARMA",
            }], rows
            audit = pd.read_csv("data/reports/sector_candidate_mapping_20261013.csv")
            status = dict(zip(audit["TckrSymb"], audit["MappingStatus"]))
            assert status["ABC"] == "OFFICIAL_NSE_INDUSTRY_MAPPED", status
            assert status["UNKNOWN"] == "WAIT_FOR_DATA", status
        finally:
            os.chdir(old_cwd)

def test_delivery_average_category_passes_while_daily_category_fails():
    with tempfile.TemporaryDirectory() as tmp:
        delivery.AUDIT_DIR = Path(tmp)
        dates = [date(2026, 10, 9) - timedelta(days=i) for i in range(5)]
        values = [50.0, 75.0, 65.0, 70.0, 80.0]
        sessions = [(day, pd.DataFrame([{"SYMBOL": "ABC", "SERIES": "EQ", "DELIV_PER": value}])) for day, value in zip(dates, values)]
        candidates = pd.DataFrame([{"TckrSymb": "ABC", "SctySrs": "EQ"}])
        qualified, audit = delivery.apply_delivery_filter(candidates, dates[0], sessions=sessions)
        assert len(qualified) == 1
        assert audit.iloc[0]["DeliveryCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
        assert audit.iloc[0]["DeliveryCategoryBStatus"] == "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT"
        assert audit.iloc[0]["AvgDelivery5D"] >= 60.0
        assert audit.iloc[0]["DeliveryMin5D"] == 50.0


def test_delivery_exactly_60_each_day_passes():
    with tempfile.TemporaryDirectory() as tmp:
        delivery.AUDIT_DIR = Path(tmp)
        dates = [date(2026, 10, 9) - timedelta(days=i) for i in range(5)]
        values = [60.0, 60.0, 60.0, 60.0, 60.0]
        sessions = [(day, pd.DataFrame([{"SYMBOL": "ABC", "SERIES": "EQ", "DELIV_PER": value}])) for day, value in zip(dates, values)]
        candidates = pd.DataFrame([{"TckrSymb": "ABC", "SctySrs": "EQ"}])
        qualified, audit = delivery.apply_delivery_filter(candidates, dates[0], sessions=sessions)
        assert len(qualified) == 1, audit.to_dict("records")
        assert audit.iloc[0]["DeliveryFilterStatus"] == "PASS_GE_60_PERCENT"
        assert audit.iloc[0]["DeliveryCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
        assert audit.iloc[0]["DeliveryCategoryBStatus"] == "PASS_EACH_DAY_GE_60_PERCENT"
        assert audit.iloc[0]["DeliveryDailyPassCount"] == 5


def test_delivery_below_60_rejects_and_incomplete_waits():
    with tempfile.TemporaryDirectory() as tmp:
        delivery.AUDIT_DIR = Path(tmp)
        dates = [date(2026, 10, 9) - timedelta(days=i) for i in range(5)]
        sessions = [(day, pd.DataFrame([{"SYMBOL": "ABC", "SERIES": "EQ", "DELIV_PER": value}]))
                    for day, value in zip(dates, [60.0, 60.0, 59.99, 80.0, 90.0])]
        candidates = pd.DataFrame([{"TckrSymb": "ABC", "SctySrs": "EQ"}])
        qualified, audit = delivery.apply_delivery_filter(candidates, dates[0], sessions=sessions)
        assert len(qualified) == 1  # Average category passes despite one day below 60.
        assert audit.iloc[0]["DeliveryCategoryAStatus"] == "PASS_AVG_GE_60_PERCENT"
        assert audit.iloc[0]["DeliveryCategoryBStatus"] == "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT"
        qualified, audit = delivery.apply_delivery_filter(candidates, dates[0], sessions=sessions[:4])
        assert qualified.empty
        assert audit.iloc[0]["DeliveryFilterStatus"] == "WAIT_FOR_DATA"
        assert audit.iloc[0]["DeliveryCategoryAStatus"] == "WAIT_FOR_DATA"
        assert audit.iloc[0]["DeliveryCategoryBStatus"] == "WAIT_FOR_DATA"


def test_news_gate_uses_category_a_average_status_and_keeps_category_b_separate():
    candidates = pd.DataFrame([{
        "TckrSymb": "ABC", "AvgDelivery5D": 74.98,
        "DeliveryCategoryAStatus": "PASS_AVG_GE_60_PERCENT",
        "DeliveryCategoryBStatus": "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT",
        "DeliveryFilterStatus": "PASS_GE_60_PERCENT", "SetupType": "Breakout",
    }])
    assert len(news_catalyst._filter_catalyst_candidates(candidates)) == 1


def test_rvol_threshold_precedes_dual_delivery_in_scanner_source():
    source = Path("volume_gainer.py").read_text(encoding="utf-8")
    rvol_step = source.index("STEP 3: LOAD HISTORY AND CALCULATE RVOL BEFORE DELIVERY")
    delivery_step = source.index("STEP 4: TWO DELIVERY CATEGORIES, AFTER RVOL > 1.5")
    liquidity_step = source.index("STEP 5: EXISTING LIQUIDITY FILTER")
    fundamental_step = source.index("STEP 6: EXISTING FUNDAMENTAL FILTER")
    technical_step = source.index("STEP 7: PRICE + VOLUME")
    assert rvol_step < delivery_step < liquidity_step < fundamental_step < technical_step
    assert "def select_rvol_above_threshold" in source
    assert "minimum_rvol=1.5" in source
    assert ".head(50)" not in source[source.index("def select_rvol_above_threshold"):source.index("# PRICE + VOLUME")]


def test_empty_delivery_shortlist_keeps_merge_keys_through_technical_steps():
    # Delivery data can be legitimately unavailable. An empty shortlist must
    # not crash EMA44, breakout/pullback, or support/resistance merges.
    empty = pd.DataFrame(columns=[
        "TckrSymb", "ClsPric", "HghPric", "LwPric", "OpnPric",
        "TtlTradgVol", "PriceChangePct", "RVOL", "AvgVolume20D",
    ])
    historical = []
    trend = scanner.calculate_trend(empty.copy(), historical)
    assert trend.empty and "EMA44" in trend.columns and "TckrSymb" in trend.columns
    setup = scanner.calculate_breakout_pullback(trend.copy(), historical)
    assert setup.empty and "BreakoutStatus" in setup.columns and "TckrSymb" in setup.columns
    sr = scanner.calculate_support_resistance(setup.copy(), historical)
    assert sr.empty and "SRSupport" in sr.columns and "TckrSymb" in sr.columns


def test_ema44_analysis_is_descriptive_and_does_not_reject_not_near_candidates():
    dates = pd.bdate_range("2026-07-01", periods=60)
    close = [100 + i * 0.45 + ((i % 4) - 1.5) * 0.12 for i in range(60)]
    history = pd.DataFrame({
        "TckrSymb": ["ABC"] * 60,
        "Date": dates,
        "OpnPric": [value - 0.1 for value in close],
        "HghPric": [value + 0.7 for value in close],
        "LwPric": [value - 0.6 for value in close],
        "ClsPric": close,
        "TtlTradgVol": [1500] * 60,
    })
    candidate = pd.DataFrame([{
        "TckrSymb": "ABC", "ClsPric": close[-1], "RVOL": 1.5,
        "AvgVolume20D": 1000, "TtlTradgVol": 1500,
        "CandidateScreenStatus": "PASS", "AvgDelivery5D": 75.0,
        "DeliveryFilterStatus": "PASS_GE_60_PERCENT",
    }])
    analyzed = scanner.calculate_trend(candidate, [history])
    assert "EMA20" in analyzed.columns and "EMA44" in analyzed.columns
    assert "EMA50" not in analyzed.columns
    assert analyzed.iloc[0]["EMA44ProximityStatus"] in {"NEAR_EMA44", "NOT_NEAR_EMA44"}
    assert analyzed.iloc[0]["EMA44SignalStatus"] in {
        "BULLISH_BREAKOUT", "BEARISH_BREAKDOWN", "BULLISH_CROSS_NO_VOLUME_CONFIRMATION",
        "BEARISH_CROSS_NO_VOLUME_CONFIRMATION", "ABOVE_EMA44", "BELOW_EMA44", "AT_EMA44",
    }
    assert analyzed.iloc[0]["CandidateScreenStatus"] == "PASS"
    assert pd.notna(analyzed.iloc[0]["PriceChange5D"])


def test_telegram_digest_includes_delivery_ema44_and_near_status_without_rejection():
    row = {
        "TckrSymb": "ABC", "ClsPric": 110.0, "PriceChangePct": 2.5,
        "PriceChange5D": 7.5, "TtlTradgVol": 2500, "AvgVolume20D": 1000,
        "RVOL": 2.5, "AvgDelivery5D": 72.5, "DeliveryFilterStatus": "PASS_GE_60_PERCENT",
        "Delivery_2026-10-13": 70.0, "Delivery_2026-10-12": 75.0,
        "EMA20": 105.0, "EMA44": 102.0, "EMA44DistancePct": 7.84,
        "EMA44Trend": "RISING", "EMA44Position": "ABOVE_EMA44",
        "EMA44ProximityStatus": "NOT_NEAR_EMA44", "EMA44SignalStatus": "ABOVE_EMA44",
        "RSI14": 61.0, "ADX14": 25.0, "TrendClassification": "Bullish Trend",
        "PriceVolumeRelationship": "Positive", "CLV": 0.8,
        "BreakoutStatus": "Breakout", "PullbackStatus": "No Pullback",
        "SRSupport": 100.0, "SRResistance": 115.0, "BreakoutLevel": 115.0,
        "Sector": "Unknown", "SectorStrengthStatus": "WAIT_FOR_DATA", "MarketRegime": "MIXED",
        "NewsEvidenceStatus": "NO_DATA", "MandatoryConfirmationStatus": "WAIT_FOR_DATA",
        "IndependentConfirmationCategories": "PRICE_VOLUME", "NewsPrimarySourceVerified": False,
        "V8Score": 50, "EntryPricePlan": 110.0, "StopLossPlan": 100.0,
        "TargetPricePlan": 125.0, "RiskReward": 1.5, "ChaseStatus": "CLEAR",
        "EODWatchlistStatus": "WAIT_FOR_DATA", "EODLayerStatus": "WAIT_FOR_DATA",
        "CandidateScreenReasons": "SECTOR_WAIT_FOR_DATA",
    }
    lines = news_catalyst.build_marathi_digest(pd.DataFrame([row]), "2026-10-13", pd.DataFrame(), {"NSE": "available", "secondary": "available"})
    text = "\n".join(lines)
    for expected in ("ABC", "5D Change", "Average Delivery", "EMA44", "NOT_NEAR_EMA44", "does not reject", "WAIT_FOR_DATA"):
        assert expected in text, expected

def test_next_day_pipeline_only_receives_final_watch_candidates():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        layers.INPUT_DIR = tmp_path / "inputs"
        layers.OUTPUT_DIR = tmp_path / "outputs"
        base = {
            "SetupType": "Breakout", "EODWatchlistStatus": "WATCH",
            "EODLayerStatus": "PASS", "MandatoryConfirmationStatus": "PASS",
            "DeliveryFilterStatus": "PASS_GE_60_PERCENT", "CandidateScreenStatus": "PASS",
        }
        rows = [
            {"TckrSymb": "GOOD", **base},
            {"TckrSymb": "WAIT", **{**base, "EODWatchlistStatus": "WAIT_FOR_DATA", "EODLayerStatus": "WAIT_FOR_DATA"}},
            {"TckrSymb": "REJECT", **{**base, "CandidateScreenStatus": "REJECT"}},
        ]
        report = layers.validate_next_day(pd.DataFrame(rows), "2026-10-09")
        assert report["TckrSymb"].tolist() == ["GOOD"], report.to_dict("records")
        assert report.iloc[0]["NextDayStatus"] == "WAIT_FOR_DATA"  # bars are absent


def test_risk_reward_requires_structural_resistance_and_never_synthesizes_2r():
    result = layers._calculate_structural_risk_reward(100.0, 95.0, float("nan"))
    assert result["RiskRewardStatus"] == "WAIT_FOR_DATA", result
    assert pd.isna(result["TargetPricePlan"]), result
    assert result["TargetSource"] == "WAIT_FOR_DATA", result
    assert "synthetic 2R target prohibited" in result["RiskRewardReason"], result


def test_structural_resistance_rr_passes_only_when_at_least_2r():
    passing = layers._calculate_structural_risk_reward(100.0, 95.0, 110.0)
    assert passing["RiskRewardStatus"] == "PASS", passing
    assert passing["TargetPricePlan"] == 110.0, passing
    assert passing["TargetSource"] == "SR_RESISTANCE", passing
    assert passing["RiskReward"] == 2.0, passing

    failing = layers._calculate_structural_risk_reward(100.0, 95.0, 108.0)
    assert failing["RiskRewardStatus"] == "FAIL", failing
    assert failing["RiskReward"] == 1.6, failing
    assert failing["TargetSource"] == "SR_RESISTANCE", failing


def test_structural_risk_reward_rejects_invalid_entry_or_stop():
    for entry, stop, resistance in [(100.0, 100.0, 120.0), (100.0, 105.0, 120.0), (float("nan"), 95.0, 120.0)]:
        result = layers._calculate_structural_risk_reward(entry, stop, resistance)
        assert result["RiskRewardStatus"] == "WAIT_FOR_DATA", result
        assert pd.isna(result["TargetPricePlan"]), result


def test_source_code_uses_greater_than_or_equal_60_delivery_status():
    source = Path("delivery_filter.py").read_text(encoding="utf-8")
    assert "PASS_GE_60_PERCENT" in source
    assert "PASS_GE_60_PERCENT" in source
    assert "FILTERED_OUT_LT_60_PERCENT" in source
    assert "FILTERED_OUT_LT_60_PERCENT" in source
    layer_source = Path("v8_layers_14_41.py").read_text(encoding="utf-8")
    assert "PASS_GE_60_PERCENT" in layer_source
    assert "PASS_GE_60_PERCENT" in layer_source


def _technical_history_for_setup(last_close=120.0, last_open=119.0, last_high=120.5, last_low=118.5, last_volume=3000):
    dates = pd.bdate_range("2026-07-01", periods=60)
    close = [100.0 + i * 0.32 for i in range(59)]
    # Make the prior 20-session resistance level predictable.
    rows = []
    for i, day in enumerate(dates[:-1]):
        c = close[i]
        rows.append({
            "TckrSymb": "ABC", "Date": day,
            "OpnPric": c - 0.1, "HghPric": c + 0.5,
            "LwPric": c - 0.5, "ClsPric": c,
            "TtlTradgVol": 1000,
        })
    rows.append({
        "TckrSymb": "ABC", "Date": dates[-1],
        "OpnPric": last_open, "HghPric": last_high,
        "LwPric": last_low, "ClsPric": last_close,
        "TtlTradgVol": last_volume,
    })
    return pd.DataFrame(rows)


def test_breakout_requires_strong_clv_above_075():
    history = _technical_history_for_setup(
        last_close=119.9, last_open=119.0, last_high=120.5, last_low=118.5, last_volume=3000
    )
    candidate = pd.DataFrame([{
        "TckrSymb": "ABC", "EMA20": 118.0, "EMA44": 115.0,
        "TrendClassification": "Bullish Trend", "LowVolumeDays5D": 1,
    }])
    result = scanner.calculate_breakout_pullback(candidate, [history])
    row = result.iloc[0]
    assert row["BreakoutStatus"] != "Breakout" and row["BreakoutStatus"] != "Strong Breakout", row.to_dict()
    assert row["SetupType"] in {"Pre-Breakout", "No Clear Setup"}, row.to_dict()


def test_pullback_requires_volume_contraction_and_bullish_reversal():
    dates = pd.bdate_range("2026-07-01", periods=60)
    closes = [108.0] * 59
    closes[49] = 110.0  # recent high in the previous 20 sessions
    closes[58] = 106.6  # prior close below today's bullish reversal close
    rows = []
    for i, day in enumerate(dates[:-1]):
        c = closes[i]
        rows.append({
            "TckrSymb": "ABC", "Date": day,
            "OpnPric": c - 0.1, "HghPric": c + (0.5 if i == 49 else 0.2),
            "LwPric": c - 0.5, "ClsPric": c, "TtlTradgVol": 1000,
        })
    rows.append({
        "TckrSymb": "ABC", "Date": dates[-1],
        "OpnPric": 106.5, "HghPric": 107.8, "LwPric": 105.8,
        "ClsPric": 107.0, "TtlTradgVol": 1000,
    })
    history = pd.DataFrame(rows)
    candidate = pd.DataFrame([{
        "TckrSymb": "ABC", "EMA20": 106.8, "EMA44": 106.7,
        "TrendClassification": "Bullish Trend", "LowVolumeDays5D": 3,
    }])
    result = scanner.calculate_breakout_pullback(candidate, [history])
    row = result.iloc[0]
    assert row["PullbackStatus"] == "Strong Pullback", row.to_dict()
    assert row["SetupType"] == "Pullback", row.to_dict()

    # Without the required three low-volume days, it remains informational only.
    candidate.loc[0, "LowVolumeDays5D"] = 2
    result = scanner.calculate_breakout_pullback(candidate, [history])
    row = result.iloc[0]
    assert row["PullbackStatus"] == "Possible Pullback", row.to_dict()
    assert row["SetupType"] == "Possible Pullback", row.to_dict()

    # A red candle is not a confirmed bullish reversal even when volume contracts.
    candidate.loc[0, "LowVolumeDays5D"] = 3
    bearish_history = history.copy()
    bearish_history.loc[bearish_history.index[-1], "OpnPric"] = 107.2
    result = scanner.calculate_breakout_pullback(candidate, [bearish_history])
    row = result.iloc[0]
    assert row["PullbackStatus"] == "Possible Pullback", row.to_dict()
    assert row["SetupType"] == "Possible Pullback", row.to_dict()


def test_negative_relative_strength_is_warning_not_standalone_rejection():
    with tempfile.TemporaryDirectory() as tmp:
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            row = {
                "TckrSymb": "ABC", "DeliveryFilterStatus": "PASS_GE_60_PERCENT",
                "RVOLStatus": "PASS", "RVOL": 2.0, "SetupType": "Breakout",
                "TrendClassification": "Bullish Trend", "CLV": 0.80,
                "PriceVolumeRelationship": "Positive", "RelativeStrengthNifty": -0.5,
                "LowVolumeDays5D": 1, "BreakoutStatus": "Breakout",
                "PullbackStatus": "No Pullback", "SRSupport": 100.0,
                "SRResistance": 120.0, "PriceChangePct": 1.0,
            }
            selected = scanner.select_top20_analysis_candidates(pd.DataFrame([row]), "2026-10-14")
            assert selected.iloc[0]["CandidateScreenStatus"] == "PASS", selected.to_dict("records")
            assert "UNDERPERFORMS_NIFTY_SCORE_PENALTY" in selected.iloc[0]["CandidateScreenWarnings"]
            assert "UNDERPERFORMS_NIFTY" not in selected.iloc[0]["CandidateScreenReasons"]
        finally:
            os.chdir(old_cwd)



def test_mixed_improving_trend_does_not_confirm_core_setup():
    with tempfile.TemporaryDirectory() as tmp:
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            row = {
                "TckrSymb": "ABC", "DeliveryFilterStatus": "PASS_GE_60_PERCENT",
                "RVOLStatus": "PASS", "RVOL": 2.0, "SetupType": "Breakout",
                "TrendClassification": "Mixed / Improving", "CLV": 0.80,
                "PriceVolumeRelationship": "Positive", "RelativeStrengthNifty": 1.0,
                "LowVolumeDays5D": 1, "BreakoutStatus": "Breakout",
                "PullbackStatus": "No Pullback", "SRSupport": 100.0,
                "SRResistance": 120.0, "PriceChangePct": 1.0,
            }
            selected = scanner.select_top20_analysis_candidates(pd.DataFrame([row]), "2026-10-14")
            assert selected.iloc[0]["CandidateScreenStatus"] == "REJECT", selected.to_dict("records")
            assert "TREND_NOT_BULLISH" in selected.iloc[0]["CandidateScreenReasons"]
        finally:
            os.chdir(old_cwd)


def test_breakout_selector_rejects_clv_equal_to_075():
    with tempfile.TemporaryDirectory() as tmp:
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            row = {
                "TckrSymb": "ABC", "DeliveryFilterStatus": "PASS_GE_60_PERCENT",
                "RVOLStatus": "PASS", "RVOL": 2.0, "SetupType": "Breakout",
                "TrendClassification": "Bullish Trend", "CLV": 0.75,
                "PriceVolumeRelationship": "Positive", "RelativeStrengthNifty": 1.0,
                "LowVolumeDays5D": 1, "BreakoutStatus": "Breakout",
                "PullbackStatus": "No Pullback", "SRSupport": 100.0,
                "SRResistance": 120.0, "PriceChangePct": 1.0,
            }
            selected = scanner.select_top20_analysis_candidates(pd.DataFrame([row]), "2026-10-14")
            assert selected.iloc[0]["CandidateScreenStatus"] == "REJECT", selected.to_dict("records")
            assert "BREAKOUT_CANDLE_NOT_STRONG_CLV_NOT_GT_0_75" in selected.iloc[0]["CandidateScreenReasons"]
        finally:
            os.chdir(old_cwd)



def test_nse_naive_rss_timestamp_is_interpreted_as_ist_for_eod_window():
    item = news_catalyst.ET.fromstring(
        "<item><pubDate>16-Oct-2026 21:49:19</pubDate>"
        "<title>Official filing timestamp</title></item>"
    )
    stamp = news_catalyst._published(item)
    assert stamp is not None
    assert stamp.isoformat() == "2026-10-16T16:19:19+00:00", stamp
    # The approved next-morning window ends at 22:00 IST (16:30 UTC) on EOD day.
    assert stamp <= pd.Timestamp("2026-10-16T22:00:00+05:30").tz_convert("UTC").to_pydatetime()

def test_nse_announcement_api_normalizer_uses_official_fields_and_symbol_filter():
    class FakeResponse:
        def __init__(self, payload=None):
            self.payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload

    class FakeSession:
        def __init__(self):
            self.headers = {}
            self.calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if "corporate-filings-announcements" in url:
                return FakeResponse([])
            return FakeResponse([
                {"symbol": "ABC", "desc": "ABC Limited receives order", "an_dt": "16-Oct-2026 15:00:00", "sm_name": "ABC Limited", "attchmntText": "Company informed NSE", "attchmntFile": "https://nsearchives.nseindia.com/a.pdf", "seq_id": "123"},
                {"symbol": "XYZ", "desc": "Wrong issuer", "an_dt": "16-Oct-2026 15:00:00"},
            ])
    fake = FakeSession()
    original_session = news_catalyst.requests.Session
    try:
        news_catalyst.requests.Session = lambda: fake
        items = news_catalyst._nse_announcement_api_items("ABC", "2026-10-10", "2026-10-16")
    finally:
        news_catalyst.requests.Session = original_session
    assert len(items) == 1
    assert news_catalyst._item_text(items[0], "title") == "ABC Limited receives order"
    assert news_catalyst._item_text(items[0], "symbol") == "ABC"
    assert news_catalyst._item_text(items[0], "eventid") == "123"
    stamp = news_catalyst._published(items[0])
    assert stamp.isoformat() == "2026-10-16T09:30:00+00:00", stamp
    assert fake.calls[1][0] == "https://www.nseindia.com/api/corporate-announcements", fake.calls[1][0]
    assert fake.calls[1][1]["params"]["from_date"] == "10-10-2026"
    assert fake.calls[1][1]["params"]["to_date"] == "16-10-2026"


def test_nse_api_raw_diagnostics_report_status_payload_fields_and_counts():
    from contextlib import redirect_stdout
    from io import StringIO
    class FakeResponse:
        def __init__(self, payload=None, content=b"{}", status_code=200, headers=None):
            self.payload = payload
            self.content = content
            self.status_code = status_code
            self.headers = headers or {"Content-Type": "application/json"}
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload

    class FakeSession:
        def __init__(self):
            self.headers = {}
            self.calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if "corporate-filings-announcements" in url:
                return FakeResponse([], content=b"<html>landing</html>", headers={"Content-Type": "text/html"})
            return FakeResponse([
                {"symbol": "ABC", "desc": "ABC receives an order", "an_dt": "16-Oct-2026 15:00:00", "seq_id": "123"},
                {"symbol": "XYZ", "desc": "Different issuer", "an_dt": "16-Oct-2026 15:01:00", "seq_id": "124"},
            ], content=b'json-response-body', headers={"Content-Type": "application/json; charset=utf-8"})

    fake = FakeSession()
    original_session = news_catalyst.requests.Session
    captured = StringIO()
    try:
        news_catalyst.requests.Session = lambda: fake
        with redirect_stdout(captured):
            items = news_catalyst._nse_announcement_api_items("ABC", "2026-10-10", "2026-10-16")
    finally:
        news_catalyst.requests.Session = original_session
    output = captured.getvalue()
    assert len(items) == 1
    assert "NSE_API_LANDING symbol=ABC status=200 content_type='text/html'" in output, output
    assert "NSE_API_RAW_RESPONSE symbol=ABC status=200 content_type='application/json; charset=utf-8'" in output, output
    assert "payload_type=list raw_records=2 dict_records=2" in output, output
    assert "field_names=['an_dt', 'desc', 'seq_id', 'symbol']" in output, output
    assert "normalized_items=1 symbol_mismatch=1" in output, output


def test_news_window_eod_uses_five_calendar_days_and_2200_ist_cutoff():
    start_utc, end_utc, start_ist, end_ist, mode = news_catalyst._news_window_bounds(
        "2026-10-16", scan_mode="EOD", now="2026-10-16T22:10:00+05:30"
    )
    assert mode == "EOD"
    assert start_ist.strftime("%Y-%m-%d %H:%M:%S %Z") == "2026-10-12 00:00:00 IST", start_ist
    assert end_ist.strftime("%Y-%m-%d %H:%M:%S %Z") == "2026-10-16 22:00:00 IST", end_ist
    assert (end_ist.normalize() - start_ist.normalize()).days == 4
    assert start_utc < end_utc


def test_news_window_premarket_covers_five_calendar_days_including_weekend_to_0915():
    start_utc, end_utc, start_ist, end_ist, mode = news_catalyst._news_window_bounds(
        "2026-10-16", scan_mode="PREMARKET", now="2026-10-19T09:05:00+05:30"
    )
    assert mode == "PREMARKET"
    assert start_ist.strftime("%Y-%m-%d %H:%M:%S %Z") == "2026-10-15 00:00:00 IST", start_ist
    assert end_ist.strftime("%Y-%m-%d %H:%M:%S %Z") == "2026-10-19 09:15:00 IST", end_ist
    assert start_utc < end_utc
    assert start_ist.date() <= pd.Timestamp("2026-10-17").date()  # weekend included
    assert end_ist.hour == 9 and end_ist.minute == 15


if __name__ == "__main__":
    tests = [
        test_3_confirmations_plus_separate_primary_source_gate,
        test_nse_announcement_api_normalizer_uses_official_fields_and_symbol_filter,
        test_nse_api_raw_diagnostics_report_status_payload_fields_and_counts,
        test_news_window_eod_uses_five_calendar_days_and_2200_ist_cutoff,
        test_news_window_premarket_covers_five_calendar_days_including_weekend_to_0915,
        test_nse_naive_rss_timestamp_is_interpreted_as_ist_for_eod_window,
        test_three_secondary_reposts_do_not_create_three_confirmations,
        test_untrusted_domain_cannot_be_primary_just_because_of_label,
        test_sector_mapping_uses_exact_official_nse_industry_fallbacks,
        test_delivery_average_category_passes_while_daily_category_fails,
        test_delivery_exactly_60_each_day_passes,
        test_delivery_below_60_rejects_and_incomplete_waits,
        test_news_gate_uses_category_a_average_status_and_keeps_category_b_separate,
        test_rvol_threshold_precedes_dual_delivery_in_scanner_source,
        test_empty_delivery_shortlist_keeps_merge_keys_through_technical_steps,
        test_ema44_analysis_is_descriptive_and_does_not_reject_not_near_candidates,
        test_telegram_digest_includes_delivery_ema44_and_near_status_without_rejection,
        test_next_day_pipeline_only_receives_final_watch_candidates,
        test_risk_reward_requires_structural_resistance_and_never_synthesizes_2r,
        test_structural_resistance_rr_passes_only_when_at_least_2r,
        test_structural_risk_reward_rejects_invalid_entry_or_stop,
        test_source_code_uses_greater_than_or_equal_60_delivery_status,
        test_breakout_requires_strong_clv_above_075,
        test_pullback_requires_volume_contraction_and_bullish_reversal,
        test_negative_relative_strength_is_warning_not_standalone_rejection,
        test_mixed_improving_trend_does_not_confirm_core_setup,
        test_breakout_selector_rejects_clv_equal_to_075,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print(f"PASS: all {len(tests)} V8 regression tests")
