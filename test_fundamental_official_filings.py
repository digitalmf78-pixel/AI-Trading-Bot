import tempfile
from pathlib import Path
import pandas as pd

from fundamental_official_filings import apply_official_publication_dates, _period_end_from_description


def test_period_end_parser_requires_period_context():
    assert str(_period_end_from_description("Financial Results for quarter ended June 30, 2026")) == "2026-06-30"
    assert str(_period_end_from_description("Results discussed at board meeting on 30-Jun-2026")) == "None"


def test_exact_symbol_and_period_verified_only_before_cutoff(tmp_path):
    records = pd.DataFrame([{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30"}])
    filings = pd.DataFrame([{
        "TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30", "PublicationDate": "2026-07-25",
        "PublicationDateStatus": "VERIFIED", "OfficialFilingURL": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        "OfficialSource": "NSE corporate announcements",
    }])
    out = apply_official_publication_dates(records, "2026-10-22", filings=filings,
        cache_path=tmp_path/"cache.csv", diagnostics_path=tmp_path/"diag.csv")
    assert out.loc[0, "PublicationDateStatus"] == "VERIFIED"
    assert str(out.loc[0, "PublicationDate"])[:10] == "2026-07-25"


def test_future_publication_and_future_period_are_unverified(tmp_path):
    records = pd.DataFrame([
        {"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30"},
        {"TckrSymb": "XYZ", "FinancialPeriodEnd": "2026-12-31"},
    ])
    filings = pd.DataFrame([
        {"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30", "PublicationDate": "2026-10-23", "PublicationDateStatus": "VERIFIED"},
        {"TckrSymb": "XYZ", "FinancialPeriodEnd": "2026-12-31", "PublicationDate": "2026-10-20", "PublicationDateStatus": "VERIFIED"},
    ])
    out = apply_official_publication_dates(records, "2026-10-22", filings=filings,
        cache_path=tmp_path/"cache.csv", diagnostics_path=tmp_path/"diag.csv")
    assert set(out["PublicationDateStatus"].astype(str)) == {"UNVERIFIED"}
    assert len(out) == 2


def test_symbol_mismatch_does_not_verify_and_rows_are_retained(tmp_path):
    records = pd.DataFrame([{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30"}, {"TckrSymb": "XYZ", "FinancialPeriodEnd": "2026-06-30"}])
    filings = pd.DataFrame([{"TckrSymb": "ABCX", "FinancialPeriodEnd": "2026-06-30", "PublicationDate": "2026-07-25", "PublicationDateStatus": "VERIFIED"}])
    out = apply_official_publication_dates(records, "2026-10-22", filings=filings,
        cache_path=tmp_path/"cache.csv", diagnostics_path=tmp_path/"diag.csv")
    assert len(out) == 2
    assert all(out["PublicationDateStatus"].astype(str) == "UNVERIFIED")


def test_missing_period_does_not_use_asof_date_as_period(tmp_path):
    records = pd.DataFrame([{"TckrSymb": "ABC", "AsOfDate": "2026-10-22"}])
    filings = pd.DataFrame([{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-10-22", "PublicationDate": "2026-10-20", "PublicationDateStatus": "VERIFIED"}])
    out = apply_official_publication_dates(records, "2026-10-22", filings=filings,
        cache_path=tmp_path/"cache.csv", diagnostics_path=tmp_path/"diag.csv")
    assert out.loc[0, "PublicationDateStatus"] == "UNVERIFIED"


def test_period_end_parser_handles_ordinal_and_combined_quarter_year():
    assert str(_period_end_from_description("Financial Results for the quarter ended 30th June, 2026")) == "2026-06-30"
    assert str(_period_end_from_description("Financial Results for the quarter and year ended March 31, 2026")) == "2026-03-31"
    assert str(_period_end_from_description("Unaudited results for nine months ended 31st December 2025")) == "2025-12-31"


def test_date_parser_handles_month_first_and_epoch_timestamp():
    from fundamental_official_filings import _date
    assert str(_date("06/30/2026")) == "2026-06-30"
    assert str(_date("30-Jun-2026 17:20:00")) == "2026-06-30"
    assert str(_date(1792953600)) == "2026-10-25"


def test_fetch_failure_uses_cache_but_respects_eod_cutoff(tmp_path):
    cache = tmp_path / "filings.csv"
    pd.DataFrame([
        {"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30", "PublicationDate": "2026-07-25",
         "PublicationDateStatus": "VERIFIED", "OfficialFilingURL": "https://www.nseindia.com/file.pdf",
         "OfficialSource": "NSE corporate announcements"},
        {"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-09-30", "PublicationDate": "2026-10-23",
         "PublicationDateStatus": "VERIFIED", "OfficialFilingURL": "https://www.nseindia.com/file2.pdf",
         "OfficialSource": "NSE corporate announcements"},
    ]).to_csv(cache, index=False)
    records = pd.DataFrame([{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30"},
                            {"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-09-30"}])
    def failing_fetcher(_cutoff):
        raise RuntimeError("NSE unavailable")
    out = apply_official_publication_dates(
        records, "2026-10-22", fetcher=failing_fetcher,
        cache_path=cache, diagnostics_path=tmp_path/"diag.csv"
    )
    assert out.loc[0, "PublicationDateStatus"] == "VERIFIED"
    assert out.loc[1, "PublicationDateStatus"] == "UNVERIFIED"
    diag = pd.read_csv(tmp_path/"diag.csv")
    assert "CUTOFF_SAFE_CACHE_FALLBACK" in set(diag["Status"])
    assert "FETCH_FAILED" in set(diag["Status"])


def test_homepage_403_does_not_block_official_api_attempt(tmp_path):
    from fundamental_official_filings import fetch_nse_financial_results, NSE_HOME, NSE_API

    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")
        def json(self):
            return self._payload

    class Session:
        def __init__(self):
            self.headers = {}
            self.calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if url == NSE_HOME:
                return Response(403)
            if url == NSE_API:
                return Response(200, [{
                    "symbol": "ABC",
                    "an_dt": "25-Jul-2026",
                    "desc": "Financial Results for quarter ended June 30, 2026",
                    "attchmntFile": "https://www.nseindia.com/example.pdf",
                }])
            raise AssertionError(f"Unexpected URL: {url}")

    session = Session()
    result = fetch_nse_financial_results("2026-10-23", session_factory=lambda: session, diagnostics_path=tmp_path/"fetch_diag.csv")
    assert len(session.calls) == 2
    assert session.calls[0][0] == NSE_HOME
    assert session.calls[1][0] == NSE_API
    assert len(result) == 1
    assert result.iloc[0]["TckrSymb"] == "ABC"
    assert result.iloc[0]["FinancialPeriodEnd"] == "2026-06-30"
    assert result.iloc[0]["PublicationDate"] == "2026-07-25"



def test_empty_or_unmatched_live_payload_writes_fetch_diagnostics(tmp_path):
    from fundamental_official_filings import fetch_nse_financial_results, NSE_HOME, NSE_API

    class Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload

    class Session:
        def __init__(self):
            self.headers = {}
        def get(self, url, **kwargs):
            if url == NSE_HOME:
                return Response([])
            if url == NSE_API:
                return Response([{"symbol": "ABC", "an_dt": "20-10-2026", "desc": "Annual report uploaded"}])
            raise AssertionError(url)

    diag_path = tmp_path / "fetch_diag.csv"
    result = fetch_nse_financial_results("2026-10-23", session_factory=Session, diagnostics_path=diag_path)
    assert result.empty
    diag = pd.read_csv(diag_path).iloc[0]
    assert int(diag["APIStatusCode"]) == 200
    assert int(diag["PayloadItemCount"]) == 1
    assert int(diag["RejectNoFinancialTerm"]) == 1
    assert int(diag["AcceptedRows"]) == 0
    assert "Annual report uploaded" in diag["SampleDescriptions"]
