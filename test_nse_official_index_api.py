import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("sector_data.py")
SPEC = importlib.util.spec_from_file_location("sector_data_nse_api_under_test", MODULE_PATH)
sector_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sector_data)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", url="https://www.nseindia.com/api/historicalOR/indicesHistory"):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.url = url
        self.headers = {"Content-Type": "application/json; charset=utf-8"}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, api_response):
        self.api_response = api_response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if "/api/historicalOR/indicesHistory" in url:
            return self.api_response
        return FakeResponse(url=url)


class NseOfficialIndexApiTests(unittest.TestCase):
    def setUp(self):
        self.asof = sector_data.pd.Timestamp("2026-10-15")

    def test_reads_official_healthcare_close_and_uses_expected_query(self):
        session = FakeSession(FakeResponse(payload={"data": [
            {"EOD_INDEX_NAME": "NIFTY HEALTHCARE", "EOD_TIMESTAMP": "15-Oct-2026", "EOD_CLOSE_INDEX_VAL": "15721.45"},
            {"EOD_INDEX_NAME": "NIFTY HEALTHCARE", "EOD_TIMESTAMP": "14-Oct-2026", "EOD_CLOSE_INDEX_VAL": "15663.00"},
        ]}))
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_indices_api(session, self.asof, {"Nifty Healthcare"})
        self.assertEqual(exact, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Sector"], "Nifty Healthcare")
        self.assertEqual(rows[0]["Date"], "2026-10-15")
        self.assertAlmostEqual(rows[0]["Close"], 15721.45)
        api_call = next(call for call in session.calls if "/api/historicalOR/indicesHistory" in call[0])
        self.assertEqual(api_call[1]["params"]["indexType"], "NIFTY HEALTHCARE INDEX")
        self.assertEqual(api_call[1]["params"]["from"], "01-08-2026")
        self.assertEqual(api_call[1]["params"]["to"], "15-10-2026")

    def test_rejects_wrong_index_name_and_invalid_close(self):
        session = FakeSession(FakeResponse(payload={"data": [
            {"EOD_INDEX_NAME": "NIFTY PHARMA", "EOD_TIMESTAMP": "15-Oct-2026", "EOD_CLOSE_INDEX_VAL": "12345.0"},
            {"EOD_INDEX_NAME": "NIFTY HEALTHCARE", "EOD_TIMESTAMP": "15-Oct-2026", "EOD_CLOSE_INDEX_VAL": "-"},
        ]}))
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_indices_api(session, self.asof, {"Nifty Healthcare"})
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)

    def test_non_200_stays_missing(self):
        session = FakeSession(FakeResponse(status_code=403, payload={"data": []}, text="blocked"))
        with patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_indices_api(session, self.asof, {"Nifty Healthcare"})
        self.assertEqual(rows, [])
        self.assertEqual(exact, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
