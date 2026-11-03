"""Conservative extraction of candidate financial facts from official NSE XBRL XML.

This is an evidence/audit layer only. It does not mutate fundamental_metrics.csv,
calculate TTM, select a preferred accounting tag, or mark any value VERIFIED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


FACT_CATEGORIES = {
    "RevenueFromOperations": "REVENUE",
    "ProfitLossForPeriod": "NET_PROFIT",
    "ProfitLossForPeriodFromContinuingOperations": "NET_PROFIT_CONTINUING",
    "ProfitBeforeTax": "PROFIT_BEFORE_TAX",
    "TaxExpense": "TAX_EXPENSE",
    "NetProfitAfterTax": "NET_PROFIT_AFTER_TAX_CANDIDATE",
    "CashAndCashEquivalents": "CASH_BALANCE_INSTANT",
    "CashAndCashEquivalentsCashFlowStatement": "CASH_BALANCE_INSTANT",
    "CashFlowsFromUsedInOperations": "CASH_FLOW_OPERATIONS_CANDIDATE",
    "CashFlowsFromUsedInOperatingActivities": "OPERATING_CASH_FLOW_CANDIDATE",
    "CashFlowsFromUsedInInvestingActivities": "INVESTING_CASH_FLOW_CANDIDATE",
    "CashFlowsFromUsedInFinancingActivities": "FINANCING_CASH_FLOW_CANDIDATE",
    "IncreaseDecreaseInCashAndCashEquivalents": "NET_CHANGE_CASH_CANDIDATE",
    "IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges": "NET_CHANGE_CASH_PRE_FX_CANDIDATE",
    "EffectOfExchangeRateChangesOnCashAndCashEquivalents": "FX_EFFECT_CASH_CHANGE_CANDIDATE",
}
IDENTITY_TAGS = {"Symbol", "ScripCode", "NatureOfReportStandaloneConsolidated"}


def _local(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _context_details(root) -> dict[str, dict]:
    result = {}
    for node in root.iter():
        if _local(node.tag).lower() != "context":
            continue
        cid = node.attrib.get("id", "")
        period = next((c for c in node if _local(c.tag).lower() == "period"), None)
        dates = {}
        if period is not None:
            for child in period:
                dates[_local(child.tag).lower()] = (child.text or "").strip()
        entity_identifier = ""
        entity_scheme = ""
        entity = next((c for c in node if _local(c.tag).lower() == "entity"), None)
        if entity is not None:
            for child in entity:
                if _local(child.tag).lower() == "identifier":
                    entity_identifier = (child.text or "").strip()
                    entity_scheme = child.attrib.get("scheme", "")
                    break
        dimensions = []
        # XBRL dimensions may be inside entity/segment or scenario; inspect the
        # whole context subtree rather than assuming one placement.
        for child in node.iter():
            lname = _local(child.tag).lower()
            if lname == "explicitmember":
                dimensions.append({
                    "kind": "explicit",
                    "dimension": child.attrib.get("dimension", ""),
                    "member": (child.text or "").strip(),
                })
            elif lname == "typedmember":
                value = "".join((part.text or "") for part in child.iter() if part is not child).strip()
                dimensions.append({
                    "kind": "typed",
                    "dimension": child.attrib.get("dimension", ""),
                    "value": value[:300],
                })
        result[cid] = {
            "period": dates,
            "entity_identifier": entity_identifier,
            "entity_identifier_scheme": entity_scheme,
            "dimensions": dimensions,
        }
    return result


def _period_class(period: dict) -> tuple[str, int | None]:
    instant = period.get("instant", "")
    if instant:
        return "INSTANT", None
    start, end = period.get("startdate", ""), period.get("enddate", "")
    try:
        start_d, end_d = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        return "UNKNOWN_PERIOD", None
    if end_d < start_d:
        return "INVALID_PERIOD", None
    days = (end_d - start_d).days + 1

    # A standalone quarter must align exactly to a calendar quarter. Merely
    # having ~90 days is not sufficient to call an arbitrary duration quarterly.
    quarter_starts = {(1, 1), (4, 1), (7, 1), (10, 1)}
    if (start_d.month, start_d.day) in quarter_starts:
        expected_end_month = ((start_d.month - 1 + 2) % 12) + 1
        expected_end_year = start_d.year + (1 if start_d.month == 10 else 0)
        import calendar
        expected_end_day = calendar.monthrange(expected_end_year, expected_end_month)[1]
        if (end_d.year, end_d.month, end_d.day) == (
            expected_end_year, expected_end_month, expected_end_day
        ):
            return "QUARTERLY_3M_CANDIDATE", days

    # Indian fiscal-year YTD/annual periods begin on 1 April.
    if start_d.month == 4 and start_d.day == 1:
        if end_d.month == 9 and end_d.day == 30 and end_d.year == start_d.year:
            return "YTD_6M_CANDIDATE", days
        if end_d.month == 12 and end_d.day == 31 and end_d.year == start_d.year:
            return "YTD_9M_CANDIDATE", days
        if end_d.month == 3 and end_d.day == 31 and end_d.year == start_d.year + 1:
            return "ANNUAL_12M_CANDIDATE", days
    if days in range(179, 185):
        return "DURATION_6M_OTHER", days
    if days in range(269, 276):
        return "DURATION_9M_OTHER", days
    if days in range(360, 367):
        return "DURATION_12M_OTHER", days
    return "OTHER_DURATION", days


def _numeric_value(node) -> tuple[str, str]:
    raw = (node.text or "").strip()
    if not raw:
        return raw, ""
    try:
        value = Decimal(raw)
        scale = node.attrib.get("scale", "")
        if scale:
            value *= Decimal(10) ** int(scale)
        if node.attrib.get("sign") == "-":
            value = -value
        return raw, format(value, "f")
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return raw, ""


def _unit_map(root) -> dict[str, str]:
    units = {}
    for node in root.iter():
        if _local(node.tag).lower() == "unit":
            unit_id = node.attrib.get("id", "")
            measures = [(m.text or "").strip() for m in node.iter()
                        if _local(m.tag).lower() == "measure"]
            units[unit_id] = "*".join(measures)
    return units


def inspect_filing(xml_path: str | Path, *, expected_symbol: str = "",
                   expected_period_end: str = "", official_filing_url: str = "",
                   publication_date: str = "") -> dict:
    root = ET.parse(xml_path).getroot()
    contexts = _context_details(root)
    units = _unit_map(root)
    identity = {"Symbol": [], "ScripCode": [], "ReportingBasisByContext": {}}
    facts = []

    # Read filing identity and reporting-basis declarations first.
    leaf_nodes = [n for n in root.iter()
                  if len(n) == 0 and "contextRef" in n.attrib and n.text and n.text.strip()]
    for node in leaf_nodes:
        tag = _local(node.tag)
        context_ref = node.attrib.get("contextRef", "")
        value = node.text.strip()
        if tag == "Symbol":
            identity["Symbol"].append(value.upper())
        elif tag == "ScripCode":
            identity["ScripCode"].append(value)
        elif tag == "NatureOfReportStandaloneConsolidated":
            identity["ReportingBasisByContext"][context_ref] = value.strip().upper()

    symbols = sorted(set(identity["Symbol"]))
    symbol_match = bool(expected_symbol and symbols and symbols == [expected_symbol.strip().upper()])
    expected_end = str(expected_period_end or "").strip()
    observed_ends = sorted({
        details["period"].get("enddate", details["period"].get("instant", ""))
        for details in contexts.values()
        if details["period"].get("enddate") or details["period"].get("instant")
    })
    period_end_match = not expected_end or expected_end in observed_ends

    for node in leaf_nodes:
        tag = _local(node.tag)
        category = FACT_CATEGORIES.get(tag)
        if not category:
            continue
        context_ref = node.attrib.get("contextRef", "")
        context = contexts.get(context_ref, {})
        period = context.get("period", {})
        period_class, duration_days = _period_class(period)
        raw, numeric = _numeric_value(node)
        if not numeric:
            continue
        facts.append({
            "FactTag": tag,
            "FactCategory": category,
            "ContextRef": context_ref,
            "ContextStartDate": period.get("startdate", ""),
            "ContextEndDate": period.get("enddate", ""),
            "ContextInstant": period.get("instant", ""),
            "DurationDays": duration_days if duration_days is not None else "",
            "PeriodClass": period_class,
            "ReportingBasis": identity["ReportingBasisByContext"].get(context_ref, "UNKNOWN"),
            "ReportingBasisEvidence": (
                "XML_DECLARATION_PRESENT"
                if context_ref in identity["ReportingBasisByContext"] else "MISSING_XML_DECLARATION"
            ),
            "EntityIdentifier": context.get("entity_identifier", ""),
            "EntityIdentifierScheme": context.get("entity_identifier_scheme", ""),
            "DimensionsJSON": json.dumps(context.get("dimensions", []), ensure_ascii=False, sort_keys=True),
            "HasDimensions": bool(context.get("dimensions", [])),
            "UnitRef": node.attrib.get("unitRef", ""),
            "UnitMeasure": units.get(node.attrib.get("unitRef", ""), ""),
            "Decimals": node.attrib.get("decimals", ""),
            "Scale": node.attrib.get("scale", ""),
            "Sign": node.attrib.get("sign", ""),
            "RawValue": raw,
            "ParsedNumericValue": numeric,
            "FactVerificationStatus": "CANDIDATE_ONLY_NOT_VERIFIED",
        })

    parsed_url = urlparse(str(official_filing_url or ""))
    official_url_status = (
        "OFFICIAL_NSE_HTTPS_HOST"
        if parsed_url.scheme == "https" and (parsed_url.hostname or "").lower()
        in {"nsearchives.nseindia.com", "www.nseindia.com", "nseindia.com"}
        else "URL_NOT_CONFIRMED_OFFICIAL_NSE"
    )
    identity_status = "MATCH" if symbol_match else (
        "MISSING_EXPECTED_OR_XML_SYMBOL" if not expected_symbol or not symbols
        else "SYMBOL_MISMATCH"
    )
    if not period_end_match:
        identity_status += "|PERIOD_END_MISMATCH"
    if expected_period_end and not observed_ends:
        identity_status += "|XML_PERIOD_END_MISSING"

    return {
        "ExpectedSymbol": expected_symbol,
        "XMLSymbols": symbols,
        "ScripCodes": sorted(set(identity["ScripCode"])),
        "ExpectedFinancialPeriodEnd": expected_end,
        "ObservedContextPeriodEnds": observed_ends,
        "PublicationDateFromSourceCSV": publication_date,
        "OfficialFilingURL": official_filing_url,
        "FilingIdentityStatus": identity_status,
        "OfficialFilingURLStatus": official_url_status,
        "ContextCount": len(contexts),
        "NumericCandidateFactCount": len(facts),
        "Facts": facts,
    }


def run_audit(diagnostic_json: str | Path, output_dir: str | Path) -> dict:
    diagnostic_path = Path(diagnostic_json)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not diagnostic_path.exists():
        report = {"status": "DIAGNOSTIC_INPUT_MISSING", "sample_count": 0, "success_count": 0,
                  "failure_count": 0, "facts": []}
    else:
        source = json.loads(diagnostic_path.read_text(encoding="utf-8"))
        results, flat = [], []
        for item in source.get("results", []):
            if item.get("download_status") != "SUCCESS":
                results.append({"TckrSymb": item.get("TckrSymb", ""),
                                "status": "SOURCE_XML_NOT_AVAILABLE"})
                continue
            xml_path = Path(item.get("xml_path", ""))
            # Workflow paths are repository-relative; callers may supply an
            # alternate diagnostic artifact root via the current working dir.
            if not xml_path.exists():
                results.append({"TckrSymb": item.get("TckrSymb", ""),
                                "status": "XML_PATH_NOT_FOUND", "xml_path": str(xml_path)})
                continue
            try:
                parsed = inspect_filing(
                    xml_path,
                    expected_symbol=str(item.get("TckrSymb", "")),
                    expected_period_end=str(item.get("FinancialPeriodEnd", "")),
                    official_filing_url=str(item.get("OfficialFilingURL", "")),
                    publication_date=str(item.get("PublicationDate", "")),
                )
                parsed["TckrSymb"] = item.get("TckrSymb", "")
                parsed["status"] = "EXTRACTED"
                results.append(parsed)
                for fact in parsed["Facts"]:
                    flat.append({
                        "TckrSymb": parsed["TckrSymb"],
                        "OfficialFilingURL": parsed["OfficialFilingURL"],
                        "PublicationDateFromSourceCSV": parsed["PublicationDateFromSourceCSV"],
                        "FilingIdentityStatus": parsed["FilingIdentityStatus"],
                        "OfficialFilingURLStatus": parsed["OfficialFilingURLStatus"],
                        **fact,
                    })
            except Exception as exc:
                results.append({"TckrSymb": item.get("TckrSymb", ""),
                                "status": "PARSE_FAILED",
                                "error": f"{type(exc).__name__}: {exc}"[:500]})
        report = {
            "status": "SUCCESS" if any(r.get("status") == "EXTRACTED" for r in results)
                      else "NO_XML_EXTRACTED",
            "sample_count": len(source.get("results", [])),
            "success_count": sum(r.get("status") == "EXTRACTED" for r in results),
            "failure_count": sum(r.get("status") != "EXTRACTED" for r in results),
            "results": results,
            "facts": flat,
            "safety_note": "Extracted values are candidates only; this report does not verify accounting tags, periods, publication cutoffs, or TTM calculations.",
        }
    (output / "xbrl_financial_fact_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    pd.DataFrame(report.get("facts", [])).to_csv(
        output / "xbrl_financial_fact_candidates.csv", index=False
    )
    summary_rows = []
    for result in report.get("results", []):
        summary_rows.append({
            "TckrSymb": result.get("TckrSymb", ""),
            "Status": result.get("status", ""),
            "FilingIdentityStatus": result.get("FilingIdentityStatus", ""),
            "OfficialFilingURLStatus": result.get("OfficialFilingURLStatus", ""),
            "XMLSymbols": ";".join(result.get("XMLSymbols", [])),
            "ScripCodes": ";".join(result.get("ScripCodes", [])),
            "ContextCount": result.get("ContextCount", ""),
            "NumericCandidateFactCount": result.get("NumericCandidateFactCount", ""),
        })
    pd.DataFrame(summary_rows).to_csv(output / "xbrl_financial_fact_audit_summary.csv", index=False)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic-json", default="outputs/xbrl_sample_diagnostics/xbrl_sample_diagnostic.json")
    parser.add_argument("--output", default="outputs/xbrl_financial_fact_audit")
    args = parser.parse_args(argv)
    report = run_audit(args.diagnostic_json, args.output)
    print(json.dumps({k: report.get(k) for k in
                      ("status", "sample_count", "success_count", "failure_count")}))
    # Audit failures are reported in output files and remain non-blocking for EOD scanning.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
