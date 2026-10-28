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


def test_nse_observed_schema_creation_date_qe_date_and_zero_based_probe(tmp_path):
    from fundamental_official_filings import fetch_nse_financial_results, NSE_HOME, NSE_RESULTS_API

    record = {
        "seq_Id": "1001", "creation_Date": "23-Oct-2026 18:20:00",
        "symbol": "INFY", "cmName": "Infosys Limited", "qe_Date": "30-JUN-2026",
        "type_Sub": "Original", "consolidated": "Consolidated", "audited": "Un-Audited",
        "xbrl": "https://nsearchives.nseindia.com/xbrl/INFY.xml",
    }
    class Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload
    class Session:
        def __init__(self): self.headers = {}; self.calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if url == NSE_HOME: return Response({})
            assert url == NSE_RESULTS_API
            params = kwargs["params"]
            assert params["period_ended"] == "all"
            assert params["type"] == "Integrated Filing- Financials"
            assert params["page"] == 0
            if params["size"] == 1:
                return Response({"totalCount": 1, "data": [record]})
            return Response({"totalCount": 1, "data": [record]})
    session = Session()
    diag_path = tmp_path / "diag.csv"
    result = fetch_nse_financial_results("2026-10-23", session_factory=lambda: session, diagnostics_path=diag_path)
    assert len(result) == 1
    assert result.loc[0, "TckrSymb"] == "INFY"
    assert result.loc[0, "FinancialPeriodEnd"] == "2026-06-30"
    assert result.loc[0, "PublicationDate"] == "2026-10-23"
    assert result.loc[0, "OfficialFilingURL"] == record["xbrl"]
    assert len(session.calls) == 3  # homepage, count probe, full fetch
    diag = pd.read_csv(diag_path).iloc[0]
    assert int(diag["ReportedTotalCount"]) == 1
    assert int(diag["AcceptedRows"]) == 1


def test_homepage_403_does_not_block_official_api_attempt(tmp_path):
    from fundamental_official_filings import fetch_nse_financial_results, NSE_HOME, NSE_RESULTS_API
    record = {"seq_Id": "1", "creation_Date": "25-Jul-2026 12:30:00", "symbol": "ABC",
              "qe_Date": "30-Jun-2026", "type_Sub": "Original"}
    class Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        def __init__(self, payload, status=200): self.payload, self.status_code = payload, status
        def raise_for_status(self):
            if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")
        def json(self): return self.payload
    class Session:
        def __init__(self): self.headers = {}; self.calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if url == NSE_HOME: return Response({}, status=403)
            if url == NSE_RESULTS_API: return Response({"totalCount": 1, "data": [record]})
            raise AssertionError(url)
    session = Session()
    result = fetch_nse_financial_results("2026-10-23", session_factory=lambda: session, diagnostics_path=tmp_path/"diag.csv")
    assert len(result) == 1
    assert session.calls[0][0] == NSE_HOME
    assert all(call[0] == NSE_RESULTS_API for call in session.calls[1:])


def test_zero_total_count_is_reported_as_empty_not_fake_verified_data(tmp_path):
    from fundamental_official_filings import fetch_nse_financial_results, NSE_HOME, NSE_RESULTS_API
    class Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload
    class Session:
        def __init__(self): self.headers = {}
        def get(self, url, **kwargs):
            if url == NSE_HOME: return Response({})
            if url == NSE_RESULTS_API: return Response({"totalCount": 0, "data": []})
            raise AssertionError(url)
    diag_path = tmp_path / "diag.csv"
    result = fetch_nse_financial_results("2026-10-23", session_factory=Session, diagnostics_path=diag_path)
    assert result.empty
    diag = pd.read_csv(diag_path).iloc[0]
    assert diag["PaginationStopReason"] == "TOTAL_COUNT_ZERO"
    assert int(diag["AcceptedRows"]) == 0


def test_capped_full_fetch_falls_back_to_zero_based_pages_and_deduplicates(tmp_path):
    from fundamental_official_filings import fetch_nse_financial_results, NSE_HOME, NSE_RESULTS_API
    records = [{"seq_Id": str(i), "creation_Date": "23-Oct-2026 18:20:00", "symbol": f"SYM{i:02d}",
                "qe_Date": "30-Sep-2026", "type_Sub": "Original"} for i in range(12)]
    class Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload
    class Session:
        def __init__(self): self.headers = {}; self.pages = []
        def get(self, url, **kwargs):
            if url == NSE_HOME: return Response({})
            assert url == NSE_RESULTS_API
            params = kwargs["params"]
            if params["size"] == 1: return Response({"totalCount": 12, "data": records[:1]})
            if params["size"] != 1000: return Response({"totalCount": 12, "data": records[:5]})
            page = int(params["page"]); self.pages.append(page)
            start = page * 5
            return Response({"totalCount": 12, "data": records[start:start + 5]})
    session = Session()
    diag_path = tmp_path / "pagination_diag.csv"
    result = fetch_nse_financial_results("2026-10-23", session_factory=lambda: session, diagnostics_path=diag_path)
    assert len(result) == 12
    assert result["TckrSymb"].nunique() == 12
    assert session.pages[:3] == [0, 1, 2]
    diag = pd.read_csv(diag_path).iloc[0]
    assert int(diag["AcceptedRows"]) == 12
    assert diag["PaginationStopReason"] == "TOTALCOUNT_REACHED"


def test_publication_date_alone_does_not_verify_without_quarter_end(tmp_path):
    from fundamental_official_filings import fetch_nse_financial_results, NSE_HOME, NSE_RESULTS_API
    class Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload
    class Session:
        def __init__(self): self.headers = {}
        def get(self, url, **kwargs):
            if url == NSE_HOME: return Response({})
            if url == NSE_RESULTS_API:
                return Response({"totalCount": 1, "data": [{"seq_Id": "1", "creation_Date": "23-Oct-2026 18:20:00", "symbol": "INFY"}]})
            raise AssertionError(url)
    diag_path = tmp_path / "diag.csv"
    result = fetch_nse_financial_results("2026-10-23", session_factory=Session, diagnostics_path=diag_path)
    assert result.empty
    diag = pd.read_csv(diag_path).iloc[0]
    assert int(diag["RejectPeriodMissing"]) == 1
    assert int(diag["AcceptedRows"]) == 0



def test_targeted_lookup_tries_sme_if_equities_has_no_exact_period(monkeypatch):
    import fundamental_official_filings as mod

    exact = {
        "seq_Id": "sme-2", "creation_Date": "20-May-2026 12:00:00",
        "symbol": "ABC", "cmName": "ABC Limited", "qe_Date": "31-MAR-2026",
        "type_Sub": "Original", "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/ABC.xml",
    }
    newer = {
        "seq_Id": "eq-1", "creation_Date": "20-Aug-2026 12:00:00",
        "symbol": "ABC", "cmName": "ABC Limited", "qe_Date": "30-JUN-2026",
        "type_Sub": "Original", "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/ABC-Q1.xml",
    }
    class Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload
    class Session:
        def __init__(self): self.headers = {}; self.calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs["params"].copy()))
            params = kwargs["params"]
            assert params["symbol"] == "ABC"
            assert params["period_ended"] == "all"
            if params["index"] == "equities": return Response({"totalCount": 1, "data": [newer]})
            return Response({"totalCount": 1, "data": [exact]})
    session = Session()
    out = mod._fetch_targeted_nse_filings("2026-10-23", [{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-03-31"}], session_factory=lambda: session)
    assert len(out) == 2
    assert out[(out["FinancialPeriodEnd"] == "2026-03-31") & (out["TckrSymb"] == "ABC")].shape[0] == 1
    assert [call[1]["index"] for call in session.calls] == ["equities", "sme"]


def test_apply_official_dates_uses_targeted_fallback_for_unmatched_pair(monkeypatch, tmp_path):
    import fundamental_official_filings as mod
    bulk = pd.DataFrame([{
        "TckrSymb": "OTHER", "FinancialPeriodEnd": "2026-03-31", "PublicationDate": "2026-05-01",
        "PublicationDateStatus": "VERIFIED", "OfficialFilingURL": "https://example.invalid/other.xml",
        "OfficialSource": "NSE Integrated Filing - Financials", "FilingDescription": "Other", "RetrievedAtUTC": "2026-10-23T00:00:00Z",
    }])
    targeted = pd.DataFrame([{
        "TckrSymb": "ABC", "FinancialPeriodEnd": "2026-03-31", "PublicationDate": "2026-05-20",
        "PublicationDateStatus": "VERIFIED", "OfficialFilingURL": "https://nsearchives.nseindia.com/corporate/xbrl/ABC.xml",
        "OfficialSource": "NSE Integrated Filing - Financials (equities targeted lookup)", "FilingDescription": "ABC results", "RetrievedAtUTC": "2026-10-23T00:00:00Z",
    }])
    monkeypatch.setattr(mod, "fetch_nse_financial_results", lambda asof: bulk)
    monkeypatch.setattr(mod, "_fetch_targeted_nse_filings", lambda asof, candidates, **kwargs: targeted)
    records = pd.DataFrame([{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-03-31", "PublicationDateStatus": "UNVERIFIED"}])
    out = mod.apply_official_publication_dates(
        records, "2026-10-23", cache_path=tmp_path/"filings.csv", diagnostics_path=tmp_path/"verify.csv"
    )
    assert out.loc[0, "PublicationDateStatus"] == "VERIFIED"
    assert out.loc[0, "PublicationDate"] == "2026-05-20"
    assert "ABC.xml" in out.loc[0, "OfficialFilingURL"]
    diag = pd.read_csv(tmp_path/"verify.csv")
    assert "TARGETED_LOOKUP_COMPLETED" in set(diag["Status"])


def test_targeted_lookup_writes_per_symbol_segment_diagnostics(tmp_path):
    import fundamental_official_filings as mod

    class Response:
        status_code = 200
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload

    class Session:
        def __init__(self):
            self.headers = {}
            self.calls = []
        def get(self, url, params, timeout):
            self.calls.append((url, dict(params)))
            if params["index"] == "equities":
                return Response({"totalCount": 0, "data": []})
            return Response({"totalCount": 1, "data": [{
                "seq_Id": "sme-1",
                "creation_Date": "20-May-2026 12:00:00",
                "symbol": "ABC",
                "cmName": "ABC Limited",
                "qe_Date": "31-Mar-2026",
                "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/ABC.xml",
                "type_Sub": "Financial Results",
            }]})

    diag_path = tmp_path / "targeted.csv"
    out = mod._fetch_targeted_nse_filings(
        "2026-10-23",
        [{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-03-31"}],
        session_factory=Session,
        diagnostics_path=diag_path,
    )
    assert len(out) == 1
    diag = pd.read_csv(diag_path)
    assert list(diag["Segment"]) == ["equities", "sme"]
    assert diag.iloc[0]["RequestStatus"] == "OK"
    assert int(diag.iloc[1]["RowsForExactPeriod"]) == 1
