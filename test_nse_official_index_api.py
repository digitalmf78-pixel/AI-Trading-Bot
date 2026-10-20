"""Regression tests for the current official Nifty Indices historical-data API."""
import importlib.util
import json
import tempfile
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


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ArchiveCSVResponse:
    def __init__(self, status_code=200, content=b"", content_type="text/csv"):
        self.status_code = status_code
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.url = "https://archives.nseindia.com/content/indices/test.csv"
        self.history = []


class ArchiveCSVSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if self.responses:
            return self.responses.pop(0)
        return ArchiveCSVResponse(503, b"unavailable", "text/plain")


def _archive_csv_for_sectors(sectors):
    names = {sector: index_name for sector, _files, index_name, _symbol in sector_data.SECTOR_INDICES}
    frame = pd.DataFrame({
        "Index Name": [names[s] for s in sectors],
        "Index Date": ["19-10-2026"] * len(sectors),
        "Closing Index Value": [1000.0 + i for i in range(len(sectors))],
    })
    return frame.to_csv(index=False).encode("utf-8")


class ArchiveCacheRevalidationTests(unittest.TestCase):
    def setUp(self):
        self.asof = pd.Timestamp("2026-10-19")
        self.all_sectors = [item[0] for item in sector_data.SECTOR_INDICES]
        self.missing_six = {
            "Nifty Capital Goods", "Nifty Construction", "Nifty Consumer Services",
            "Nifty Insurance", "Nifty Power", "Nifty Telecommunications",
        }

    def test_incomplete_cache_is_revalidated_and_replaced_by_complete_official_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cache_path = cache_dir / "ind_close_all_19102026.csv"
            initial = [s for s in self.all_sectors if s not in self.missing_six]
            pd.DataFrame({
                "Index Name": [next(x[2] for x in sector_data.SECTOR_INDICES if x[0] == s) for s in initial],
                "Index Date": ["19-10-2026"] * len(initial),
                "Closing Index Value": [1000.0] * len(initial),
            }).to_csv(cache_path, index=False)
            session = ArchiveCSVSession([ArchiveCSVResponse(200, _archive_csv_for_sectors(self.all_sectors))])
            with patch.object(sector_data, "CACHE_DIR", cache_dir):
                frame = sector_data._download_daily_index_file(session, self.asof)
                self.assertEqual(len(sector_data._archive_sector_coverage(frame)), len(self.all_sectors))
                self.assertEqual(len(session.calls), 1)
                refreshed = pd.read_csv(cache_path)
                self.assertEqual(len(sector_data._archive_sector_coverage(refreshed)), len(self.all_sectors))

    def test_complete_cache_is_reused_without_network_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cache_path = cache_dir / "ind_close_all_19102026.csv"
            cache_path.write_bytes(_archive_csv_for_sectors(self.all_sectors))
            session = ArchiveCSVSession([])
            with patch.object(sector_data, "CACHE_DIR", cache_dir):
                frame = sector_data._download_daily_index_file(session, self.asof)
            self.assertEqual(len(sector_data._archive_sector_coverage(frame)), len(self.all_sectors))
            self.assertEqual(session.calls, [])

    def test_failed_revalidation_preserves_and_returns_existing_incomplete_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cache_path = cache_dir / "ind_close_all_19102026.csv"
            initial = [s for s in self.all_sectors if s not in self.missing_six]
            cache_bytes = _archive_csv_for_sectors(initial)
            cache_path.write_bytes(cache_bytes)
            session = ArchiveCSVSession([
                ArchiveCSVResponse(403, b"blocked", "text/html"),
                ArchiveCSVResponse(403, b"blocked", "text/html"),
            ])
            with patch.object(sector_data, "CACHE_DIR", cache_dir):
                frame = sector_data._download_daily_index_file(session, self.asof)
            self.assertEqual(len(sector_data._archive_sector_coverage(frame)), len(self.all_sectors) - 6)
            self.assertEqual(cache_path.read_bytes(), cache_bytes)
            self.assertEqual(len(session.calls), 2)
