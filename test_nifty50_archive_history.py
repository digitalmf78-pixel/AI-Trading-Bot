import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

MODULE_PATH = Path(__file__).with_name("sector_data.py")
SPEC = importlib.util.spec_from_file_location("sector_data_nifty50_archive_under_test", MODULE_PATH)
sector_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sector_data)


class Nifty50OfficialArchiveHistoryTests(unittest.TestCase):
    def setUp(self):
        self.asof = pd.Timestamp("2026-11-17")

    @staticmethod
    def _archive(day, close):
        return pd.DataFrame({
            "Index Name": ["Nifty 50"],
            "Index Date": [pd.Timestamp(day).strftime("%d-%b-%Y")],
            "Closing Index Value": [close],
        })

    def test_returns_50_exact_distinct_official_sessions(self):
        def archive(_session, day):
            return self._archive(day, 22000 + (self.asof - pd.Timestamp(day)).days)

        with patch.object(sector_data, "is_trading_session", side_effect=lambda day: day.weekday() < 5), \
             patch.object(sector_data, "_download_daily_index_file", side_effect=archive), \
             patch.object(sector_data.time, "sleep", return_value=None):
            result = sector_data.load_nifty50_index_history_from_archive(self.asof, min_bars=50, max_calendar_days=110)

        self.assertEqual(len(result), 50)
        self.assertEqual(result["Date"].nunique(), 50)
        self.assertEqual(pd.Timestamp(result.iloc[-1]["Date"]).normalize(), self.asof)
        self.assertTrue((pd.to_numeric(result["NiftyClose"]) > 0).all())

    def test_missing_exact_eod_date_fails_closed_even_with_older_closes(self):
        def archive(_session, day):
            if pd.Timestamp(day).normalize() == self.asof:
                return pd.DataFrame(columns=["Index Name", "Index Date", "Closing Index Value"])
            return self._archive(day, 22000 + (self.asof - pd.Timestamp(day)).days)

        with patch.object(sector_data, "is_trading_session", side_effect=lambda day: day.weekday() < 5), \
             patch.object(sector_data, "_download_daily_index_file", side_effect=archive), \
             patch.object(sector_data.time, "sleep", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "exact EOD 2026-11-17 is required"):
                sector_data.load_nifty50_index_history_from_archive(self.asof, min_bars=50, max_calendar_days=110)

    def test_wrong_index_name_and_internal_date_mismatch_are_not_accepted(self):
        def archive(_session, day):
            return pd.DataFrame({
                "Index Name": ["Nifty Next 50", "Nifty 50"],
                "Index Date": [pd.Timestamp(day).strftime("%d-%b-%Y"), "01-Jan-2020"],
                "Closing Index Value": [30000, 22000],
            })

        with patch.object(sector_data, "is_trading_session", side_effect=lambda day: day.weekday() < 5), \
             patch.object(sector_data, "_download_daily_index_file", side_effect=archive), \
             patch.object(sector_data.time, "sleep", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "0/50 distinct closes"):
                sector_data.load_nifty50_index_history_from_archive(self.asof, min_bars=50, max_calendar_days=15)

    def test_calendar_coverage_error_is_not_silently_skipped(self):
        def unavailable(_day):
            raise sector_data.CalendarCoverageError("calendar year missing")

        with patch.object(sector_data, "is_trading_session", side_effect=unavailable), \
             patch.object(sector_data.time, "sleep", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "official NSE calendar coverage unavailable"):
                sector_data.load_nifty50_index_history_from_archive(self.asof, min_bars=50, max_calendar_days=15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
