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

def test_delivery_average_above_60_percent_passes():
    with tempfile.TemporaryDirectory() as tmp:
        delivery.AUDIT_DIR = Path(tmp)
        dates = [date(2026, 10, 9) - timedelta(days=i) for i in range(5)]
        values = [50.0, 55.0, 60.0, 65.0, 70.1]  # average = 60.02, strictly above 60
        sessions = []
        for day, value in zip(dates, values):
            sessions.append((day, pd.DataFrame([{"SYMBOL": "ABC", "SERIES": "EQ", "DELIV_PER": value}])))
        candidates = pd.DataFrame([{"TckrSymb": "ABC", "SctySrs": "EQ"}])
        qualified, audit = delivery.apply_delivery_filter(candidates, dates[0], sessions=sessions)
        assert len(qualified) == 1, audit.to_dict("records")
        assert audit.iloc[0]["DeliveryFilterStatus"] == "PASS_GT_60_PERCENT"
        assert abs(audit.iloc[0]["AvgDelivery5D"] - 60.02) < 1e-9


def test_delivery_average_exactly_60_percent_rejects():
    with tempfile.TemporaryDirectory() as tmp:
        delivery.AUDIT_DIR = Path(tmp)
        dates = [date(2026, 10, 9) - timedelta(days=i) for i in range(5)]
        values = [50.0, 55.0, 60.0, 65.0, 70.0]  # average = exactly 60
        sessions = [(day, pd.DataFrame([{"SYMBOL": "ABC", "SERIES": "EQ", "DELIV_PER": value}])) for day, value in zip(dates, values)]
        candidates = pd.DataFrame([{"TckrSymb": "ABC", "SctySrs": "EQ"}])
        qualified, audit = delivery.apply_delivery_filter(candidates, dates[0], sessions=sessions)
        assert qualified.empty
        assert audit.iloc[0]["DeliveryFilterStatus"] == "FILTERED_OUT_LE_60_PERCENT"
        assert abs(audit.iloc[0]["AvgDelivery5D"] - 60.0) < 1e-9

def test_delivery_below_60_rejects_and_incomplete_waits():
    with tempfile.TemporaryDirectory() as tmp:
        delivery.AUDIT_DIR = Path(tmp)
        dates = [date(2026, 10, 9) - timedelta(days=i) for i in range(5)]
        sessions = [(day, pd.DataFrame([{"SYMBOL": "ABC", "SERIES": "EQ", "DELIV_PER": 59.9}])) for day in dates]
        candidates = pd.DataFrame([{"TckrSymb": "ABC", "SctySrs": "EQ"}])
        qualified, audit = delivery.apply_delivery_filter(candidates, dates[0], sessions=sessions)
        assert qualified.empty
        assert audit.iloc[0]["DeliveryFilterStatus"] == "FILTERED_OUT_LE_60_PERCENT"
        qualified, audit = delivery.apply_delivery_filter(candidates, dates[0], sessions=sessions[:4])
        assert qualified.empty
        assert audit.iloc[0]["DeliveryFilterStatus"] == "WAIT_FOR_DATA"



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
        "DeliveryFilterStatus": "PASS_GT_60_PERCENT",
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
        "RVOL": 2.5, "AvgDelivery5D": 72.5, "DeliveryFilterStatus": "PASS_GT_60_PERCENT",
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
            "DeliveryFilterStatus": "PASS_GT_60_PERCENT", "CandidateScreenStatus": "PASS",
        }
        rows = [
            {"TckrSymb": "GOOD", **base},
            {"TckrSymb": "WAIT", **{**base, "EODWatchlistStatus": "WAIT_FOR_DATA", "EODLayerStatus": "WAIT_FOR_DATA"}},
            {"TckrSymb": "REJECT", **{**base, "CandidateScreenStatus": "REJECT"}},
        ]
        report = layers.validate_next_day(pd.DataFrame(rows), "2026-10-09")
        assert report["TckrSymb"].tolist() == ["GOOD"], report.to_dict("records")
        assert report.iloc[0]["NextDayStatus"] == "WAIT_FOR_DATA"  # bars are absent


def test_source_code_uses_strict_greater_than_60_delivery_status():
    source = Path("delivery_filter.py").read_text(encoding="utf-8")
    assert "PASS_GT_60_PERCENT" in source
    assert "PASS_GE_60_PERCENT" not in source
    assert "FILTERED_OUT_LE_60_PERCENT" in source
    assert "FILTERED_OUT_LT_60_PERCENT" not in source
    layer_source = Path("v8_layers_14_41.py").read_text(encoding="utf-8")
    assert "PASS_GT_60_PERCENT" in layer_source
    assert "PASS_GE_60_PERCENT" not in layer_source


if __name__ == "__main__":
    tests = [
        test_3_confirmations_plus_separate_primary_source_gate,
        test_three_secondary_reposts_do_not_create_three_confirmations,
        test_untrusted_domain_cannot_be_primary_just_because_of_label,
        test_sector_mapping_uses_exact_official_nse_industry_fallbacks,
        test_delivery_average_above_60_percent_passes,
        test_delivery_average_exactly_60_percent_rejects,
        test_delivery_below_60_rejects_and_incomplete_waits,
        test_ema44_analysis_is_descriptive_and_does_not_reject_not_near_candidates,
        test_telegram_digest_includes_delivery_ema44_and_near_status_without_rejection,
        test_next_day_pipeline_only_receives_final_watch_candidates,
        test_source_code_uses_strict_greater_than_60_delivery_status,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print(f"PASS: all {len(tests)} V8 regression tests")
