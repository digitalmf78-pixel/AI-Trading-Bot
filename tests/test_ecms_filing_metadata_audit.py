import pandas as pd
from strategies.ecms.filing_metadata_audit import audit_ecms_filing_metadata

def test_explicit_xbrl_details_audit_and_basis_are_kept_separate():
    filings = pd.DataFrame([{"TckrSymb":"ABC","FinancialPeriodEnd":"2026-03-31","xbrl":"https://nsearchives.nseindia.com/xbrl/ABC.xml","details_url":"https://nsearchives.nseindia.com/corporate/ABC.html","audited":"Audited","consolidated":"Standalone"}])
    out = audit_ecms_filing_metadata(filings).iloc[0]
    assert out["XBRLURL"].endswith("ABC.xml") and out["DetailsURL"].endswith("ABC.html")
    assert out["FilingMetadataStatus"] == "EXPLICIT_METADATA_CAPTURED"
    assert out["VerificationStatus"] == "NOT_VERIFIED"

def test_generic_url_or_details_is_never_promoted_to_xbrl_or_details_url():
    filings = pd.DataFrame([{"TckrSymb":"ABC","url":"https://nsearchives.nseindia.com/corporate/ABC.html","details":"https://nsearchives.nseindia.com/corporate/ABC.html","audited":"Un-Audited","consolidated":"Consolidated"}])
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
