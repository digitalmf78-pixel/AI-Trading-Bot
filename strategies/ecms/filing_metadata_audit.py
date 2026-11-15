"""ECMS-only audit of explicit NSE filing metadata; never verifies ratio formulas."""
from __future__ import annotations

from urllib.parse import urlsplit
import pandas as pd

OUTPUT_COLUMNS = ["TckrSymb", "FinancialPeriodEnd", "PublicationDate", "XBRLURL", "XBRLURLStatus", "DetailsURL", "DetailsURLStatus", "AuditedLabel", "AuditStatus", "ConsolidationLabel", "ConsolidationStatus", "FilingMetadataStatus", "VerificationStatus", "VerificationWarning"]
NSE_HOSTS = {"nsearchives.nseindia.com", "nsearchives.nseindia.in", "www.nseindia.com", "nseindia.com"}

def _value(row, names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip().lower() not in {"", "nan", "none", "nat", "<na>"}:
            return str(value).strip()
    return ""

def _official_https_url(value):
    parsed = urlsplit(str(value or "").strip())
    return parsed.scheme.lower() == "https" and (parsed.hostname or "").lower() in NSE_HOSTS

def _label_status(value, accepted):
    normalized = " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())
    if not normalized: return "MISSING"
    return "EXPLICIT_LABEL_CAPTURED" if normalized in accepted else "UNRECOGNIZED_LABEL"

def audit_ecms_filing_metadata(filings: pd.DataFrame) -> pd.DataFrame:
    """Keep XBRL, Details, audit and basis as separate explicit source fields.

    Generic url/details fields are never treated as XBRL URLs. No URL is
    synthesized from another URL and no missing metadata is inferred.
    """
    rows = []
    for _, source in filings.iterrows():
        row = source.to_dict()
        xbrl = _value(row, ("xbrl", "xbrl_Link", "xbrlLink", "xbrl_url", "xbrlUrl", "OfficialXBRLURL"))
        details = _value(row, ("details_url", "detailsUrl", "detailsURL", "detailUrl", "DetailsURL", "OfficialDetailsURL"))
        audited = _value(row, ("audited", "auditStatus", "audit_status", "AuditedLabel"))
        consolidation = _value(row, ("consolidated", "consolidation", "reportingBasis", "reporting_basis", "ConsolidationLabel"))
        xbrl_ok = _official_https_url(xbrl) and urlsplit(xbrl).path.lower().endswith(".xml")
        details_ok = _official_https_url(details) and not urlsplit(details).path.lower().endswith(".xml")
        audit_status = _label_status(audited, {"audited", "un audited", "unaudited"})
        basis_status = _label_status(consolidation, {"standalone", "consolidated"})
        metadata_ok = xbrl_ok and details_ok and audit_status == "EXPLICIT_LABEL_CAPTURED" and basis_status == "EXPLICIT_LABEL_CAPTURED"
        warnings = []
        if not xbrl_ok: warnings.append("EXPLICIT_OFFICIAL_XBRL_XML_URL_MISSING_OR_INVALID")
        if not details_ok: warnings.append("SEPARATE_OFFICIAL_DETAILS_HTML_URL_MISSING_OR_INVALID")
        if audit_status != "EXPLICIT_LABEL_CAPTURED": warnings.append("AUDIT_LABEL_MISSING_OR_UNRECOGNIZED")
        if basis_status != "EXPLICIT_LABEL_CAPTURED": warnings.append("REPORTING_BASIS_MISSING_OR_UNRECOGNIZED")
        rows.append({"TckrSymb": _value(row, ("TckrSymb", "symbol")).upper(), "FinancialPeriodEnd": _value(row, ("FinancialPeriodEnd", "qe_Date")), "PublicationDate": _value(row, ("PublicationDate", "creation_Date")), "XBRLURL": xbrl, "XBRLURLStatus": "PASS" if xbrl_ok else "BLOCKED", "DetailsURL": details, "DetailsURLStatus": "PASS" if details_ok else "BLOCKED", "AuditedLabel": audited, "AuditStatus": audit_status, "ConsolidationLabel": consolidation, "ConsolidationStatus": basis_status, "FilingMetadataStatus": "EXPLICIT_METADATA_CAPTURED" if metadata_ok else "METADATA_INCOMPLETE", "VerificationStatus": "NOT_VERIFIED", "VerificationWarning": ";".join(warnings) if warnings else "Metadata only; Remarks/formula and XBRL reconciliation are still required"})
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)