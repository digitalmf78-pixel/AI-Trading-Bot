"""Audit arithmetic relationships in official NSE XBRL financial statements.

This module is deliberately read-only: it never writes fundamental_metrics.csv,
selects a provider value, calculates TTM, or marks any fact VERIFIED.  It checks
whether reported subtotals reconcile within XBRL precision and emits evidence
for human/taxonomy review.
"""
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from nse_xbrl_financial_fact_audit import _period_class

# Standard line items needed to reconcile the reported P&L and cash-flow totals.
AUDIT_TAGS = {
    "RevenueFromOperations", "OtherIncome", "Income", "Expenses",
    "ProfitBeforeExceptionalItemsAndTax", "ExceptionalItemsBeforeTax",
    "ProfitBeforeTax", "CurrentTax", "DeferredTax", "TaxExpense",
    "ProfitLossForPeriodFromContinuingOperations", "ProfitLossFromDiscontinuedOperationsAfterTax",
    "ProfitLossForPeriod", "NetProfitAfterTax",
    "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod",
    "CashFlowsFromUsedInOperations", "CashFlowsFromUsedInOperatingActivities",
    "CashFlowsFromUsedInInvestingActivities", "CashFlowsFromUsedInFinancingActivities",
    "IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges",
    "IncreaseDecreaseInCashAndCashEquivalents", "CashAndCashEquivalentsCashFlowStatement",
}


def _local(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _namespace(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def _decimal_value(node) -> Decimal | None:
    raw = (node.text or "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
        scale = node.attrib.get("scale", "")
        if scale:
            value *= Decimal(10) ** int(scale)
        if node.attrib.get("sign") == "-":
            value = -value
        return value
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return None


def _context_map(root) -> dict[str, dict]:
    result = {}
    for node in root.iter():
        if _local(node.tag).lower() != "context":
            continue
        cid = node.attrib.get("id", "")
        period_node = next((c for c in node if _local(c.tag).lower() == "period"), None)
        period = {}
        if period_node is not None:
            period = {_local(c.tag).lower(): (c.text or "").strip() for c in period_node}
        entity_id = ""
        entity_scheme = ""
        entity = next((c for c in node if _local(c.tag).lower() == "entity"), None)
        if entity is not None:
            identifier = next((c for c in entity if _local(c.tag).lower() == "identifier"), None)
            if identifier is not None:
                entity_id = (identifier.text or "").strip()
                entity_scheme = identifier.attrib.get("scheme", "")
        dimensions = []
        for child in node.iter():
            if _local(child.tag).lower() == "explicitmember":
                dimensions.append({"kind": "explicit", "dimension": child.attrib.get("dimension", ""),
                                   "member": (child.text or "").strip()})
            elif _local(child.tag).lower() == "typedmember":
                typed_value = "".join((p.text or "") for p in child.iter() if p is not child).strip()
                dimensions.append({"kind": "typed", "dimension": child.attrib.get("dimension", ""),
                                   "value": typed_value[:300]})
        result[cid] = {"period": period, "entity_identifier": entity_id,
                       "entity_identifier_scheme": entity_scheme, "dimensions": dimensions}
    return result


def _unit_map(root) -> dict[str, str]:
    result = {}
    for node in root.iter():
        if _local(node.tag).lower() == "unit":
            result[node.attrib.get("id", "")] = "*".join(
                (m.text or "").strip() for m in node.iter() if _local(m.tag).lower() == "measure"
            )
    return result


def _rounding_tolerance(facts: list[dict]) -> Decimal:
    """Conservative sum of half-unit rounding bounds from XBRL decimals."""
    tolerance = Decimal(0)
    for fact in facts:
        decimals = fact.get("decimals", "")
        if decimals in ("", "INF", "inf", None):
            continue
        try:
            tolerance += (Decimal(10) ** (-int(decimals))) / Decimal(2)
        except (ValueError, InvalidOperation, OverflowError):
            continue
    return tolerance


def _check(name: str, lhs: Decimal, rhs: Decimal, used_facts: list[dict],
           note: str = "") -> dict:
    delta = lhs - rhs
    tolerance = _rounding_tolerance(used_facts)
    return {"Check": name, "LeftValue": str(lhs), "RightValue": str(rhs),
            "Difference": str(delta), "RoundingTolerance": str(tolerance),
            "Status": "PASS_WITHIN_XBRL_ROUNDING" if abs(delta) <= tolerance else "MISMATCH",
            "Note": note}


def inspect_statement(xml_path: str | Path, *, symbol: str = "",
                      official_filing_url: str = "", publication_date: str = "") -> dict:
    root = ET.parse(xml_path).getroot()
    contexts = _context_map(root)
    units = _unit_map(root)
    basis_by_context = {}
    xml_symbols = set()
    scrip_codes = set()
    for node in root.iter():
        if len(node) != 0 or "contextRef" not in node.attrib or not node.text:
            continue
        tag = _local(node.tag)
        value = node.text.strip()
        if tag == "Symbol":
            xml_symbols.add(value.upper())
        elif tag == "ScripCode":
            scrip_codes.add(value)
        elif tag == "NatureOfReportStandaloneConsolidated":
            basis_by_context[node.attrib.get("contextRef", "")] = value.upper()

    by_context: dict[str, dict[str, list[dict]]] = {}
    facts_flat = []
    for node in root.iter():
        if len(node) != 0 or "contextRef" not in node.attrib:
            continue
        tag = _local(node.tag)
        if tag not in AUDIT_TAGS:
            continue
        value = _decimal_value(node)
        if value is None:
            continue
        context_ref = node.attrib.get("contextRef", "")
        context = contexts.get(context_ref, {})
        period = context.get("period", {})
        period_class, duration_days = _period_class(period)
        unit_ref = node.attrib.get("unitRef", "")
        fact = {
            "Tag": tag, "Namespace": _namespace(node.tag), "ContextRef": context_ref,
            "StartDate": period.get("startdate", ""), "EndDate": period.get("enddate", ""),
            "Instant": period.get("instant", ""), "PeriodClass": period_class,
            "DurationDays": duration_days if duration_days is not None else "",
            "ReportingBasis": basis_by_context.get(context_ref, "UNKNOWN"),
            "DimensionsJSON": json.dumps(context.get("dimensions", []), ensure_ascii=False, sort_keys=True),
            "EntityIdentifier": context.get("entity_identifier", ""),
            "EntityIdentifierScheme": context.get("entity_identifier_scheme", ""),
            "UnitRef": unit_ref, "UnitMeasure": units.get(unit_ref, ""),
            "Decimals": node.attrib.get("decimals", ""), "Scale": node.attrib.get("scale", ""),
            "Sign": node.attrib.get("sign", ""), "RawValue": (node.text or "").strip(),
            "Value": str(value), "VerificationStatus": "CANDIDATE_ONLY_NOT_VERIFIED",
        }
        facts_flat.append(fact)
        by_context.setdefault(context_ref, {}).setdefault(tag, []).append(fact)

    checks = []
    context_summaries = []
    for context_ref, tag_map in by_context.items():
        period = contexts.get(context_ref, {}).get("period", {})
        period_class, _ = _period_class(period)
        basis = basis_by_context.get(context_ref, "UNKNOWN")
        context_summaries.append({"ContextRef": context_ref, "PeriodClass": period_class,
                                  "StartDate": period.get("startdate", ""),
                                  "EndDate": period.get("enddate", ""),
                                  "Instant": period.get("instant", ""),
                                  "ReportingBasis": basis,
                                  "DimensionsJSON": json.dumps(contexts.get(context_ref, {}).get("dimensions", []),
                                                                ensure_ascii=False, sort_keys=True)})

        def one(tag: str):
            values = tag_map.get(tag, [])
            return values[0] if len(values) == 1 else None

        def numeric(tag: str):
            fact = one(tag)
            return (Decimal(fact["Value"]), fact) if fact else (None, None)

        # Income = Revenue from operations + Other income.
        rev, rev_f = numeric("RevenueFromOperations")
        other, other_f = numeric("OtherIncome")
        income, income_f = numeric("Income")
        if all(x is not None for x in (rev, other, income)):
            checks.append({**_check("INCOME_EQUALS_REVENUE_PLUS_OTHER_INCOME", income, rev + other,
                                    [rev_f, other_f, income_f]), "ContextRef": context_ref,
                           "PeriodClass": period_class, "ReportingBasis": basis})

        # PBT = PBT before exceptional items + exceptional items.
        pre_exc, pre_exc_f = numeric("ProfitBeforeExceptionalItemsAndTax")
        exceptional, exceptional_f = numeric("ExceptionalItemsBeforeTax")
        pbt, pbt_f = numeric("ProfitBeforeTax")
        if all(x is not None for x in (pre_exc, exceptional, pbt)):
            checks.append({**_check("PBT_EQUALS_PRE_EXCEPTIONAL_PLUS_EXCEPTIONAL", pbt,
                                    pre_exc + exceptional, [pre_exc_f, exceptional_f, pbt_f]),
                           "ContextRef": context_ref, "PeriodClass": period_class,
                           "ReportingBasis": basis})

        # Continuing profit = PBT less reported tax expense.
        tax, tax_f = numeric("TaxExpense")
        cont_profit, cont_f = numeric("ProfitLossForPeriodFromContinuingOperations")
        if all(x is not None for x in (pbt, tax, cont_profit)):
            checks.append({**_check("CONTINUING_PROFIT_EQUALS_PBT_LESS_TAX", cont_profit,
                                    pbt - tax, [pbt_f, tax_f, cont_f]),
                           "ContextRef": context_ref, "PeriodClass": period_class,
                           "ReportingBasis": basis})

        # Total profit includes discontinued operations and equity-accounted associates.
        disc, disc_f = numeric("ProfitLossFromDiscontinuedOperationsAfterTax")
        associates, associates_f = numeric("ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod")
        total_profit, total_f = numeric("ProfitLossForPeriod")
        if all(x is not None for x in (cont_profit, disc, associates, total_profit)):
            checks.append({**_check("TOTAL_PROFIT_EQUALS_CONTINUING_PLUS_DISCONTINUED_PLUS_ASSOCIATES",
                                    total_profit, cont_profit + disc + associates,
                                    [cont_f, disc_f, associates_f, total_f]),
                           "ContextRef": context_ref, "PeriodClass": period_class,
                           "ReportingBasis": basis})

        current_tax, current_tax_f = numeric("CurrentTax")
        deferred_tax, deferred_tax_f = numeric("DeferredTax")
        if all(x is not None for x in (current_tax, deferred_tax, tax)):
            checks.append({**_check("TAX_EXPENSE_EQUALS_CURRENT_PLUS_DEFERRED",
                                    tax, current_tax + deferred_tax,
                                    [current_tax_f, deferred_tax_f, tax_f]),
                           "ContextRef": context_ref, "PeriodClass": period_class,
                           "ReportingBasis": basis})

        # IAS 7 statement cross-foot: net CFO + CFI + CFF = net change in cash.
        cfo, cfo_f = numeric("CashFlowsFromUsedInOperatingActivities")
        cfi, cfi_f = numeric("CashFlowsFromUsedInInvestingActivities")
        cff, cff_f = numeric("CashFlowsFromUsedInFinancingActivities")
        cash_change, cash_change_f = numeric("IncreaseDecreaseInCashAndCashEquivalents")
        if all(x is not None for x in (cfo, cfi, cff, cash_change)):
            checks.append({**_check("CFO_PLUS_CFI_PLUS_CFF_EQUALS_NET_CASH_CHANGE",
                                    cfo + cfi + cff, cash_change,
                                    [cfo_f, cfi_f, cff_f, cash_change_f],
                                    "CashFlowsFromUsedInOperatingActivities is the operating total used in the cash-flow cross-foot."),
                           "ContextRef": context_ref, "PeriodClass": period_class,
                           "ReportingBasis": basis})

    # Preserve cross-context conflicts rather than choosing a preferred tag/context.
    anomalies = []
    period_profit_facts = [f for f in facts_flat if f["Tag"] == "ProfitLossForPeriod"]
    for candidate in (f for f in facts_flat if f["Tag"] == "NetProfitAfterTax"):
        same_period = [f for f in period_profit_facts
                       if f["StartDate"] == candidate["StartDate"]
                       and f["EndDate"] == candidate["EndDate"]
                       and f["Instant"] == candidate["Instant"]]
        for reported in same_period:
            if (candidate["Value"] != reported["Value"] and
                    (candidate["ReportingBasis"] == "UNKNOWN" or candidate["DimensionsJSON"] != "[]")):
                anomalies.append({
                    "Code": "DIMENSIONED_NET_PROFIT_AFTER_TAX_CONFLICT",
                    "ContextRef": candidate["ContextRef"],
                    "ComparedContextRef": reported["ContextRef"],
                    "PeriodStart": candidate["StartDate"], "PeriodEnd": candidate["EndDate"],
                    "CandidateValue": candidate["Value"], "UndimensionedProfitLossForPeriod": reported["Value"],
                    "CandidateReportingBasis": candidate["ReportingBasis"],
                    "CandidateDimensionsJSON": candidate["DimensionsJSON"],
                    "Status": "REQUIRES_DIMENSIONAL_AND_STATEMENT_RECONCILIATION",
                    "Note": "No canonical value selected; both facts remain candidate-only.",
                })

    # Determine availability from actual fact contexts, never infer a missing quarter.
    q4_cashflow_contexts = sorted({f["ContextRef"] for f in facts_flat
                                   if f["Tag"] == "CashFlowsFromUsedInOperatingActivities"
                                   and f["PeriodClass"] == "QUARTERLY_3M_CANDIDATE"})
    annual_cashflow_contexts = sorted({f["ContextRef"] for f in facts_flat
                                       if f["Tag"] == "CashFlowsFromUsedInOperatingActivities"
                                       and f["PeriodClass"] == "ANNUAL_12M_CANDIDATE"})
    identity_status = "MATCH" if symbol and xml_symbols == {symbol.upper()} else "IDENTITY_NOT_CONFIRMED"
    return {
        "Symbol": symbol, "XMLSymbols": sorted(xml_symbols), "ScripCodes": sorted(scrip_codes),
        "IdentityStatus": identity_status, "OfficialFilingURL": official_filing_url,
        "PublicationDateFromSourceCSV": publication_date,
        "ContextCount": len(contexts), "FactCount": len(facts_flat),
        "Facts": facts_flat, "Contexts": context_summaries, "ReconciliationChecks": checks,
        "Anomalies": anomalies,
        "Q4OperatingCashFlowContexts": q4_cashflow_contexts,
        "AnnualOperatingCashFlowContexts": annual_cashflow_contexts,
        "QuarterlyOperatingCashFlowAvailability": (
            "PRESENT_AS_CANDIDATE" if q4_cashflow_contexts else "NO_Q4_CFO_FACT_IN_SAMPLE"),
        "CFOArithmeticEvidence": (
            "ANNUAL_CFO_TAG_RECONCILES_TO_NET_CASH_CHANGE" if any(
                c["Check"] == "CFO_PLUS_CFI_PLUS_CFF_EQUALS_NET_CASH_CHANGE" and
                c["Status"] == "PASS_WITHIN_XBRL_ROUNDING" for c in checks
            ) else "NO_SUCCESSFUL_CFO_CROSSFOOT"),
        "SafetyNote": "All values remain candidate-only. Arithmetic reconciliation is supporting evidence, not taxonomy or filing verification.",
    }


def run_reconciliation(diagnostic_json: str | Path, output_dir: str | Path) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source_path = Path(diagnostic_json)
    if not source_path.exists():
        report = {"Status": "DIAGNOSTIC_INPUT_MISSING", "SampleCount": 0,
                  "SuccessCount": 0, "FailureCount": 0, "Results": []}
    else:
        source = json.loads(source_path.read_text(encoding="utf-8"))
        results = []
        all_facts, all_checks, all_contexts, all_anomalies = [], [], [], []
        for item in source.get("results", []):
            if item.get("download_status") != "SUCCESS":
                results.append({"Symbol": item.get("TckrSymb", ""), "Status": "SOURCE_XML_NOT_AVAILABLE"})
                continue
            xml_path = Path(item.get("xml_path", ""))
            if not xml_path.exists():
                results.append({"Symbol": item.get("TckrSymb", ""), "Status": "XML_PATH_NOT_FOUND",
                                "XMLPath": str(xml_path)})
                continue
            try:
                result = inspect_statement(xml_path, symbol=str(item.get("TckrSymb", "")),
                                           official_filing_url=str(item.get("OfficialFilingURL", "")),
                                           publication_date=str(item.get("PublicationDate", "")))
                result["Status"] = "AUDITED_CANDIDATE"
                results.append(result)
                for fact in result["Facts"]:
                    all_facts.append({"Symbol": result["Symbol"], **fact})
                for check in result["ReconciliationChecks"]:
                    all_checks.append({"Symbol": result["Symbol"], **check})
                for context in result["Contexts"]:
                    all_contexts.append({"Symbol": result["Symbol"], **context})
                for anomaly in result["Anomalies"]:
                    all_anomalies.append({"Symbol": result["Symbol"], **anomaly})
            except Exception as exc:
                results.append({"Symbol": item.get("TckrSymb", ""), "Status": "PARSE_FAILED",
                                "Error": f"{type(exc).__name__}: {exc}"[:500]})
        report = {"Status": "SUCCESS" if any(r.get("Status") == "AUDITED_CANDIDATE" for r in results)
                  else "NO_XML_AUDITED", "SampleCount": len(source.get("results", [])),
                  "SuccessCount": sum(r.get("Status") == "AUDITED_CANDIDATE" for r in results),
                  "FailureCount": sum(r.get("Status") != "AUDITED_CANDIDATE" for r in results),
                  "Results": results, "SafetyNote": "No fact is promoted to VERIFIED.",
                  "Facts": all_facts, "Checks": all_checks, "Contexts": all_contexts,
                  "Anomalies": all_anomalies}
    (output / "xbrl_statement_reconciliation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    pd.DataFrame(report.get("Facts", [])).to_csv(output / "xbrl_statement_facts.csv", index=False)
    pd.DataFrame(report.get("Checks", [])).to_csv(output / "xbrl_statement_reconciliation_checks.csv", index=False)
    pd.DataFrame(report.get("Contexts", [])).to_csv(output / "xbrl_statement_contexts.csv", index=False)
    pd.DataFrame(report.get("Anomalies", [])).to_csv(output / "xbrl_statement_anomalies.csv", index=False)
    summary = []
    for result in report.get("Results", []):
        check_rows = result.get("ReconciliationChecks", [])
        summary.append({"Symbol": result.get("Symbol", ""), "Status": result.get("Status", ""),
                        "IdentityStatus": result.get("IdentityStatus", ""),
                        "ContextCount": result.get("ContextCount", ""),
                        "FactCount": result.get("FactCount", ""),
                        "Q4OperatingCashFlowAvailability": result.get("QuarterlyOperatingCashFlowAvailability", ""),
                        "AnnualOperatingCashFlowContexts": ";".join(result.get("AnnualOperatingCashFlowContexts", [])),
                        "CFOArithmeticEvidence": result.get("CFOArithmeticEvidence", ""),
                        "ReconciliationChecksPass": sum(c.get("Status") == "PASS_WITHIN_XBRL_ROUNDING" for c in check_rows),
                        "ReconciliationChecksMismatch": sum(c.get("Status") == "MISMATCH" for c in check_rows),
                        "AnomalyCount": len(result.get("Anomalies", []))})
    pd.DataFrame(summary).to_csv(output / "xbrl_statement_reconciliation_summary.csv", index=False)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic-json", default="outputs/xbrl_sample_diagnostics/xbrl_sample_diagnostic.json")
    parser.add_argument("--output", default="outputs/xbrl_statement_reconciliation")
    args = parser.parse_args(argv)
    report = run_reconciliation(args.diagnostic_json, args.output)
    print(json.dumps({k: report.get(k) for k in ("Status", "SampleCount", "SuccessCount", "FailureCount")}))
    return 0  # diagnostic-only: scanner remains independent; inspect report status separately


if __name__ == "__main__":
    raise SystemExit(main())
