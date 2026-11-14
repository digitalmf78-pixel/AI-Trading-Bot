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
