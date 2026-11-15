"""ECMS-only audit of explicit NSE filing metadata; never verifies ratio formulas."""
from __future__ import annotations

from urllib.parse import urlsplit
import hashlib
import requests
from bs4 import BeautifulSoup
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

def fetch_ecms_details_remarks(
    audit: pd.DataFrame,
    session=None,
    timeout=25,
    max_bytes=2_000_000,
) -> pd.DataFrame:
    """Fetch only explicit, allowlisted Details URLs and capture visible Remarks.

    HTML is treated as issuer evidence, not as a formula verification. PDF/XML,
    redirects to non-NSE hosts, missing URLs and ambiguous Remarks labels fail closed.
    """
    client = session or requests.Session()
    rows = []
    for _, source in audit.iterrows():
        row = source.to_dict()
        result = dict(row)
        url = str(row.get("DetailsURL", "") or "").strip()
        result.update({
            "RemarksText": "",
            "RemarksStatus": "DETAILS_URL_MISSING",
            "RemarksEvidenceSHA256": "",
            "RemarksContentType": "",
            "VerificationStatus": "NOT_VERIFIED",
        })
        if not url or row.get("DetailsURLStatus") != "PASS":
            rows.append(result)
            continue
        try:
            response = client.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            final_url = str(getattr(response, "url", url) or url)
            if not _official_https_url(final_url):
                result["RemarksStatus"] = "REDIRECTED_OFFICIAL_HOST_CHECK_FAILED"
                rows.append(result)
                continue
            content_type = str(getattr(response, "headers", {}).get("Content-Type", "")).lower()
            result["RemarksContentType"] = content_type[:160]
            body = getattr(response, "content", b"")
            if not isinstance(body, bytes):
                body = str(getattr(response, "text", "")).encode("utf-8", errors="replace")
            if len(body) > max_bytes:
                result["RemarksStatus"] = "HTML_SIZE_LIMIT_EXCEEDED"
                rows.append(result)
                continue
            if "html" not in content_type and not body.lstrip().lower().startswith((b"<!doctype html", b"<html", b"<?xml")):
                result["RemarksStatus"] = "DETAILS_RESPONSE_NOT_HTML"
                rows.append(result)
                continue
            soup = BeautifulSoup(body, "html.parser")
            extracted = []
            for cell in soup.find_all(["td", "th", "dt"]):
                label = " ".join(cell.get_text(" ", strip=True).lower().split()).rstrip(":")
                if label != "remarks":
                    continue
                value = ""
                if cell.name == "dt":
                    sibling = cell.find_next_sibling("dd")
                    value = sibling.get_text(" ", strip=True) if sibling else ""
                else:
                    sibling = cell.find_next_sibling(["td", "th"])
                    if sibling:
                        value = sibling.get_text(" ", strip=True)
                    if not value:
                        parent = cell.find_parent("tr")
                        if parent:
                            cells = parent.find_all(["td", "th"], recursive=False)
                            try:
                                index = cells.index(cell)
                                if index + 1 < len(cells):
                                    value = cells[index + 1].get_text(" ", strip=True)
                            except ValueError:
                                pass
                if value:
                    extracted.append(value)
            unique = list(dict.fromkeys(extracted))
            result["RemarksEvidenceSHA256"] = hashlib.sha256(body).hexdigest()
            if len(unique) == 1:
                result["RemarksText"] = unique[0][:12000]
                result["RemarksStatus"] = "REMARKS_EXTRACTED"
            elif len(unique) > 1:
                result["RemarksStatus"] = "AMBIGUOUS_MULTIPLE_REMARKS"
            else:
                result["RemarksStatus"] = "REMARKS_NOT_FOUND"
        except Exception as exc:
            result["RemarksStatus"] = f"FETCH_OR_PARSE_ERROR:{type(exc).__name__}"
        rows.append(result)
    return pd.DataFrame(rows)
