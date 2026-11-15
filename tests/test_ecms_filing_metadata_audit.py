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