import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

MODULE_PATH = Path(__file__).with_name("sector_data.py")
SPEC = importlib.util.spec_from_file_location("sector_data_history_under_test", MODULE_PATH)
sector_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sector_data)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", content_type="text/html; charset=utf-8"):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": content_type}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, post_responses, get_exception=None):
        self.post_responses = list(post_responses)
        self.get_exception = get_exception
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if self.get_exception:
            raise self.get_exception
        return FakeResponse(text="<html>official historical data page</html>")

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if not self.post_responses:
            raise AssertionError("Unexpected POST request")
        return self.post_responses.pop(0)


class NiftyIndicesHistoryBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.asof = pd.Timestamp("2026-10-15")
        self.data_payload = {"d": json.dumps([
            {"HistoricalDate": "15 Oct 2026", "CLOSE": "12345.67"},
            {"HistoricalDate": "14 Oct 2026", "CLOSE": "12300.00"},
        ])}

    def test_bootstraps_official_page_before_parsing_history_response(self):
        session = FakeSession([
            FakeResponse(payload=self.data_payload, text=json.dumps(self.data_payload), content_type="application/json")
        ])
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact_count = sector_data._history_from_niftyindices_api(
                session, self.asof, sectors_to_fetch={"Nifty Healthcare"}
            )

        self.assertEqual([call[0] for call in session.calls], ["GET", "POST"])
        self.assertIn("/reports/historical-data", session.calls[0][1])
        post_kwargs = session.calls[1][2]
        self.assertIn("data", post_kwargs)
        self.assertNotIn("json", post_kwargs)
        self.assertIn("application/json", post_kwargs["headers"]["Content-Type"])
        sent_body = json.loads(post_kwargs["data"])
        self.assertIn("NIFTY HEALTHCARE", sent_body["cinfo"])
        self.assertIn("startDate", sent_body["cinfo"])
        self.assertEqual(exact_count, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Sector"], "Nifty Healthcare")
        self.assertEqual(rows[0]["Date"], "2026-10-15")
        self.assertAlmostEqual(rows[0]["Close"], 12345.67)

    def test_retries_once_after_html_response_and_refreshes_session(self):
        session = FakeSession([
            FakeResponse(payload=ValueError("not JSON"), text="<!DOCTYPE html><html>challenge</html>"),
            FakeResponse(payload=self.data_payload, text=json.dumps(self.data_payload), content_type="application/json"),
        ])
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact_count = sector_data._history_from_niftyindices_api(
                session, self.asof, sectors_to_fetch={"Nifty Healthcare"}
            )

        self.assertEqual([call[0] for call in session.calls], ["GET", "POST", "GET", "POST"])
        self.assertEqual(exact_count, 1)
        self.assertTrue(any(row["Date"] == "2026-10-15" for row in rows))

    def test_failed_bootstrap_does_not_block_data_request(self):
        session = FakeSession([
            FakeResponse(payload=self.data_payload, text=json.dumps(self.data_payload), content_type="application/json")
        ], get_exception=TimeoutError("simulated page timeout"))
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact_count = sector_data._history_from_niftyindices_api(
                session, self.asof, sectors_to_fetch={"Nifty Healthcare"}
            )
        self.assertEqual(exact_count, 1)
        self.assertTrue(rows)

    def test_invalid_html_after_retry_stays_missing_not_synthetic(self):
        html = FakeResponse(payload=ValueError("not JSON"), text="<!DOCTYPE html><html>blocked</html>")
        session = FakeSession([html, html])
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact_count = sector_data._history_from_niftyindices_api(
                session, self.asof, sectors_to_fetch={"Nifty Healthcare"}
            )
        self.assertEqual(rows, [])
        self.assertEqual(exact_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
