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


if __name__ == "__main__":
    unittest.main(verbosity=2)
