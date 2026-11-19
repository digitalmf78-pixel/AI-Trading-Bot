"""ECMS-only audit of explicit NSE filing metadata; never verifies ratio formulas."""
from __future__ import annotations

from urllib.parse import urlsplit
import hashlib
import time
import requests
from bs4 import BeautifulSoup
import pandas as pd

OUTPUT_COLUMNS = ["TckrSymb", "FinancialPeriodEnd", "PublicationDate", "RevisedDate", "SequenceId", "TypeOfSubmission", "XBRLURL", "XBRLURLStatus", "DetailsURL", "DetailsURLStatus", "AuditedLabel", "AuditStatus", "ConsolidationLabel", "ConsolidationStatus", "FilingMetadataStatus", "NSELookupStatus", "SourceEvidenceID", "SourceURL", "SourceRequestParameters", "SourceRetrievedAtUTC", "SourceHTTPStatus", "SourceContentType", "SourcePayloadBytes", "SourcePayloadSHA256", "SourceRecordCount", "SourcePage", "SourcePageSize", "CaptureCoverageStatus", "CaptureLimitations", "RemarksText", "RemarksStatus", "RemarksEvidenceSHA256", "RemarksContentType", "VerificationStatus", "VerificationWarning"]
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

def _nse_capture_evidence(response, params, payload, items):
    """Record bounded response evidence; never infer pagination completeness."""
    from datetime import datetime, timezone
    import json
    body = getattr(response, "content", None)
    if not isinstance(body, bytes):
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest() if body else ""
    page, size = int(params.get("page", 0)), int(params.get("size", 0))
    total_pages = payload.get("totalPages", payload.get("total_pages")) if isinstance(payload, dict) else None
    try: total_pages = int(total_pages) if total_pages is not None else None
    except (TypeError, ValueError): total_pages = None
    if total_pages == 1 and page == 0:
        coverage, limits = "PAGINATION_COMPLETE_EXPLICIT_SINGLE_PAGE", ""
    elif total_pages is not None and total_pages > 1:
        coverage, limits = "PARTIAL_PAGINATION_PAGE_ONLY", f"ONLY_PAGE_{page}_OF_{total_pages}_CAPTURED"
    elif size and len(items) >= size:
        coverage, limits = "PAGE_LIMIT_REACHED_PAGINATION_UNKNOWN", "PAGE_SIZE_REACHED; TOTAL_PAGE_COUNT_NOT_CONFIRMED"
    else:
        coverage, limits = "PAGINATION_NOT_EXPOSED_SINGLE_PAGE_ONLY", "ONE_PAGE_CAPTURED; SOURCE_TOTAL_PAGES_NOT_CONFIRMED"
    identity = json.dumps({"url": NSE_RESULTS_API, "params": params, "payload_sha256": digest}, sort_keys=True, separators=(",", ":"))
    headers = getattr(response, "headers", {}) or {}
    return {"SourceEvidenceID": "nse-ifiling-" + hashlib.sha256(identity.encode()).hexdigest()[:20], "SourceURL": NSE_RESULTS_API, "SourceRequestParameters": json.dumps(params, sort_keys=True, separators=(",", ":")), "SourceRetrievedAtUTC": datetime.now(timezone.utc).isoformat(), "SourceHTTPStatus": str(getattr(response, "status_code", "") or "UNKNOWN"), "SourceContentType": str(headers.get("Content-Type", ""))[:160], "SourcePayloadBytes": len(body), "SourcePayloadSHA256": digest, "SourceRecordCount": len(items), "SourcePage": page, "SourcePageSize": size, "CaptureCoverageStatus": coverage, "CaptureLimitations": limits}

def audit_ecms_filing_metadata(filings: pd.DataFrame) -> pd.DataFrame:
    """Keep XBRL, Details, audit and basis as separate explicit source fields.

    Generic url fields are never promoted. The explicit API field details is
    accepted only when already an HTTPS URL on an NSE host. No URL is
    synthesized from another URL and no missing metadata is inferred.
    """
    rows = []
    for _, source in filings.iterrows():
        row = source.to_dict()
        xbrl = _value(row, ("xbrl", "xbrl_Link", "xbrlLink", "xbrl_url", "xbrlUrl", "OfficialXBRLURL"))
        if not xbrl:
            possible = _value(row, ("OfficialFilingURL",))
            if _official_https_url(possible) and urlsplit(possible).path.lower().endswith(".xml"):
                xbrl = possible
        details = _value(row, ("ixbrl", "iXBRL", "ixbrl_url", "ixbrlUrl", "details_url", "detailsUrl", "detailsURL", "detailUrl", "DetailsURL", "OfficialDetailsURL", "details"))
        if not _official_https_url(details) or not urlsplit(details).path.lower().endswith((".html", ".htm")):
            details = ""
        audited = _value(row, ("audited", "auditStatus", "audit_status", "AuditedLabel"))
        consolidation = _value(row, ("consolidated", "consolidation", "reportingBasis", "reporting_basis", "ConsolidationLabel"))
        xbrl_ok = _official_https_url(xbrl) and urlsplit(xbrl).path.lower().endswith(".xml")
        details_ok = _official_https_url(details) and urlsplit(details).path.lower().endswith((".html", ".htm"))
        audit_status = _label_status(audited, {"audited", "un audited", "unaudited"})
        basis_status = _label_status(consolidation, {"standalone", "consolidated"})
        metadata_ok = xbrl_ok and details_ok and audit_status == "EXPLICIT_LABEL_CAPTURED" and basis_status == "EXPLICIT_LABEL_CAPTURED"
        warnings = []
        if not xbrl_ok: warnings.append("EXPLICIT_OFFICIAL_XBRL_XML_URL_MISSING_OR_INVALID")
        if not details_ok: warnings.append("SEPARATE_OFFICIAL_DETAILS_HTML_URL_MISSING_OR_INVALID")
        if audit_status != "EXPLICIT_LABEL_CAPTURED": warnings.append("AUDIT_LABEL_MISSING_OR_UNRECOGNIZED")
        if basis_status != "EXPLICIT_LABEL_CAPTURED": warnings.append("REPORTING_BASIS_MISSING_OR_UNRECOGNIZED")
        rows.append({"TckrSymb": _value(row, ("TckrSymb", "symbol")).upper(), "FinancialPeriodEnd": _value(row, ("FinancialPeriodEnd", "qe_Date")), "PublicationDate": _value(row, ("PublicationDate", "creation_Date", "broadcast_Date")), "RevisedDate": _value(row, ("RevisedDate", "revised_Date")), "SequenceId": _value(row, ("SequenceId", "seq_Id")), "TypeOfSubmission": _value(row, ("TypeOfSubmission", "type_Sub")), "XBRLURL": xbrl, "XBRLURLStatus": "PASS" if xbrl_ok else "BLOCKED", "DetailsURL": details, "DetailsURLStatus": "PASS" if details_ok else "BLOCKED", "AuditedLabel": audited, "AuditStatus": audit_status, "ConsolidationLabel": consolidation, "ConsolidationStatus": basis_status, "FilingMetadataStatus": "EXPLICIT_METADATA_CAPTURED" if metadata_ok else "METADATA_INCOMPLETE",
            "NSELookupStatus": _value(row, ("FilingMetadataStatus",)) or "LOOKUP_STATUS_NOT_PROVIDED", **{column: row.get(column, "") for column in OUTPUT_COLUMNS if column.startswith("Source") or column.startswith("Capture")}, "VerificationStatus": "NOT_VERIFIED", "VerificationWarning": ";".join(warnings) if warnings else "Metadata only; Remarks/formula and XBRL reconciliation are still required"})
    result = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if not result.empty and {"TckrSymb", "FinancialPeriodEnd"}.issubset(result.columns):
        # Original/revised submissions are distinct filing variants when
        # NSE supplies a sequence or revision date. Only duplicate rows for
        # the same exact variant are ambiguous.
        variant_key = ["TckrSymb", "FinancialPeriodEnd", "AuditedLabel", "ConsolidationLabel"]
        for column in ("SequenceId", "RevisedDate"):
            if column in result.columns:
                variant_key.append(column)
        counts = result.groupby(variant_key, dropna=False)["TckrSymb"].transform("size")
        ambiguous = counts.gt(1)
        result.loc[ambiguous, "FilingMetadataStatus"] = "AMBIGUOUS_EXACT_FILING_MATCH"
        result.loc[ambiguous, "VerificationStatus"] = "NOT_VERIFIED"
        result.loc[ambiguous, "VerificationWarning"] = result.loc[ambiguous, "VerificationWarning"].astype(str) + ";MULTIPLE_EXACT_FILING_ROWS_REQUIRE_MANUAL_RECONCILIATION"
    return result

def fetch_ecms_details_remarks(
    audit: pd.DataFrame,
    session=None,
    timeout=(8, 35),
    max_bytes=2_000_000,
    max_attempts=2,
    retry_backoff=1.0,
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
            # Retry transient NSE archive network failures without relaxing validation.
            response = None
            attempts = max(1, int(max_attempts))
            for attempt in range(attempts):
                try:
                    response = client.get(
                        url, timeout=timeout, allow_redirects=True,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Referer": NSE_FILINGS_PAGE,
                        },
                    )
                    response.raise_for_status()
                    break
                except requests.exceptions.RequestException as exc:
                    status_code = getattr(getattr(exc, "response", None), "status_code", None)
                    retryable = isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)) or status_code in {429, 500, 502, 503, 504}
                    if not retryable or attempt + 1 >= attempts:
                        raise
                    retry_after = getattr(getattr(exc, "response", None), "headers", {}).get("Retry-After", "")
                    try:
                        delay = min(8.0, max(0.0, float(retry_after)))
                    except (TypeError, ValueError):
                        delay = min(8.0, max(0.0, float(retry_backoff)) * (2 ** attempt))
                    time.sleep(delay)
            if response is None:
                raise RuntimeError("NSE_DETAILS_FETCH_NO_RESPONSE")
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
            remarks_heading_found = False

            # NSE's iXBRL Details page renders Remarks as a section heading
            # followed by one or more table rows, not necessarily as a table
            # cell literally labelled "Remarks".
            for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                heading_text = " ".join(heading.get_text(" ", strip=True).lower().split()).rstrip(":")
                if heading_text != "remarks":
                    continue
                remarks_heading_found = True
                for element in heading.find_all_next(["h1", "h2", "h3", "h4", "h5", "h6", "tr", "p", "li"]):
                    if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                        break
                    if element.name == "tr":
                        cells = element.find_all(["td", "th"], recursive=False)
                        values = [" ".join(cell.get_text(" ", strip=True).split()) for cell in cells]
                        if len(values) >= 2 and any(values[1:]):
                            extracted.append(f"{values[0]}: {' | '.join(value for value in values[1:] if value)}".strip())
                    elif element.name in {"p", "li"}:
                        value = " ".join(element.get_text(" ", strip=True).split())
                        if value:
                            extracted.append(value)

            # Backward-compatible parser for explicitly labelled Remarks rows
            # in older NSE Details HTML layouts.
            if not remarks_heading_found:
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

            unique = list(dict.fromkeys(value for value in extracted if value))
            result["RemarksEvidenceSHA256"] = hashlib.sha256(body).hexdigest()
            if unique:
                result["RemarksText"] = "\n".join(unique)[:12000]
                result["RemarksStatus"] = "REMARKS_EXTRACTED"
            else:
                result["RemarksStatus"] = "REMARKS_SECTION_EMPTY" if remarks_heading_found else "REMARKS_NOT_FOUND"
        except Exception as exc:
            result["RemarksStatus"] = f"FETCH_OR_PARSE_ERROR:{type(exc).__name__}"
        rows.append(result)
    return pd.DataFrame(rows)


NSE_HOME = "https://www.nseindia.com/"
NSE_RESULTS_API = "https://www.nseindia.com/api/integrated-filing-results"
NSE_FILINGS_PAGE = "https://www.nseindia.com/companies-listing/corporate-integrated-filing"


def _parse_nse_date(value):
    """Parse known NSE/API date formats deterministically without dayfirst guessing."""
    from datetime import date, datetime

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw or raw.lower() in {"nan", "nat", "none", "<na>"}:
        return None
    formats = (
        "%Y-%m-%d", "%Y-%m-%d %H:%M:%S",
        "%d-%b-%Y", "%d-%b-%Y %H:%M:%S",
        "%d-%B-%Y", "%d-%B-%Y %H:%M:%S",
        "%d-%m-%Y", "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y", "%d/%m/%Y %H:%M:%S",
        "%Y/%m/%d", "%Y/%m/%d %H:%M:%S",
    )
    for date_format in formats:
        try:
            return datetime.strptime(raw, date_format).date()
        except ValueError:
            continue
    return None


def fetch_ecms_candidate_filing_metadata(
    candidates: pd.DataFrame,
    asof_date,
    session=None,
    timeout=35,
) -> pd.DataFrame:
    """Discover the latest eligible NSE Integrated Financial filing per symbol.

    FinancialPeriodEnd is optional. If supplied, it is treated as an exact
    period constraint; otherwise all available periods are requested and the
    latest period not after the cutoff is selected. All filing variants for
    that period (standalone/consolidated, audited/unaudited, original/revised)
    are retained separately. Metadata is never metric verification.
    """
    client = session or requests.Session()
    client.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": NSE_FILINGS_PAGE,
        "X-Requested-With": "XMLHttpRequest",
    })
    cutoff = _parse_nse_date(asof_date)
    if cutoff is None:
        return pd.DataFrame([{"TckrSymb": "", "FilingMetadataStatus": "INVALID_ASOF_DATE", "VerificationStatus": "NOT_VERIFIED", "VerificationWarning": "As-of date could not be parsed"}])
    try:
        client.get(NSE_HOME, timeout=timeout)
    except Exception:
        # Keep attempting the API; any cookie/session failure is reported below.
        pass

    output = []
    for _, candidate in candidates.iterrows():
        symbol = str(candidate.get("TckrSymb", "") or "").strip().upper()
        requested_period = _parse_nse_date(candidate.get("FinancialPeriodEnd"))
        if not symbol:
            output.append({
                "TckrSymb": symbol,
                "FilingMetadataStatus": "CANDIDATE_SYMBOL_INVALID",
                "VerificationStatus": "NOT_VERIFIED",
                "VerificationWarning": "A non-empty NSE symbol is required",
            })
            continue
        if requested_period is not None and requested_period > cutoff:
            output.append({
                "TckrSymb": symbol,
                "FinancialPeriodEnd": requested_period.isoformat(),
                "FilingMetadataStatus": "CANDIDATE_PERIOD_AFTER_CUTOFF",
                "VerificationStatus": "NOT_VERIFIED",
                "VerificationWarning": "Requested financial period is later than the as-of date",
            })
            continue

        params = {
            "index": "equities",
            "symbol": symbol,
            "period_ended": "all",
            "type": "Integrated Filing- Financials",
            "page": 0,
            "size": 1000,
        }
        try:
            response = client.get(NSE_RESULTS_API, params=params, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                items = [item for item in payload if isinstance(item, dict)]
            elif isinstance(payload, dict):
                raw = payload.get("data", payload.get("results", payload.get("records", [])))
                if isinstance(raw, dict):
                    raw = raw.get("data", raw.get("results", raw.get("records", [])))
                items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
            else:
                items = []
            capture_evidence = _nse_capture_evidence(response, params, payload, items)

            eligible = []
            for item in items:
                item_symbol = str(item.get("symbol", item.get("TckrSymb", "")) or "").strip().upper()
                item_period = _parse_nse_date(item.get("qe_Date", item.get("FinancialPeriodEnd", "")))
                pub_date = _parse_nse_date(item.get("creation_Date", item.get("broadcast_Date", item.get("PublicationDate", ""))))
                if item_symbol != symbol or item_period is None or item_period > cutoff:
                    continue
                if requested_period is not None and item_period != requested_period:
                    continue
                # A missing broadcast/publication date is not silently treated as eligible.
                if pub_date is None or pub_date > cutoff:
                    continue
                eligible.append((item_period, pub_date, item))

            if not eligible:
                output.append({
                    "TckrSymb": symbol,
                    "FinancialPeriodEnd": requested_period.isoformat() if requested_period else "",
                    "FilingMetadataStatus": "NO_ELIGIBLE_NSE_FILING",
                    "VerificationStatus": "NOT_VERIFIED",
                    "VerificationWarning": "No exact symbol filing with a valid period and publication date on/before cutoff was returned",
                    **capture_evidence,
                })
                continue

            selected_period = requested_period or max(entry[0] for entry in eligible)
            selected = [entry for entry in eligible if entry[0] == selected_period]
            for item_period, pub_date, item in sorted(selected, key=lambda entry: (entry[1], str(entry[2].get("seq_Id", "")))):
                output.append({
                    "TckrSymb": symbol,
                    "FinancialPeriodEnd": item_period.isoformat(),
                    "PublicationDate": pub_date.isoformat(),
                    "RevisedDate": str(item.get("revised_Date", "") or ""),
                    "SequenceId": str(item.get("seq_Id", "") or ""),
                    "TypeOfSubmission": str(item.get("type_Sub", "") or ""),
                    "xbrl": item.get("xbrl", item.get("xbrl_Link", item.get("xbrlLink", ""))),
                    # NSE's Integrated Filing API exposes the official HTML
                    # Details attachment as ixbrl, distinct from the XML xbrl.
                    "details": item.get("ixbrl", item.get("iXBRL", item.get("details_url", item.get("details", "")))),
                    "audited": item.get("audited", ""),
                    "consolidated": item.get("consolidated", ""),
                    "OfficialSource": "NSE Integrated Filing - Financials",
                    "FilingMetadataStatus": "RAW_LATEST_PERIOD_NSE_API_ROW" if requested_period is None else "RAW_EXACT_NSE_API_ROW",
                    "VerificationStatus": "NOT_VERIFIED",
                    "VerificationWarning": "NSE filing metadata only; audit basis, revision choice, Remarks/formula and XBRL facts still require reconciliation",
                    **capture_evidence,
                })
        except Exception as exc:
            output.append({
                "TckrSymb": symbol,
                "FinancialPeriodEnd": requested_period.isoformat() if requested_period else "",
                "FilingMetadataStatus": "NSE_API_LOOKUP_ERROR",
                "VerificationStatus": "NOT_VERIFIED",
                "VerificationWarning": f"{type(exc).__name__}: {str(exc)[:240]}",
                "SourceURL": NSE_RESULTS_API,
                "SourceRequestParameters": __import__("json").dumps(params, sort_keys=True, separators=(",", ":")),
                "SourceRetrievedAtUTC": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "SourceHTTPStatus": str(getattr(getattr(exc, "response", None), "status_code", "") or "UNKNOWN"),
                "SourcePayloadBytes": 0,
                "SourcePayloadSHA256": "",
                "SourceRecordCount": 0,
                "SourcePage": int(params.get("page", 0)),
                "SourcePageSize": int(params.get("size", 0)),
                "CaptureCoverageStatus": "SOURCE_CAPTURE_FAILED",
                "CaptureLimitations": f"{type(exc).__name__}:{str(exc)[:180]}",
            })
    return pd.DataFrame(output)
