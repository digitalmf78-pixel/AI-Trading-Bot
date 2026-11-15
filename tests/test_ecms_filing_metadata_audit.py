import pandas as pd
from strategies.ecms.filing_metadata_audit import audit_ecms_filing_metadata

def test_explicit_xbrl_details_audit_and_basis_are_kept_separate():
    filings = pd.DataFrame([{"TckrSymb":"ABC","FinancialPeriodEnd":"2026-03-31","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC.xml","details_url":"https://nsearchives.nseindia.com/corporate/ABC.html","audited":"Audited","consolidated":"Standalone"}])
    out = audit_ecms_filing_metadata(filings).iloc[0]
    assert out["XBRLURL"].endswith("ABC.xml") and out["DetailsURL"].endswith("ABC.html")
    assert out["FilingMetadataStatus"] == "EXPLICIT_METADATA_CAPTURED"
    assert out["VerificationStatus"] == "NOT_VERIFIED"

def test_generic_url_or_details_is_never_promoted_to_xbrl_or_details_url():
    filings = pd.DataFrame([{"TckrSymb":"ABC","url":"https://nsearchives.nseindia.com/corporate/ABC.html","audited":"Un-Audited","consolidated":"Consolidated"}])
    out = audit_ecms_filing_metadata(filings).iloc[0]
    assert out["XBRLURL"] == "" and out["DetailsURL"] == ""
    assert out["FilingMetadataStatus"] == "METADATA_INCOMPLETE"
    assert out["VerificationStatus"] == "NOT_VERIFIED"

def test_non_nse_urls_and_unknown_labels_fail_closed():
    filings = pd.DataFrame([{"TckrSymb":"XYZ","xbrl":"https://example.com/XYZ.xml","details_url":"https://example.com/XYZ.html","audited":"Maybe","consolidated":"Group"}])
    out = audit_ecms_filing_metadata(filings).iloc[0]
    assert out["XBRLURLStatus"] == "BLOCKED" and out["DetailsURLStatus"] == "BLOCKED"
    assert out["AuditStatus"] == "UNRECOGNIZED_LABEL" and out["ConsolidationStatus"] == "UNRECOGNIZED_LABEL"

def test_remarks_are_extracted_only_from_explicit_official_html_details_url():
    from strategies.ecms.filing_metadata_audit import fetch_ecms_details_remarks

    class Response:
        url = "https://nsearchives.nseindia.com/corporate/ABC.html"
        headers = {"Content-Type": "text/html; charset=utf-8"}
        content = b"<html><table><tr><td>Remarks</td><td>ROCE = EBIT divided by average capital employed</td></tr></table></html>"
        def raise_for_status(self): pass

    class Session:
        def get(self, url, **kwargs):
            assert url == Response.url
            return Response()

    source = audit_ecms_filing_metadata(pd.DataFrame([{
        "TckrSymb": "ABC",
        "xbrl": "https://nsearchives.nseindia.com/xbrl/ABC.xml",
        "details_url": Response.url,
        "audited": "Audited",
        "consolidated": "Standalone",
    }]))
    out = fetch_ecms_details_remarks(source, session=Session()).iloc[0]
    assert out["RemarksStatus"] == "REMARKS_EXTRACTED"
    assert out["RemarksText"] == "ROCE = EBIT divided by average capital employed"
    assert len(out["RemarksEvidenceSHA256"]) == 64
    assert out["VerificationStatus"] == "NOT_VERIFIED"


def test_remarks_fetch_is_blocked_when_details_url_is_missing():
    from strategies.ecms.filing_metadata_audit import fetch_ecms_details_remarks

    source = audit_ecms_filing_metadata(pd.DataFrame([{
        "TckrSymb": "ABC",
        "url": "https://nsearchives.nseindia.com/corporate/ABC.html",
    }]))
    class NeverCalled:
        def get(self, *_args, **_kwargs):
            raise AssertionError("missing explicit Details URL must not be fetched")

    out = fetch_ecms_details_remarks(source, session=NeverCalled()).iloc[0]
    assert out["RemarksStatus"] == "DETAILS_URL_MISSING"
    assert out["VerificationStatus"] == "NOT_VERIFIED"


def test_remarks_redirect_to_non_nse_host_is_rejected():
    from strategies.ecms.filing_metadata_audit import fetch_ecms_details_remarks

    source = audit_ecms_filing_metadata(pd.DataFrame([{
        "TckrSymb": "ABC",
        "xbrl": "https://nsearchives.nseindia.com/xbrl/ABC.xml",
        "details_url": "https://nsearchives.nseindia.com/corporate/ABC.html",
        "audited": "Audited",
        "consolidated": "Consolidated",
    }]))
    class Response:
        url = "https://example.com/ABC.html"
        headers = {"Content-Type": "text/html"}
        content = b"<html><tr><td>Remarks</td><td>some formula</td></tr></html>"
        def raise_for_status(self): pass
    class Session:
        def get(self, *_args, **_kwargs): return Response()

    out = fetch_ecms_details_remarks(source, session=Session()).iloc[0]
    assert out["RemarksStatus"] == "REDIRECTED_OFFICIAL_HOST_CHECK_FAILED"
    assert out["RemarksText"] == ""
    assert out["VerificationStatus"] == "NOT_VERIFIED"


def test_candidate_lookup_uses_exact_symbol_period_and_keeps_details_separate():
    from strategies.ecms.filing_metadata_audit import fetch_ecms_candidate_filing_metadata

    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"data": [{
                "symbol": "ABC", "qe_Date": "31-Mar-2026",
                "creation_Date": "20-May-2026 18:00:00",
                "xbrl": "https://nsearchives.nseindia.com/xbrl/ABC.xml",
                "details": "https://nsearchives.nseindia.com/corporate/ABC.html",
                "audited": "Audited", "consolidated": "Standalone",
                "seq_Id": "42", "type_Sub": "Original",
            }, {
                "symbol": "ABCD", "qe_Date": "31-Mar-2026",
                "creation_Date": "20-May-2026 18:00:00",
                "xbrl": "https://nsearchives.nseindia.com/xbrl/ABCD.xml",
            }, {
                "symbol": "ABC", "qe_Date": "30-Jun-2026",
                "creation_Date": "20-May-2026 18:00:00",
                "xbrl": "https://nsearchives.nseindia.com/xbrl/ABC-Q1.xml",
            }]}

    class Session:
        def __init__(self): self.headers = {}; self.calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response()

    session = Session()
    candidates = pd.DataFrame([{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-03-31"}])
    result = fetch_ecms_candidate_filing_metadata(candidates, "2026-11-15", session=session)
    assert len(result) == 1
    assert result.iloc[0]["TckrSymb"] == "ABC"
    assert result.iloc[0]["details"].endswith("ABC.html")
    assert result.iloc[0]["xbrl"].endswith("ABC.xml")
    assert result.iloc[0]["audited"] == "Audited"
    assert result.iloc[0]["consolidated"] == "Standalone"
    assert session.calls[-1][1]["params"]["symbol"] == "ABC"
    assert session.calls[-1][1]["params"]["from_date"] == "31-03-2026"


def test_candidate_lookup_never_accepts_future_publication_date():
    from strategies.ecms.filing_metadata_audit import fetch_ecms_candidate_filing_metadata

    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"data": [{
                "symbol": "ABC", "qe_Date": "31-Mar-2026",
                "creation_Date": "20-Nov-2026 18:00:00",
                "xbrl": "https://nsearchives.nseindia.com/xbrl/ABC.xml",
            }]}

    class Session:
        def __init__(self): self.headers = {}
        def get(self, *_args, **_kwargs): return Response()

    result = fetch_ecms_candidate_filing_metadata(
        pd.DataFrame([{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-03-31"}]),
        "2026-11-15", session=Session(),
    )
    assert result.iloc[0]["FilingMetadataStatus"] == "NO_EXACT_NSE_API_ROW"
    assert result.iloc[0]["VerificationStatus"] == "NOT_VERIFIED"


def test_api_details_field_must_be_official_url_before_remarks_fetch():
    from strategies.ecms.filing_metadata_audit import audit_ecms_filing_metadata

    raw = pd.DataFrame([{
        "TckrSymb": "ABC", "xbrl": "https://nsearchives.nseindia.com/xbrl/ABC.xml",
        "details": "Not a URL; textual detail", "audited": "Audited",
        "consolidated": "Standalone",
    }])
    out = audit_ecms_filing_metadata(raw).iloc[0]
    assert out["DetailsURL"] == ""
    assert out["DetailsURLStatus"] == "BLOCKED"
    assert out["VerificationStatus"] == "NOT_VERIFIED"


def test_duplicate_exact_filing_rows_are_flagged_ambiguous():
    raw = pd.DataFrame([
        {"TckrSymb":"ABC","FinancialPeriodEnd":"2026-03-31","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC-a.xml","details":"https://nsearchives.nseindia.com/corporate/ABC-a.html","audited":"Audited","consolidated":"Standalone","FilingMetadataStatus":"RAW_EXACT_NSE_API_ROW"},
        {"TckrSymb":"ABC","FinancialPeriodEnd":"2026-03-31","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC-b.xml","details":"https://nsearchives.nseindia.com/corporate/ABC-b.html","audited":"Audited","consolidated":"Standalone","FilingMetadataStatus":"RAW_EXACT_NSE_API_ROW"},
    ])
    out = audit_ecms_filing_metadata(raw)
    assert len(out) == 2
    assert set(out["FilingMetadataStatus"]) == {"AMBIGUOUS_EXACT_FILING_MATCH"}
    assert set(out["NSELookupStatus"]) == {"RAW_EXACT_NSE_API_ROW"}
    assert set(out["VerificationStatus"]) == {"NOT_VERIFIED"}
