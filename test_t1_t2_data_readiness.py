from __future__ import annotations
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
from t1_t2_data_readiness import resistance_levels, audit_signal_frame, official_sessions_after, load_price_cache, load_price_cache

class ResistanceTests(unittest.TestCase):
    def test_two_distinct_levels_sorted_and_deduplicated(self):
        row = pd.Series({"TargetPricePlan":120.0,"TargetSource":"SR_RESISTANCE",
                         "SRResistance":120.0,"SRSwingHigh":130.0,"SR20DHigh":115.0})
        self.assertEqual(resistance_levels(row,100.0),
                         [(115.0,"SR_20D_HIGH"),(120.0,"SR_RESISTANCE"),(130.0,"SR_SWING_HIGH")])
    def test_levels_at_or_below_entry_excluded(self):
        row = pd.Series({"SRResistance":100.0,"SRSwingHigh":99.0,"SR20DHigh":110.0})
        self.assertEqual(resistance_levels(row,100.0),[(110.0,"SR_20D_HIGH")])
    def test_no_synthetic_second_target(self):
        row = pd.Series({"TargetPricePlan":120.0,"TargetSource":"SR_RESISTANCE"})
        self.assertEqual(len(resistance_levels(row,100.0)),1)

class ReadinessTests(unittest.TestCase):
    def test_missing_stop_and_t2_fail_closed(self):
        frame = pd.DataFrame([{"EODDate":"2026-11-10","Symbol":"TEST","EntryPricePlan":100.0,
                               "TargetPricePlan":120.0,"TargetSource":"SR_RESISTANCE"}])
        result = audit_signal_frame(frame,{},"fixture.csv").iloc[0]
        self.assertEqual(result["ReadinessStatus"],"WAIT_FOR_DATA")
        self.assertIn("STOP_MISSING_OR_INVALID",result["ReadinessReasons"])
        self.assertIn("T2_DISTINCT_VERIFIED_RESISTANCE_MISSING",result["ReadinessReasons"])
    def test_official_sessions_after_signal_date(self):
        dates = official_sessions_after("2026-11-13",2)
        self.assertEqual(len(dates),2)
        self.assertGreater(dates[0],pd.Timestamp("2026-11-13").date())

    def test_canonical_bhavcopy_filename_and_ohlc_are_loaded(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "bhavcopy_20261109.csv"
            pd.DataFrame([{"SYMBOL":"TEST","SERIES":"EQ","OPEN":10,"HIGH":12,"LOW":9,"CLOSE":11}]).to_csv(path,index=False)
            records, errors = load_price_cache(Path(temp))
            self.assertEqual(errors, [])
            self.assertEqual(records[("TEST", pd.Timestamp("2026-11-09").date())]["CLOSE"], 11)

    def test_invalid_ohlc_file_is_rejected_not_loaded(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "bhavcopy_20261109.csv"
            pd.DataFrame([{"SYMBOL":"TEST","SERIES":"EQ","OPEN":10,"HIGH":8,"LOW":9,"CLOSE":11}]).to_csv(path,index=False)
            records, errors = load_price_cache(Path(temp))
            self.assertEqual(records, {})
            self.assertTrue(any(item.startswith("INVALID_OHLC:") for item in errors))

if __name__ == "__main__":
    unittest.main()
