import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import research_free_fundamental_validation as collector


class FundamentalResearchCollectorTests(unittest.TestCase):
    def test_period_validation_preserves_explicit_labels(self):
        self.assertTrue(collector.valid_period("ROEPercent", "Mar 2026"))
        self.assertTrue(collector.valid_period("ROEPercent", "2026-09-30"))
        self.assertTrue(collector.valid_period("ROEPercent", "Q2 FY 2026"))
        self.assertFalse(collector.valid_period("ROEPercent", "0"))
        self.assertFalse(collector.valid_period("ROEPercent", ""))
        self.assertFalse(collector.valid_period("ROEPercent", "FY2025->FY2026"))

    def test_growth_comparison_period_is_only_valid_for_growth_metrics(self):
        self.assertTrue(collector.valid_period("RevenueGrowthPct", "FY2025->FY2026"))
        self.assertTrue(collector.valid_period("ProfitGrowthPct", "FY 2025 -> FY 2026"))
        self.assertFalse(collector.valid_period("ROEPercent", "FY2025->FY2026"))


    def test_existing_research_metrics_are_not_requested_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "research.csv"
            pd.DataFrame([{
                "Symbol": "ABC", "Metric": "ROEPercent", "Value": "18.2",
                "FinancialPeriod": "2026-09-30",
            }, {
                "Symbol": "ABC", "Metric": "EPS", "Value": "2.4",
                "FinancialPeriod": "0",
            }]).to_csv(cache, index=False)
            with patch.object(collector, "PRODUCTION_CACHE", Path(tmp) / "no-production.csv"), \
                 patch.object(collector, "CACHE_PATH", cache):
                found = collector.load_existing_metric_map()
            self.assertIn("ROEPercent", found["ABC"])
            self.assertNotIn("EPS", found["ABC"])
            self.assertEqual(collector.CORE_METRICS - found["ABC"], collector.CORE_METRICS - {"ROEPercent"})

    def test_production_cache_is_read_only_source_for_existing_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            production = Path(tmp) / "production.csv"
            pd.DataFrame([{
                "TckrSymb": "XYZ", "ROEPercent": "12.5", "EPS": "",
            }]).to_csv(production, index=False)
            with patch.object(collector, "PRODUCTION_CACHE", production), \
                 patch.object(collector, "CACHE_PATH", Path(tmp) / "no-research.csv"):
                found = collector.load_existing_metric_map()
            self.assertEqual(found["XYZ"], {"ROEPercent"})
            self.assertTrue(production.exists())

    def test_collection_targets_only_symbols_with_no_accepted_metric(self):
        universe = ["AAA", "BBB", "CCC"]
        existing = {"AAA": {"ROEPercent"}, "BBB": {"PromoterHoldingPct"}}
        self.assertEqual(
            collector.symbols_missing_any_accepted_metric(universe, existing),
            ["CCC"],
        )

    def test_all_symbols_represented_means_no_initial_collection_targets(self):
        universe = ["AAA", "BBB"]
        existing = {"AAA": {"ROEPercent"}, "BBB": {"EPS"}}
        self.assertEqual(
            collector.symbols_missing_any_accepted_metric(universe, existing),
            [],
        )

    def test_diagnostics_prevent_retrying_symbols_with_no_metric_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp) / "diagnostics.csv"
            pd.DataFrame([{
                "Symbol": "NORESULT",
                "AttemptedAtUTC": "2026-11-14T04:00:00+00:00",
            }]).to_csv(diag, index=False)
            with patch.object(collector, "PRODUCTION_CACHE", Path(tmp) / "missing-production.csv"), \
                 patch.object(collector, "CACHE_PATH", Path(tmp) / "missing-cache.csv"), \
                 patch.object(collector, "DIAGNOSTICS_PATH", diag):
                attempts = collector.load_recent_attempts()
            self.assertIn("NORESULT", attempts)
            self.assertEqual(str(attempts["NORESULT"]), "2026-11-14 04:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
