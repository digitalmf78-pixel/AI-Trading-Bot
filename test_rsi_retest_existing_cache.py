import tempfile
import unittest
from pathlib import Path
import pandas as pd
import numpy as np
from rsi_retest_existing_cache import _read_price_cache, _read_delivery_cache, _delivery_status, _rsi, _signals_for_symbol, run_backtest

class ExistingCacheRSITests(unittest.TestCase):
    def test_rsi_rising_price_reaches_100(self):
        s = pd.Series(range(1, 40), dtype=float)
        out = _rsi(s)
        self.assertEqual(float(out.dropna().iloc[-1]), 100.0)

    def test_reads_existing_price_cache_no_network(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            df = pd.DataFrame({"TckrSymb":["ABC"], "SctySrs":["EQ"], "ClsPric":[100], "OpnPric":[99], "HghPric":[101], "LwPric":[98], "TtlTradgVol":[1000], "TtlTrfVal":[100000]})
            df.to_csv(p / "bhavcopy_20260102.csv", index=False)
            prices, issues = _read_price_cache(p)
            self.assertEqual(len(prices), 1)
            self.assertEqual(prices.iloc[0]["SYMBOL"], "ABC")
            self.assertEqual(issues, [])

    def test_delivery_cache_requires_exact_columns(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            pd.DataFrame({"SYMBOL":["ABC"], "SERIES":["EQ"], "DELIV_PER":[60]}).to_csv(p / "sec_bhavdata_full_02012026.csv", index=False)
            data, issues = _read_delivery_cache(p)
            self.assertEqual(len(data), 1)
            self.assertEqual(float(data[pd.Timestamp("2026-01-02")].iloc[0]["DELIV_PER"]), 60.0)
            self.assertEqual(issues, [])


    def test_ema50_is_available_with_warmup_flag(self):
        dates = pd.date_range("2026-01-01", periods=55, freq="B")
        frame = pd.DataFrame({"DATE": dates, "SYMBOL": ["ABC"] * 55, "SERIES": ["EQ"] * 55,
                              "OPEN": np.arange(100, 155, dtype=float), "HIGH": np.arange(101, 156, dtype=float),
                              "LOW": np.arange(99, 154, dtype=float), "CLOSE": np.arange(100, 155, dtype=float),
                              "VOLUME": [1000] * 55, "TRADED_VALUE": [100000] * 55})
        out = _signals_for_symbol(frame)
        self.assertFalse(pd.isna(out.iloc[0]["EMA50"]))
        self.assertEqual(out.iloc[0]["EMA50WarmupStatus"], "PRELIMINARY_LESS_THAN_50_BARS")
        self.assertEqual(out.iloc[49]["EMA50WarmupStatus"], "MATURE_50_PLUS_BARS")

    def test_empty_cache_writes_wait_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            price = root / "prices"; price.mkdir()
            delivery = root / "delivery"; delivery.mkdir()
            out = root / "out"
            result = run_backtest(price, delivery, out)
            self.assertEqual(result["status"], "WAIT_FOR_DATA")
            self.assertTrue((out / "rsi_retest_comparison.csv").exists())

    def test_30d_delivery_category_a_passes_category_b_fails(self):
        signal_date = pd.Timestamp("2026-10-30")
        by_date = {}
        values = [100, 59, 59, 59, 59, 100, 59, 59, 59, 59, 100, 59, 59]
        for day, value in zip(pd.date_range("2026-10-05", periods=13, freq="2D"), values):
            by_date[day.normalize()] = pd.DataFrame([{"SYMBOL": "ABC", "SERIES": "EQ", "DELIV_PER": value}])
        result = _delivery_status("ABC", signal_date, by_date)
        self.assertEqual(result["DeliverySessions"], 6)
        self.assertEqual(result["DeliveryCategoryAStatus"], "PASS_ROLLING_5D_AVG_GE_60_AT_LEAST_5")
        self.assertEqual(result["DeliveryCategoryBStatus"], "FILTERED_OUT_DAILY_DELIVERY_LT_5")

    def test_30d_delivery_category_b_passes_at_exactly_60(self):
        signal_date = pd.Timestamp("2026-10-30")
        by_date = {}
        for day in pd.date_range("2026-10-05", periods=5, freq="5D"):
            by_date[day.normalize()] = pd.DataFrame([{"SYMBOL": "ABC", "SERIES": "EQ", "DELIV_PER": 60.0}])
        result = _delivery_status("ABC", signal_date, by_date)
        self.assertEqual(result["DeliveryCategoryAStatus"], "FILTERED_OUT_ROLLING_5D_AVG_LT_5")
        self.assertEqual(result["DeliveryCategoryBStatus"], "PASS_DAILY_DELIVERY_GE_60_AT_LEAST_5")

    def test_30d_delivery_fewer_than_five_valid_symbol_reports_waits(self):
        signal_date = pd.Timestamp("2026-10-30")
        by_date = {}
        for day in pd.date_range("2026-10-05", periods=4, freq="5D"):
            by_date[day.normalize()] = pd.DataFrame([{"SYMBOL": "ABC", "SERIES": "EQ", "DELIV_PER": 75.0}])
        result = _delivery_status("ABC", signal_date, by_date)
        self.assertEqual(result["DeliverySessions"], 4)
        self.assertEqual(result["DeliveryCategoryAStatus"], "WAIT_FOR_DATA")
        self.assertEqual(result["DeliveryCategoryBStatus"], "WAIT_FOR_DATA")

    def test_30d_delivery_excludes_reports_outside_window_and_after_signal(self):
        signal_date = pd.Timestamp("2026-10-30")
        by_date = {}
        for day in [pd.Timestamp("2026-09-30"), *pd.date_range("2026-10-05", periods=4, freq="5D"), pd.Timestamp("2026-10-31")]:
            by_date[day.normalize()] = pd.DataFrame([{"SYMBOL": "ABC", "SERIES": "EQ", "DELIV_PER": 75.0}])
        result = _delivery_status("ABC", signal_date, by_date)
        self.assertEqual(result["DeliverySessions"], 4)
        self.assertEqual(result["DeliveryCategoryAStatus"], "WAIT_FOR_DATA")

if __name__ == "__main__":
    unittest.main()
