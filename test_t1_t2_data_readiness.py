from __future__ import annotations
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
from t1_t2_data_readiness import resistance_levels, audit_signal_frame, official_sessions_after, load_price_cache

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
    def test_stop_intraday_touch_exits_at_stop(self):
        from t1_t2_data_readiness import evaluate_daily_stop_bar
        result = evaluate_daily_stop_bar({"OPEN":100,"HIGH":105,"LOW":89,"CLOSE":95},90)
        self.assertEqual(result["status"],"STOP_HIT")
        self.assertEqual(result["exit_price"],90)
        self.assertEqual(result["reason"],"INTRADAY_STOP_AT_STOP_PRICE")

    def test_gap_below_stop_exits_at_open(self):
        from t1_t2_data_readiness import evaluate_daily_stop_bar
        result = evaluate_daily_stop_bar({"OPEN":85,"HIGH":95,"LOW":80,"CLOSE":90},90)
        self.assertEqual(result["status"],"STOP_HIT")
        self.assertEqual(result["exit_price"],85)
        self.assertEqual(result["reason"],"GAP_THROUGH_STOP_AT_OPEN")

    def test_open_equal_stop_exits_at_stop(self):
        from t1_t2_data_readiness import evaluate_daily_stop_bar
        result = evaluate_daily_stop_bar({"OPEN":90,"HIGH":95,"LOW":88,"CLOSE":92},90)
        self.assertEqual(result["exit_price"],90)

    def test_no_stop_touch(self):
        from t1_t2_data_readiness import evaluate_daily_stop_bar
        result = evaluate_daily_stop_bar({"OPEN":100,"HIGH":105,"LOW":91,"CLOSE":102},90)
        self.assertEqual(result["status"],"NO_STOP_HIT")

    def test_stop_first_when_same_day_high_also_reaches_target(self):
        from t1_t2_data_readiness import evaluate_daily_stop_bar
        result = evaluate_daily_stop_bar({"OPEN":100,"HIGH":125,"LOW":89,"CLOSE":110},90)
        self.assertEqual(result["status"],"STOP_HIT")
        self.assertEqual(result["exit_price"],90)
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
            pd.DataFrame([{"BizDt":"2026-11-09","SYMBOL":"TEST","SERIES":"EQ","OPEN":10,"HIGH":12,"LOW":9,"CLOSE":11}]).to_csv(path,index=False)
            records, errors = load_price_cache(Path(temp))
            self.assertEqual(errors, [])
            self.assertEqual(records[("TEST", pd.Timestamp("2026-11-09").date())]["CLOSE"], 11)

    def test_invalid_ohlc_file_is_rejected_not_loaded(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "bhavcopy_20261109.csv"
            pd.DataFrame([{"BizDt":"2026-11-09","SYMBOL":"TEST","SERIES":"EQ","OPEN":10,"HIGH":8,"LOW":9,"CLOSE":11}]).to_csv(path,index=False)
            records, errors = load_price_cache(Path(temp))
            self.assertEqual(records, {})
            self.assertTrue(any(item.startswith("INVALID_OHLC:") for item in errors))

    def test_t1_and_t2_data_readiness_is_horizon_specific(self):
        signal_date = "2026-10-28"
        dates = official_sessions_after(signal_date, 20)
        prices = {("TEST", day): {"OPEN": 100.0, "HIGH": 125.0, "LOW": 95.0, "CLOSE": 110.0} for day in dates}
        frame = pd.DataFrame([{
            "EODDate": signal_date, "Symbol": "TEST", "EntryPricePlan": 100.0,
            "StopLossPlan": 90.0, "TargetPricePlan": 110.0, "TargetSource": "SR_20D_HIGH",
            "SR20DHigh": 110.0, "SR50DHigh": 120.0,
        }])
        result = audit_signal_frame(frame, prices, "fixture.csv").iloc[0]
        self.assertEqual(result["T1DataReady5D"], "DATA_READY")
        self.assertEqual(result["T2DataReady5D"], "DATA_READY")
        self.assertEqual(result["T1DataReady20D"], "DATA_READY")
        self.assertEqual(result["T2DataReady20D"], "DATA_READY")
        self.assertEqual(result["EntryExecutionRule"], "NEXT_OFFICIAL_SESSION_OPEN")
        self.assertEqual(result["EntryExecutionPrice"], 100.0)
        self.assertEqual(result["EntryExecutionStatus"], "ENTRY_READY")

    def test_targets_are_above_actual_next_open_fill(self):
        signal_date = "2026-10-28"
        dates = official_sessions_after(signal_date, 20)
        prices = {("TEST", day): {"OPEN": 115.0 if i == 0 else 100.0, "HIGH": 135.0, "LOW": 95.0, "CLOSE": 110.0} for i, day in enumerate(dates)}
        frame = pd.DataFrame([{
            "EODDate": signal_date, "Symbol": "TEST", "EntryPricePlan": 100.0,
            "StopLossPlan": 90.0, "TargetPricePlan": 110.0, "TargetSource": "SR_20D_HIGH",
            "SR20DHigh": 110.0, "SR50DHigh": 120.0, "SR100DHigh": 130.0,
        }])
        result = audit_signal_frame(frame, prices, "fixture.csv").iloc[0]
        self.assertEqual(result["EntryExecutionPrice"], 115.0)
        self.assertEqual(result["Target1"], 120.0)
        self.assertEqual(result["Target2"], 130.0)

    def test_next_open_at_or_below_stop_blocks_entry(self):
        signal_date = "2026-10-28"
        dates = official_sessions_after(signal_date, 20)
        prices = {("TEST", day): {"OPEN": 89.0 if i == 0 else 100.0, "HIGH": 125.0, "LOW": 85.0, "CLOSE": 95.0} for i, day in enumerate(dates)}
        frame = pd.DataFrame([{
            "EODDate": signal_date, "Symbol": "TEST", "EntryPricePlan": 100.0,
            "StopLossPlan": 90.0, "TargetPricePlan": 110.0, "TargetSource": "SR_20D_HIGH",
            "SR20DHigh": 110.0, "SR50DHigh": 120.0,
        }])
        result = audit_signal_frame(frame, prices, "fixture.csv").iloc[0]
        self.assertEqual(result["EntryExecutionStatus"], "WAIT_FOR_DATA")
        self.assertEqual(result["T1DataReady5D"], "WAIT_FOR_DATA")
        self.assertIn("NEXT_SESSION_OPEN_AT_OR_BELOW_STOP", result["ReadinessReasons"])

    def test_missing_next_session_open_blocks_entry_readiness(self):
        signal_date = "2026-10-28"
        dates = official_sessions_after(signal_date, 20)
        prices = {("TEST", day): {"OPEN": 100.0, "HIGH": 125.0, "LOW": 95.0, "CLOSE": 110.0} for day in dates[1:]}
        frame = pd.DataFrame([{
            "EODDate": signal_date, "Symbol": "TEST", "EntryPricePlan": 100.0,
            "StopLossPlan": 90.0, "TargetPricePlan": 110.0, "TargetSource": "SR_20D_HIGH",
            "SR20DHigh": 110.0, "SR50DHigh": 120.0,
        }])
        result = audit_signal_frame(frame, prices, "fixture.csv").iloc[0]
        self.assertEqual(result["EntryExecutionStatus"], "WAIT_FOR_DATA")
        self.assertEqual(result["T1DataReady5D"], "WAIT_FOR_DATA")
        self.assertEqual(result["T2DataReady5D"], "WAIT_FOR_DATA")

if __name__ == "__main__":
    unittest.main()
