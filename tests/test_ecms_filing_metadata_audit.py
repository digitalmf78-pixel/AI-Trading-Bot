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
    assert session.calls[-1][1]["params"]["period_ended"] == "all"
    assert "from_date" not in session.calls[-1][1]["params"]


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
    assert result.iloc[0]["FilingMetadataStatus"] == "NO_ELIGIBLE_NSE_FILING"
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

def test_nse_date_parser_uses_explicit_formats_without_ambiguous_dayfirst_guessing():
    from strategies.ecms.filing_metadata_audit import _parse_nse_date
    from datetime import date

    assert _parse_nse_date("2026-03-31") == date(2026, 3, 31)
    assert _parse_nse_date("31-Mar-2026 18:00:00") == date(2026, 3, 31)
    assert _parse_nse_date("31-03-2026") == date(2026, 3, 31)
    assert _parse_nse_date("2026-31-03") is None
    assert _parse_nse_date("") is None



def test_candidate_lookup_discovers_latest_period_without_cached_period_and_keeps_bases_separate():
    from strategies.ecms.filing_metadata_audit import fetch_ecms_candidate_filing_metadata

    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"data": [
                {"symbol":"ABC","qe_Date":"31-Mar-2026","creation_Date":"20-May-2026 18:00:00","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC-old.xml","audited":"Audited","consolidated":"Standalone","seq_Id":"10","type_Sub":"Original"},
                {"symbol":"ABC","qe_Date":"30-Jun-2026","creation_Date":"12-Aug-2026 18:00:00","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC-standalone.xml","details":"https://nsearchives.nseindia.com/corporate/ABC-s.html","audited":"Un-Audited","consolidated":"Standalone","seq_Id":"11","type_Sub":"Original"},
                {"symbol":"ABC","qe_Date":"30-Jun-2026","creation_Date":"12-Aug-2026 18:01:00","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC-consolidated.xml","details":"https://nsearchives.nseindia.com/corporate/ABC-c.html","audited":"Un-Audited","consolidated":"Consolidated","seq_Id":"12","type_Sub":"Original"},
                {"symbol":"ABCD","qe_Date":"30-Jun-2026","creation_Date":"12-Aug-2026 18:00:00","xbrl":"https://nsearchives.nseindia.com/xbrl/OTHER.xml","audited":"Audited","consolidated":"Standalone"},
                {"symbol":"ABC","qe_Date":"30-Sep-2026","creation_Date":"20-Nov-2026 18:00:00","xbrl":"https://nsearchives.nseindia.com/xbrl/future.xml","audited":"Un-Audited","consolidated":"Standalone"},
            ]}

    class Session:
        def __init__(self): self.headers = {}; self.calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response()

    session = Session()
    result = fetch_ecms_candidate_filing_metadata(
        pd.DataFrame([{"TckrSymb":"ABC"}]), "2026-11-15", session=session
    )
    assert len(result) == 2
    assert set(result["FinancialPeriodEnd"]) == {"2026-06-30"}
    assert set(result["consolidated"]) == {"Standalone", "Consolidated"}
    assert set(result["VerificationStatus"]) == {"NOT_VERIFIED"}
    assert session.calls[-1][1]["params"]["period_ended"] == "all"
    assert "from_date" not in session.calls[-1][1]["params"]


def test_latest_period_audit_does_not_confuse_standalone_and_consolidated_rows():
    raw = pd.DataFrame([
        {"TckrSymb":"ABC","FinancialPeriodEnd":"2026-06-30","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC-s.xml","details":"https://nsearchives.nseindia.com/corporate/ABC-s.html","audited":"Un-Audited","consolidated":"Standalone","FilingMetadataStatus":"RAW_LATEST_PERIOD_NSE_API_ROW"},
        {"TckrSymb":"ABC","FinancialPeriodEnd":"2026-06-30","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC-c.xml","details":"https://nsearchives.nseindia.com/corporate/ABC-c.html","audited":"Un-Audited","consolidated":"Consolidated","FilingMetadataStatus":"RAW_LATEST_PERIOD_NSE_API_ROW"},
    ])
    out = audit_ecms_filing_metadata(raw)
    assert set(out["FilingMetadataStatus"]) == {"EXPLICIT_METADATA_CAPTURED"}
    assert set(out["VerificationStatus"]) == {"NOT_VERIFIED"}


def test_original_and_revised_same_basis_are_kept_as_distinct_filing_variants():
    raw = pd.DataFrame([
        {"TckrSymb":"ABC","FinancialPeriodEnd":"2026-03-31","PublicationDate":"2026-05-20","RevisedDate":"","SequenceId":"10","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC-original.xml","details":"https://nsearchives.nseindia.com/corporate/ABC-original.html","audited":"Audited","consolidated":"Standalone"},
        {"TckrSymb":"ABC","FinancialPeriodEnd":"2026-03-31","PublicationDate":"2026-06-01","RevisedDate":"2026-06-01","SequenceId":"11","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC-revised.xml","details":"https://nsearchives.nseindia.com/corporate/ABC-revised.html","audited":"Audited","consolidated":"Standalone"},
    ])
    out = audit_ecms_filing_metadata(raw)
    assert len(out) == 2
    assert set(out["FilingMetadataStatus"]) == {"EXPLICIT_METADATA_CAPTURED"}
    assert set(out["VerificationStatus"]) == {"NOT_VERIFIED"}


def test_nse_ixbrl_field_maps_to_official_details_html_and_remarks_heading_is_extracted():
    from strategies.ecms.filing_metadata_audit import (
        audit_ecms_filing_metadata,
        fetch_ecms_candidate_filing_metadata,
        fetch_ecms_details_remarks,
    )

    details_url = "https://nsearchives.nseindia.com/corporate/ixbrl/ABC_iXBRL_WEB.html"

    class LookupResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"data": [{
                "symbol": "ABC", "qe_Date": "30-Sep-2026",
                "creation_Date": "12-Nov-2026 18:00:00",
                "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/ABC.xml",
                "ixbrl": details_url,
                "audited": "Un-Audited", "consolidated": "Standalone",
                "seq_Id": "123", "type_Sub": "Original",
            }]}

    class LookupSession:
        def __init__(self): self.headers = {}
        def get(self, *_args, **_kwargs): return LookupResponse()

    lookup = fetch_ecms_candidate_filing_metadata(
        pd.DataFrame([{"TckrSymb": "ABC"}]), "2026-11-15",
        session=LookupSession(),
    )
    assert lookup.iloc[0]["details"] == details_url

    class DetailsResponse:
        url = details_url
        headers = {"Content-Type": "text/html; charset=utf-8"}
        content = (
            b"<html><body><h3>Remarks</h3><table>"
            b"<tr><td>Debt equity ratio</td><td>Borrowings divided by equity</td></tr>"
            b"<tr><td>Interest service coverage ratio</td><td>EBIT divided by finance cost</td></tr>"
            b"</table><h3>Statement of Asset and Liabilities</h3></body></html>"
        )
        def raise_for_status(self): pass

    class DetailsSession:
        def get(self, *_args, **_kwargs): return DetailsResponse()

    audit = audit_ecms_filing_metadata(lookup)
    out = fetch_ecms_details_remarks(audit, session=DetailsSession()).iloc[0]
    assert out["DetailsURL"] == details_url
    assert out["DetailsURLStatus"] == "PASS"
    assert out["RemarksStatus"] == "REMARKS_EXTRACTED"
    assert "Borrowings divided by equity" in out["RemarksText"]
    assert "EBIT divided by finance cost" in out["RemarksText"]
    assert out["VerificationStatus"] == "NOT_VERIFIED"


def test_nse_remarks_heading_with_only_blank_rows_is_explicitly_empty():
    from strategies.ecms.filing_metadata_audit import fetch_ecms_details_remarks

    details_url = "https://nsearchives.nseindia.com/corporate/ixbrl/ABC_iXBRL_WEB.html"
    source = audit_ecms_filing_metadata(pd.DataFrame([{
        "TckrSymb": "ABC",
        "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/ABC.xml",
        "ixbrl": details_url,
        "audited": "Un-Audited",
        "consolidated": "Standalone",
    }]))

    class Response:
        url = details_url
        headers = {"Content-Type": "text/html"}
        content = b"<html><body><h3>Remarks</h3><table><tr><td>Debt equity ratio</td><td></td></tr></table><h3>Next</h3></body></html>"
        def raise_for_status(self): pass

    class Session:
        def get(self, *_args, **_kwargs): return Response()

    out = fetch_ecms_details_remarks(source, session=Session()).iloc[0]
    assert out["RemarksStatus"] == "REMARKS_SECTION_EMPTY"
    assert out["RemarksText"] == ""
    assert out["VerificationStatus"] == "NOT_VERIFIED"
