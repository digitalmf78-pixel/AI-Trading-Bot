"""Diagnostic-only inspection of official NSE XBRL filing XML samples.

This module does not calculate financial metrics or alter the scanner/cache.
It downloads a small, deterministic sample from OfficialFilingURL values already
recorded by the fundamental collection pipeline and emits machine-readable
context/fact evidence for manual schema and period-basis review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from nse_xbrl_fetch import ALLOWED_HOSTS, fetch_official_xbrl_xml

CASHFLOW_HINTS = (
    "cashflow", "cashflows", "operatingactivities", "investingactivities",
    "financingactivities", "cashandcashequivalents", "capitalexpenditure",
    "paymentstoacquireproperty", "netcash",
)


def _local(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _safe_text(node, path: str) -> str:
    child = node.find(path)
    return "" if child is None or child.text is None else child.text.strip()


def _context_map(root) -> dict[str, dict]:
    contexts = {}
    for node in root.iter():
        if _local(node.tag).lower() != "context":
            continue
        context_id = node.attrib.get("id", "")
        period = next((c for c in node if _local(c.tag).lower() == "period"), None)
        dates = {}
        if period is not None:
            for child in period:
                dates[_local(child.tag)] = (child.text or "").strip()
        entity = next((c for c in node if _local(c.tag).lower() == "entity"), None)
        identifier = ""
        if entity is not None:
            for child in entity:
                if _local(child.tag).lower() == "identifier":
                    identifier = (child.text or "").strip()
                    break
        contexts[context_id] = {
            "entity_identifier": identifier,
            "period": dates,
            "has_dimensions": any(
                "explicitMember" in _local(desc.tag) or "typedMember" in _local(desc.tag)
                for desc in node.iter()
            ),
        }
    return contexts


def inspect_xbrl_xml(xml_path: str | Path, *, max_cashflow_facts: int = 30) -> dict:
    root = ET.parse(xml_path).getroot()
    contexts = _context_map(root)
    units = {}
    facts = []
    cashflow_facts = []
    excluded = {"xbrl", "context", "unit", "schemaref", "footnotelink"}
    for node in root.iter():
        name = _local(node.tag)
        low = name.lower()
        if low == "unit":
            unit_id = node.attrib.get("id", "")
            measures = [(m.text or "").strip() for m in node.iter() if _local(m.tag).lower() == "measure"]
            units[unit_id] = measures
            continue
        if low in excluded or len(node) or "contextRef" not in node.attrib:
            continue
        value = (node.text or "").strip()
        if not value:
            continue
        row = {
            "tag": name,
            "context_ref": node.attrib.get("contextRef", ""),
            "unit_ref": node.attrib.get("unitRef", ""),
            "decimals": node.attrib.get("decimals", ""),
            "value": value[:160],
            "context": contexts.get(node.attrib.get("contextRef", ""), {}),
        }
        facts.append(row)
        compact = re.sub(r"[^a-z0-9]", "", low)
        if any(hint in compact for hint in CASHFLOW_HINTS):
            cashflow_facts.append(row)
    return {
        "root_tag": _local(root.tag),
        "namespace": root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else "",
        "context_count": len(contexts),
        "unit_count": len(units),
        "fact_count": len(facts),
        "cashflow_candidate_fact_count": len(cashflow_facts),
        "contexts": contexts,
        "units": units,
        "cashflow_facts": cashflow_facts[:max_cashflow_facts],
    }


def select_samples(metrics_path: str | Path, limit: int = 5) -> list[dict]:
    path = Path(metrics_path)
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    required = {"OfficialFilingURL"}
    if not required.issubset(frame.columns):
        return []
    if "TckrSymb" not in frame.columns:
        frame["TckrSymb"] = ""
    for col in ("PublicationDate", "FinancialPeriodEnd"):
        if col not in frame.columns:
            frame[col] = ""
    frame["OfficialFilingURL"] = frame["OfficialFilingURL"].fillna("").astype(str).str.strip()
    frame = frame[frame["OfficialFilingURL"] != ""].drop_duplicates("OfficialFilingURL")
    frame = frame[frame["OfficialFilingURL"].map(_is_allowed_xml_url)]
    frame = frame.sort_values(["PublicationDate", "TckrSymb"], ascending=[False, True], kind="stable")
    return frame.head(max(0, int(limit)))[
        ["TckrSymb", "FinancialPeriodEnd", "PublicationDate", "OfficialFilingURL"]
    ].to_dict("records")


def _is_allowed_xml_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower() in ALLOWED_HOSTS
        and parsed.path.lower().endswith(".xml")
    )


def run_diagnostic(metrics_path: str | Path, output_dir: str | Path,
                   cache_dir: str | Path, limit: int = 5) -> dict:
    output = Path(output_dir)
    cache = Path(cache_dir)
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    samples = select_samples(metrics_path, limit)
    results = []
    for item in samples:
        url = item["OfficialFilingURL"]
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        target = cache / f"{digest}.xml"
        row = {**item, "download_status": "NOT_ATTEMPTED", "xml_path": str(target)}
        try:
            fetch_official_xbrl_xml(url, target)
            evidence = inspect_xbrl_xml(target)
            row.update({"download_status": "SUCCESS", **evidence})
        except Exception as exc:  # retain per-sample failure and continue
            row.update({
                "download_status": "FAILED",
                "failure_reason": f"{type(exc).__name__}: {exc}"[:500],
            })
        results.append(row)
    report = {
        "status": "NO_ELIGIBLE_FILINGS" if not samples else (
            "SUCCESS" if any(r["download_status"] == "SUCCESS" for r in results) else "ALL_DOWNLOADS_FAILED"
        ),
        "metrics_path": str(metrics_path),
        "sample_limit": int(limit),
        "sample_count": len(results),
        "success_count": sum(r["download_status"] == "SUCCESS" for r in results),
        "failure_count": sum(r["download_status"] == "FAILED" for r in results),
        "results": results,
    }
    (output / "xbrl_sample_diagnostic.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    flat = []
    for row in results:
        flat.append({k: row.get(k, "") for k in (
            "TckrSymb", "FinancialPeriodEnd", "PublicationDate", "OfficialFilingURL",
            "download_status", "failure_reason", "root_tag", "namespace",
            "context_count", "unit_count", "fact_count", "cashflow_candidate_fact_count",
            "xml_path",
        )})
    pd.DataFrame(flat).to_csv(output / "xbrl_sample_diagnostic_summary.csv", index=False)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default="data/inputs/fundamental_metrics.csv")
    parser.add_argument("--output", default="outputs/xbrl_sample_diagnostics")
    parser.add_argument("--cache", default="data/cache/xbrl_samples")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    report = run_diagnostic(args.metrics, args.output, args.cache, args.limit)
    print(json.dumps({k: report[k] for k in (
        "status", "sample_count", "success_count", "failure_count"
    )}, ensure_ascii=False))
    # A diagnostic failure is represented in the report; it must not be confused
    # with a scanner/test pass or prevent the main scanner artifact upload.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
