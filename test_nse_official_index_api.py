"""Regression tests for the official NSE historical index JSON endpoint."""
import importlib.util
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
    def __init__(self, status_code=200, payload=None, text="", content_type="application/json; charset=utf-8", url=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": content_type}
        self.url = url or "https://www.nseindia.com/api/historicalOR/indicesHistory"

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, api_responses):
        self.api_responses = list(api_responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/report-detail/eq_security"):
            return FakeResponse(text="<html>bootstrap</html>", content_type="text/html", url=url)
        if self.api_responses:
            return self.api_responses.pop(0)
        raise AssertionError(f"Unexpected GET: {url}")


class OfficialNSEHistoryTests(unittest.TestCase):
    def setUp(self):
        self.asof = pd.Timestamp("2026-10-19")

    def test_parses_official_nse_index_close_records_and_correct_query(self):
        response = FakeResponse(payload={"data": {"indexCloseOnlineRecords": [
            {"EOD_INDEX_NAME": "NIFTY POWER", "EOD_TIMESTAMP": "19-Oct-2026", "EOD_CLOSE_INDEX_VAL": "8123.45"},
            {"EOD_INDEX_NAME": "NIFTY POWER", "EOD_TIMESTAMP": "16-Oct-2026", "EOD_CLOSE_INDEX_VAL": "8090.10"},
        ]}})
        session = FakeSession([response])
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_official_nse_api(session, self.asof, {"Nifty Power"})
        self.assertEqual(exact, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Sector"], "Nifty Power")
        self.assertEqual(rows[0]["Date"], "2026-10-19")
        self.assertAlmostEqual(rows[0]["Close"], 8123.45)
        api_call = next((url, kw) for url, kw in session.calls if "historicalOR/indicesHistory" in url)
        self.assertEqual(api_call[1]["params"], {"indexType": "NIFTY POWER", "from": "05-08-2026", "to": "19-10-2026"})

    def test_rejects_wrong_index_identity_and_bad_close(self):
        response = FakeResponse(payload={"data": {"indexCloseOnlineRecords": [
            {"EOD_INDEX_NAME": "NIFTY BANK", "EOD_TIMESTAMP": "19-Oct-2026", "EOD_CLOSE_INDEX_VAL": "59000"},
            {"EOD_INDEX_NAME": "NIFTY POWER", "EOD_TIMESTAMP": "19-Oct-2026", "EOD_CLOSE_INDEX_VAL": "-"},
        ]}})
        session = FakeSession([response])
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_official_nse_api(session, self.asof, {"Nifty Power"})
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)

    def test_rejects_http_403_and_html_even_if_status_200(self):
        for response in (
            FakeResponse(status_code=403, payload={"data": []}, text="blocked", content_type="text/html"),
            FakeResponse(status_code=200, payload=ValueError("not JSON"), text="<html>login</html>", content_type="text/html"),
        ):
            session = FakeSession([response, response])
            with patch.object(sector_data.time, "sleep", return_value=None):
                rows, exact = sector_data._history_from_official_nse_api(session, self.asof, {"Nifty Power"})
            self.assertEqual(rows, [])
            self.assertEqual(exact, 0)

    def test_nifty_healthcare_api_name_is_explicit(self):
        response = FakeResponse(payload={"data": {"indexCloseOnlineRecords": [
            {"EOD_INDEX_NAME": "NIFTY HEALTHCARE", "EOD_TIMESTAMP": "19-Oct-2026", "EOD_CLOSE_INDEX_VAL": "15721.45"},
        ]}})
        session = FakeSession([response])
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_official_nse_api(session, self.asof, {"Nifty Healthcare"})
        self.assertEqual(exact, 1)
        self.assertAlmostEqual(rows[0]["Close"], 15721.45)
        api_call = next((url, kw) for url, kw in session.calls if "historicalOR/indicesHistory" in url)
        self.assertEqual(api_call[1]["params"]["indexType"], "NIFTY HEALTHCARE INDEX")


if __name__ == "__main__":
    unittest.main(verbosity=2)
