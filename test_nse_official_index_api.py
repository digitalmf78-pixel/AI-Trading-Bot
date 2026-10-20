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
        self.assertEqual(
            post_call[1],
            "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString",
        )
        self.assertIn("data", post_call[2])
        self.assertNotIn("json", post_call[2])
        body = json.loads(post_call[2]["data"])
        self.assertIn("NIFTY HEALTHCARE", body["cinfo"])
        self.assertIn("startDate':'01 Aug 2026", body["cinfo"])
        self.assertIn("endDate':'15 Oct 2026", body["cinfo"])

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


class OfficialNSEHistoryTests(unittest.TestCase):
    def setUp(self):
        self.asof = pd.Timestamp("2026-10-15")

    def test_current_nse_endpoint_parses_exact_healthcare_closes(self):
        class Response:
            status_code = 200
            headers = {"Content-Type": "application/json; charset=utf-8"}
            text = ""
            def __init__(self, payload=None):
                self.payload = payload or {}
            def json(self):
                return self.payload

        class Session:
            def __init__(self):
                self.calls = []
            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if url.endswith("/report-detail/eq_security"):
                    return Response({})
                return Response({"data": [
                    {
                        "EOD_INDEX_NAME": "NIFTY HEALTHCARE",
                        "EOD_TIMESTAMP": "15-OCT-2026",
                        "EOD_CLOSE_INDEX_VAL": "15721.45",
                    },
                    {
                        "EOD_INDEX_NAME": "NIFTY HEALTHCARE",
                        "EOD_TIMESTAMP": "14-OCT-2026",
                        "EOD_CLOSE_INDEX_VAL": "15663.00",
                    },
                ]})

        session = Session()
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_official_api(
                session, self.asof, {"Nifty Healthcare"}
            )
        self.assertEqual(exact, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Sector"], "Nifty Healthcare")
        self.assertEqual(rows[0]["Date"], "2026-10-15")
        self.assertAlmostEqual(rows[0]["Close"], 15721.45)
        api_call = next(call for call in session.calls if "/api/historicalOR/indicesHistory" in call[0])
        self.assertEqual(api_call[1]["params"]["indexType"], "NIFTY HEALTHCARE INDEX")
        self.assertEqual(api_call[1]["params"]["from"], "01-08-2026")
        self.assertEqual(api_call[1]["params"]["to"], "15-10-2026")

    def test_current_nse_endpoint_parses_documented_nested_records_schema(self):
        class Response:
            status_code = 200
            headers = {"Content-Type": "application/json; charset=utf-8"}
            text = ""
            def __init__(self, payload=None):
                self.payload = payload or {}
            def json(self):
                return self.payload

        class Session:
            def __init__(self):
                self.calls = []
            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if url.endswith("/report-detail/eq_security"):
                    return Response({})
                return Response({"data": {"indexCloseOnlineRecords": [
                    {
                        "EOD_INDEX_NAME": "NIFTY HEALTHCARE",
                        "EOD_TIMESTAMP": "15-OCT-2026",
                        "EOD_CLOSE_INDEX_VAL": "15721.45",
                    },
                    {
                        "EOD_INDEX_NAME": "NIFTY HEALTHCARE",
                        "EOD_TIMESTAMP": "14-OCT-2026",
                        "EOD_CLOSE_INDEX_VAL": "15663.00",
                    },
                ]}})

        session = Session()
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_official_api(
                session, self.asof, {"Nifty Healthcare"}
            )
        self.assertEqual(exact, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Sector"], "Nifty Healthcare")
        self.assertEqual(rows[0]["Date"], "2026-10-15")
        self.assertAlmostEqual(rows[0]["Close"], 15721.45)

    def test_current_nse_endpoint_rejects_wrong_index_identity(self):
        class Response:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            text = ""
            def __init__(self, payload=None):
                self.payload = payload or {}
            def json(self):
                return self.payload

        class Session:
            def get(self, url, **kwargs):
                if url.endswith("/report-detail/eq_security"):
                    return Response({})
                return Response({"data": [{
                    "EOD_INDEX_NAME": "NIFTY IT",
                    "EOD_TIMESTAMP": "15-OCT-2026",
                    "EOD_CLOSE_INDEX_VAL": "15721.45",
                }]})

        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_official_api(
                Session(), self.asof, {"Nifty Healthcare"}
            )
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)

    def test_current_nse_endpoint_rejects_html_and_http_errors(self):
        class Response:
            headers = {"Content-Type": "text/html"}
            text = "<html>login</html>"
            def __init__(self, status_code):
                self.status_code = status_code
            def json(self):
                raise ValueError("not json")

        class Session:
            def get(self, url, **kwargs):
                if url.endswith("/report-detail/eq_security"):
                    return Response(200)
                return Response(403)

        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_official_api(
                Session(), self.asof, {"Nifty Healthcare"}
            )
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
