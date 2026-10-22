import tempfile
import unittest
from pathlib import Path
import pandas as pd
import numpy as np
from rsi_retest_existing_cache import _read_price_cache, _read_delivery_cache, _rsi, _signals_for_symbol, run_backtest

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

if __name__ == "__main__":
    unittest.main()
