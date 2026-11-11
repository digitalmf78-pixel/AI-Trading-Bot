"""Live smoke test for no-key Indian fundamentals sources.

This is intentionally separate from the production scanner: it checks a few
known NSE listings, writes only mapped metric values and provider diagnostics,
and never mutates the Fundamental Cache or trading outputs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from free_fundamental_sources import fetch_free_fundamental_sources

SAMPLES = [
    ("RELIANCE", "Reliance Industries Limited"),
    ("TCS", "Tata Consultancy Services Limited"),
    ("INFY", "Infosys Limited"),
]


def main():
    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for symbol, company_name in SAMPLES:
        result = fetch_free_fundamental_sources(
            symbol,
            company_name=company_name,
            missing_metrics=None,
            pause_seconds=0.25,
        )
        print(json.dumps({
            "symbol": symbol,
            "providers": result.get("providers", {}),
            "metrics": result.get("metrics", {}),
            "metric_sources": result.get("metric_sources", {}),
            "metric_alternates": result.get("metric_alternates", {}),
        }, sort_keys=True, default=str))
        for source, detail in result.get("providers", {}).items():
            rows.append({
                "TckrSymb": symbol,
                "CompanyName": company_name,
                "Provider": source,
                "ProviderStatus": detail.get("status", ""),
                "RowsByEndpointJSON": json.dumps(detail.get("rows", {}), sort_keys=True),
                "TableSchemaJSON": json.dumps(detail.get("table_schema", {}), sort_keys=True),
                "ProviderReason": detail.get("reason", ""),
                "MetricsFoundJSON": json.dumps(result.get("metrics", {}), sort_keys=True),
                "MetricSourcesJSON": json.dumps(result.get("metric_sources", {}), sort_keys=True),
                "MetricAlternatesJSON": json.dumps(result.get("metric_alternates", {}), sort_keys=True),
            })
    pd.DataFrame(rows).to_csv(out_dir / "free_fundamental_live_smoke.csv", index=False)
    summary = {
        "symbols_tested": len(SAMPLES),
        "provider_rows": len(rows),
        "data_found": sum(row["ProviderStatus"] == "DATA_FOUND" for row in rows),
        "identity_unverified": sum(row["ProviderStatus"] == "IDENTITY_UNVERIFIED" for row in rows),
        "empty_or_errors": sum(row["ProviderStatus"] not in {"DATA_FOUND", "IDENTITY_UNVERIFIED"} for row in rows),
    }
    (out_dir / "free_fundamental_live_smoke_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print("FREE_FUNDAMENTAL_LIVE_SMOKE_SUMMARY=" + json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
