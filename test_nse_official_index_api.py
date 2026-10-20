"""Regression tests for the current official Nifty Indices historical-data API."""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

MODULE_PATH = Path(__file__).with_name("sector_data.py")
SPEC = importlib.util.spec_from_file_location("sector_data_official_history_under_test", MODULE_PATH)
sector_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sector_data)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", content_type="application/json; charset=utf-8"):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": content_type}
        self.url = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return FakeResponse(text="<html>official historical data page</html>", content_type="text/html; charset=utf-8")

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.response


class OfficialIndexHistoryTests(unittest.TestCase):
    def setUp(self):
        self.asof = pd.Timestamp("2026-10-15")

    def test_reads_official_healthcare_closes_and_posts_expected_query(self):
        response = FakeResponse(payload={"d": json.dumps([
            {"HistoricalDate": "15 Oct 2026", "CLOSE": "15721.45"},
            {"HistoricalDate": "14 Oct 2026", "CLOSE": "15663.00"},
        ])})
        session = FakeSession(response)
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_niftyindices_api(session, self.asof, {"Nifty Healthcare"})
        self.assertEqual(exact, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Sector"], "Nifty Healthcare")
        self.assertEqual(rows[0]["Date"], "2026-10-15")
        self.assertAlmostEqual(rows[0]["Close"], 15721.45)
        post_call = next(call for call in session.calls if call[0] == "POST")
        self.assertIn("getHistoricaldatatabletoString", post_call[1])
        self.assertIn("data", post_call[2])
        self.assertNotIn("json", post_call[2])
        body = json.loads(post_call[2]["data"])
        self.assertIn("NIFTY HEALTHCARE", body["cinfo"])

    def test_rejects_invalid_dates_and_closes(self):
        response = FakeResponse(payload={"d": json.dumps([
            {"HistoricalDate": "15 Oct 2026", "CLOSE": "-"},
            {"HistoricalDate": "not-a-date", "CLOSE": "12345.0"},
        ])})
        session = FakeSession(response)
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_niftyindices_api(session, self.asof, {"Nifty Healthcare"})
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)

    def test_non_200_stays_missing(self):
        response = FakeResponse(status_code=403, payload={"d": "[]"}, text="blocked", content_type="text/html")
        session = FakeSession(response)
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_niftyindices_api(session, self.asof, {"Nifty Healthcare"})
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)


class NSEHistoryResponse:
    def __init__(self, status_code=200, payload=None, text="", content_type="application/json; charset=utf-8", url=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": content_type}
        self.url = url

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class NSEHistorySession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.cookies = {"session": "test"}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url in {
            "https://www.nseindia.com/report-detail/eq_security",
            "https://www.nseindia.com/reports-indices-historical-index-data",
            "https://www.nseindia.com/",
        }:
            return NSEHistoryResponse(
                text="<html>official NSE report page</html>",
                content_type="text/html; charset=utf-8",
                url=url,
            )
        return NSEHistoryResponse(payload=self.payload, url=url)


class NSEOfficialHistoryEndpointTests(unittest.TestCase):
    def setUp(self):
        self.asof = pd.Timestamp("2026-10-19")

    def test_reads_nested_index_close_online_records_and_uses_nse_endpoint(self):
        session = NSEHistorySession({"data": {"indexCloseOnlineRecords": [
            {"EOD_INDEX_NAME": "NIFTY POWER", "EOD_TIMESTAMP": "19-Oct-2026", "EOD_CLOSE_INDEX_VAL": "8123.45"},
            {"EOD_INDEX_NAME": "NIFTY POWER", "EOD_TIMESTAMP": "16-Oct-2026", "EOD_CLOSE_INDEX_VAL": "8099.10"},
            {"EOD_INDEX_NAME": "NIFTY INSURANCE", "EOD_TIMESTAMP": "19-Oct-2026", "EOD_CLOSE_INDEX_VAL": "123.0"},
        ]}})
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_indices_api(session, self.asof, {"Nifty Power"})
        self.assertEqual(exact, 1)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["Sector"] == "Nifty Power" for row in rows))
        self.assertEqual(rows[0]["Date"], "2026-10-19")
        self.assertAlmostEqual(rows[0]["Close"], 8123.45)
        api_call = next((url, kw) for url, kw in session.calls if "historicalOR/indicesHistory" in url)
        self.assertEqual(api_call[1]["params"]["indexType"], "NIFTY POWER")
        self.assertEqual(api_call[1]["params"]["from"], "05-08-2026")
        self.assertEqual(api_call[1]["params"]["to"], "19-10-2026")

    def test_uses_report_detail_bootstrap_before_root_fallback(self):
        session = NSEHistorySession({"data": {"indexCloseOnlineRecords": []}})
        with patch.object(sector_data.time, "sleep", return_value=None):
            sector_data._history_from_nse_indices_api(session, self.asof, {"Nifty Power"})
        bootstrap_urls = [url for url, _kwargs in session.calls if "historicalOR/indicesHistory" not in url]
        self.assertGreaterEqual(len(bootstrap_urls), 1)
        self.assertEqual(bootstrap_urls[0], "https://www.nseindia.com/report-detail/eq_security")

    def test_empty_or_invalid_payload_stays_missing(self):
        session = NSEHistorySession({"data": {"indexCloseOnlineRecords": []}})
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_indices_api(session, self.asof, {"Nifty Power"})
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)

    def test_rejects_wrong_index_name_bad_close_and_future_date(self):
        session = NSEHistorySession({"data": {"indexCloseOnlineRecords": [
            {"EOD_INDEX_NAME": "NIFTY INSURANCE", "EOD_TIMESTAMP": "19-Oct-2026", "EOD_CLOSE_INDEX_VAL": "123"},
            {"EOD_INDEX_NAME": "NIFTY POWER", "EOD_TIMESTAMP": "19-Oct-2026", "EOD_CLOSE_INDEX_VAL": "-"},
            {"EOD_INDEX_NAME": "NIFTY POWER", "EOD_TIMESTAMP": "20-Oct-2026", "EOD_CLOSE_INDEX_VAL": "999"},
        ]}})
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_indices_api(session, self.asof, {"Nifty Power"})
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class SameDaySnapshotResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)
        self.content = self.text.encode("utf-8")
        self.headers = {"Content-Type": "application/json; charset=utf-8"}
        self.url = "https://www.nseindia.com/api/allIndices"

    def json(self):
        return self._payload


class SameDaySnapshotSession:
    def __init__(self, payload):
        self.response = SameDaySnapshotResponse(payload)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class NSEAllIndicesSnapshotTests(unittest.TestCase):
    def test_accepts_only_same_day_post_close_snapshot_for_missing_sectors(self):
        from datetime import datetime
        payload = {"data": [
            {"index": "NIFTY CAPITAL GOODS", "last": "16200.41"},
            {"index": "NIFTY CONSTRUCTION", "last": "1001.25"},
            {"index": "NIFTY CONSUMER SERVICES", "last": "900.15"},
            {"index": "NIFTY INSURANCE", "last": "820.10"},
            {"index": "NIFTY POWER", "last": "7500.55"},
            {"index": "NIFTY TELECOMMUNICATIONS", "last": "2100.35"},
        ]}
        session = SameDaySnapshotSession(payload)
        now = datetime.fromisoformat("2026-10-20T16:00:00+05:30")
        rows, exact = sector_data._history_from_nse_all_indices_snapshot(
            session, pd.Timestamp("2026-10-20"),
            {"Nifty Capital Goods", "Nifty Construction", "Nifty Consumer Services",
             "Nifty Insurance", "Nifty Power", "Nifty Telecommunications"},
            now=now,
        )
        self.assertEqual(exact, 6)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["Date"] == "2026-10-20" for row in rows))
        self.assertEqual({row["Sector"] for row in rows}, {
            "Nifty Capital Goods", "Nifty Construction", "Nifty Consumer Services",
            "Nifty Insurance", "Nifty Power", "Nifty Telecommunications",
        })

    def test_never_stamps_today_snapshot_on_prior_eod_date(self):
        from datetime import datetime
        session = SameDaySnapshotSession({"data": [{"index": "NIFTY POWER", "last": "7500.55"}]})
        now = datetime.fromisoformat("2026-10-20T22:10:00+05:30")
        rows, exact = sector_data._history_from_nse_all_indices_snapshot(
            session, pd.Timestamp("2026-10-19"), {"Nifty Power"}, now=now
        )
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)

    def test_skips_snapshot_before_market_close(self):
        from datetime import datetime
        session = SameDaySnapshotSession({"data": [{"index": "NIFTY POWER", "last": "7500.55"}]})
        now = datetime.fromisoformat("2026-10-20T15:30:00+05:30")
        rows, exact = sector_data._history_from_nse_all_indices_snapshot(
            session, pd.Timestamp("2026-10-20"), {"Nifty Power"}, now=now
        )
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)
        self.assertEqual(session.calls, [])
