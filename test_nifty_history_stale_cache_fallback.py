import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import volume_gainer as vg


class NiftyHistoryStaleCacheFallbackTests(unittest.TestCase):
    def _cache(self, root, dates):
        frame = pd.DataFrame({
            "Date": pd.to_datetime(dates),
            "NiftyClose": [22000.0 + i for i in range(len(dates))],
        })
        path = root / "nifty50_index_history.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%d")
        return frame

    def _patched_cache_and_provider(self, root, provider):
        return (
            patch.object(vg, "DATA_CACHE_DIR", str(root)),
            patch.object(vg, "NIFTY_HISTORY_CACHE", str(root / "nifty50_index_history.csv")),
            patch.object(vg, "fetch_nifty_index_history", **provider),
        )

    def test_stale_but_sufficient_cache_survives_provider_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = pd.bdate_range("2026-08-01", periods=60)
            original = self._cache(root, dates)
            p1, p2, p3 = self._patched_cache_and_provider(
                root, {"side_effect": TimeoutError("provider down")}
            )
            with p1, p2, p3:
                result = vg.load_nifty_index_history(pd.Timestamp("2026-11-08"))
            self.assertEqual(len(result), 60)
            self.assertEqual(pd.to_datetime(result["Date"]).max().normalize(), dates.max().normalize())
            self.assertEqual(len(pd.read_csv(root / "nifty50_index_history.csv")), len(original))

    def test_exact_date_refresh_replaces_stale_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = pd.bdate_range("2026-08-01", periods=60)
            self._cache(root, dates)
            target = pd.Timestamp("2026-11-08")
            downloaded = pd.DataFrame({"Date": [target], "NiftyClose": [24500.0]})
            p1, p2, p3 = self._patched_cache_and_provider(
                root, {"return_value": downloaded}
            )
            with p1, p2, p3:
                result = vg.load_nifty_index_history(target)
            self.assertEqual(pd.to_datetime(result["Date"]).max().normalize(), target.normalize())
            cached = pd.read_csv(root / "nifty50_index_history.csv")
            self.assertEqual(pd.to_datetime(cached["Date"]).max().normalize(), target.normalize())

    def test_insufficient_cache_and_provider_failure_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = pd.bdate_range("2026-10-01", periods=10)
            self._cache(root, dates)
            p1, p2, p3 = self._patched_cache_and_provider(
                root, {"side_effect": TimeoutError("provider down")}
            )
            with p1, p2, p3:
                with self.assertRaisesRegex(RuntimeError, "only 10 valid closes"):
                    vg.load_nifty_index_history(pd.Timestamp("2026-11-08"))

    def test_stale_nifty_history_marks_relative_strength_wait_instead_of_crashing(self):
        dates = pd.bdate_range("2026-09-01", periods=25)
        historical = [pd.DataFrame({
            "Date": dates,
            "TckrSymb": ["TEST"] * len(dates),
            "ClsPric": [100.0 + i for i in range(len(dates))],
        })]
        current = pd.DataFrame([{"TckrSymb": "TEST", "ClsPric": 125.0}])
        stale_nifty = pd.DataFrame({
            "Date": pd.bdate_range("2026-08-01", periods=60),
            "NiftyClose": [22000.0 + i for i in range(60)],
        })
        result = vg.calculate_relative_strength_nifty(
            current, historical, stale_nifty, pd.Timestamp("2026-11-08")
        )
        self.assertTrue(pd.isna(result.loc[0, "NiftyReturn20D"]))
        self.assertTrue(pd.isna(result.loc[0, "RelativeStrengthNifty"]))
        self.assertEqual(result.loc[0, "RSNiftyClassification"], "Insufficient Data")


if __name__ == "__main__":
    unittest.main()
