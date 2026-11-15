"""Research-only Yahoo Finance/yfinance coverage audit for NSE Mainboard.

Calls the existing V8 Yahoo adapter in read-only mode. It does not write or
change production fundamental_metrics.csv, scanner inputs, or main-branch code.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fundamental_data_provider import _fetch_one, METRIC_COLUMNS
from research_free_fundamental_validation import load_universe

OUT = Path("data/research/yfinance_coverage")
PRIMARY = [
    "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
    "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
]
ALL_METRICS = PRIMARY + ["FreeCashFlowINR"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    batch_size = max(1, min(100, int(__import__("os").getenv("YAHOO_COVERAGE_BATCH_SIZE", "25"))))
    universe = load_universe()
    # Evenly spaced deterministic sample across the full sorted Mainboard list.
    if len(universe) <= batch_size:
        sample = universe.copy()
    else:
        positions = sorted(set(round(i * (len(universe) - 1) / (batch_size - 1))
                                for i in range(batch_size))) if batch_size > 1 else [len(universe) // 2]
        sample = universe.iloc[positions].reset_index(drop=True)

    rows = []
    started = time.monotonic()
    for i, item in enumerate(sample.to_dict("records"), 1):
        symbol = str(item["Symbol"]).strip().upper()
        record, diagnostic = _fetch_one(symbol, company_name=item.get("CompanyName"))
        row = {
            "Symbol": symbol,
            "CompanyName": item.get("CompanyName", ""),
            "ProviderStatus": diagnostic.get("ProviderStatus", ""),
            "ProviderReason": diagnostic.get("ProviderReason", ""),
            "FinancialPeriodEnd": record.get("FinancialPeriodEnd", ""),
            "MetricCalculationBasis": record.get("MetricCalculationBasis", ""),
            "QuarterlyAlignmentReason": record.get("QuarterlyAlignmentReason", ""),
            "Source": record.get("Source", ""),
            "SourceURL": record.get("SourceURL", ""),
        }
        for metric in ALL_METRICS:
            value = record.get(metric)
            row[metric] = value if pd.notna(value) else ""
            row[metric + "Available"] = bool(pd.notna(value))
        rows.append(row)
        print(json.dumps({
            "progress": f"{i}/{len(sample)}",
            "symbol": symbol,
            "status": row["ProviderStatus"],
            "available_primary_metrics": [m for m in PRIMARY if row[m + "Available"]],
            "financial_period_end": str(row["FinancialPeriodEnd"]),
            "basis": str(row["MetricCalculationBasis"]),
        }, default=str))
        if i < len(sample):
            time.sleep(0.8)

    frame = pd.DataFrame(rows)
    csv_path = OUT / "yfinance_mainboard_sample.csv"
    frame.to_csv(csv_path, index=False)
    per_metric = {
        metric: int(frame[metric + "Available"].sum()) if not frame.empty else 0
        for metric in PRIMARY
    }
    complete = int(frame[[m + "Available" for m in PRIMARY]].all(axis=1).sum()) if not frame.empty else 0
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "universe_source": "NSE EQUITY_L.csv Mainboard equity list",
        "mainboard_universe_count": int(len(universe)),
        "sample_method": "deterministic evenly-spaced sample across sorted Mainboard symbols",
        "sample_size": int(len(frame)),
        "symbols_with_any_primary_metric": int(frame[[m + "Available" for m in PRIMARY]].any(axis=1).sum()) if not frame.empty else 0,
        "symbols_with_all_7_primary_metrics": complete,
        "primary_metric_available_counts": per_metric,
        "provider_status_counts": frame["ProviderStatus"].value_counts(dropna=False).to_dict() if not frame.empty else {},
        "calculation_basis_counts": frame["MetricCalculationBasis"].value_counts(dropna=False).to_dict() if not frame.empty else {},
        "period_end_available": int(frame["FinancialPeriodEnd"].fillna("").astype(str).str.strip().ne("").sum()) if not frame.empty else 0,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "production_cache_modified": False,
        "production_scanner_modified": False,
        "main_branch_modified": False,
        "note": "Yahoo/yfinance provider-only coverage research. Values are not official filing verification and are not eligible for production scoring from this artifact.",
    }
    (OUT / "yfinance_mainboard_sample_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print("YFINANCE_COVERAGE_SUMMARY=" + json.dumps(summary, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
