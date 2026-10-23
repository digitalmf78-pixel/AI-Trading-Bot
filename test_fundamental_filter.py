import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fundamental_filter import apply_fundamental_filter, INPUT_COLUMNS, METRIC_COLUMNS


CONFIG = {
    "min_revenue_growth_pct": 0,
    "min_profit_growth_pct": 0,
    "min_roe_pct": 10,
    "min_roce_pct": 10,
    "max_debt_to_equity": 1.5,
    "min_interest_coverage": 2,
    "require_positive_operating_cash_flow": True,
    "require_positive_free_cash_flow": True,
    "acceptable_earnings_quality_status": ["PASS"],
    "acceptable_valuation_status": ["PASS"],
    "max_data_age_days": 450,
}


def good_record(symbol="ABC"):
    return {
        "TckrSymb": symbol, "AsOfDate": "2026-09-30", "Source": "Official filing",
        "SourceURL": "https://example.com/filing", "RevenueGrowthPct": 12,
        "ProfitGrowthPct": 14, "ROEPercent": 16, "ROCEPercent": 18,
        "DebtToEquity": 0.4, "InterestCoverage": 6,
        "OperatingCashFlowINR": 1000000, "FreeCashFlowINR": 500000,
        "EarningsQualityStatus": "PASS", "ValuationStatus": "PASS",
    }


class FundamentalFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.metrics = self.root / "metrics.csv"
        self.thresholds = self.root / "thresholds.json"
        self.metrics.parent.mkdir(parents=True, exist_ok=True)
        self.thresholds.write_text(json.dumps(CONFIG), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_filter(self, records):
        pd.DataFrame(records, columns=INPUT_COLUMNS).to_csv(self.metrics, index=False)
        candidates = pd.DataFrame({"TckrSymb": ["ABC"]})
        result, audit = apply_fundamental_filter(candidates, "2026-10-19", self.metrics, self.thresholds)
        return result.iloc[0]

    def test_complete_qualified_record_passes(self):
        self.assertEqual(self.run_filter([good_record()])["FundamentalStatus"], "COMPLETE")

    def test_missing_record_waits(self):
        row = self.run_filter([])
        self.assertEqual(row["FundamentalStatus"], "MISSING_DATA")
        self.assertIn("FUNDAMENTAL_RECORD_MISSING", row["FundamentalReason"])

    def test_missing_metric_waits(self):
        record = good_record(); record["ROCEPercent"] = None
        row = self.run_filter([record])
        self.assertEqual(row["FundamentalStatus"], "PARTIAL_DATA")

    def test_weak_metric_is_collected_not_rejected(self):
        record = good_record(); record["DebtToEquity"] = 3
        row = self.run_filter([record])
        self.assertEqual(row["FundamentalStatus"], "COMPLETE")
        self.assertEqual(row["FundamentalAssessmentStatus"], "NOT_SHORTLISTED_YET")

    def test_unconfigured_thresholds_do_not_block_collection(self):
        self.thresholds.write_text(json.dumps({key: None for key in CONFIG}), encoding="utf-8")
        row = self.run_filter([good_record()])
        self.assertEqual(row["FundamentalStatus"], "COMPLETE")

    def test_future_financial_date_waits(self):
        record = good_record(); record["AsOfDate"] = "2026-12-31"
        row = self.run_filter([record])
        self.assertEqual(row["FundamentalStatus"], "PARTIAL_DATA")

    def test_duplicate_records_are_flagged_but_not_removed(self):
        row = self.run_filter([good_record(), good_record()])
        self.assertEqual(row["FundamentalStatus"], "PARTIAL_DATA")
        self.assertIn("DUPLICATE_FUNDAMENTAL_RECORDS", row["FundamentalReason"])


if __name__ == "__main__":
    unittest.main()


def test_fundamental_score_fields_are_written_by_filter_source():
    from pathlib import Path
    source = Path("fundamental_filter.py").read_text(encoding="utf-8")
    assert "FundamentalScore" in source
    assert "FundamentalRank" in source
    assert "Equal-weight percentile mean" in source
