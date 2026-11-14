"""Research-only live validation of public NSE fundamental data sources.

Uses a deterministic sample of currently missing Mainboard symbols. No production
cache or scanner output is read or modified. NSE shareholding cache is redirected
to the research output directory.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from free_fundamental_sources import fetch_free_fundamental_sources
from nse_shareholding import fetch_nse_shareholding_metrics

SAMPLES = [
    "20MICRONS", "ASKAUTOLTD", "CHEMCON", "EPIGRAL",
    "HEROMOTOCO", "JYOTHYLAB", "MARKSANS", "ORIRAIL",
    "RESPONIND", "SIMPLXREA", "TMB", "ZYDUSWELL",
]
OUT_DIR = Path("outputs/research_free_fundamental_validation")
SHAREHOLDING_CACHE = OUT_DIR / "shareholding_cache"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SHAREHOLDING_CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    started = time.monotonic()

    def isolated_nse_shareholding(symbol: str):
        return fetch_nse_shareholding_metrics(
            symbol, cache_dir=SHAREHOLDING_CACHE,
        )

    for index, symbol in enumerate(SAMPLES):
        symbol_started = time.monotonic()
        result = fetch_free_fundamental_sources(
            symbol,
            company_name=None,
            missing_metrics=None,
            pause_seconds=0.5,
            source_factories={"nse_shareholding": isolated_nse_shareholding},
        )
        providers = result.get("providers", {})
        metrics = result.get("metrics", {})
        for provider, diagnostic in providers.items():
            rows.append({
                "Symbol": symbol,
                "Provider": provider,
                "Status": diagnostic.get("status", "UNKNOWN"),
                "Reason": str(diagnostic.get("reason", ""))[:500],
                "MetricsFoundJSON": json.dumps(
                    {k: v for k, v in metrics.items()
                     if result.get("metric_sources", {}).get(k) == provider},
                    sort_keys=True,
                ),
                "MetricPeriodsJSON": json.dumps(
                    {k: v for k, v in result.get("metric_periods", {}).items()
                     if result.get("metric_sources", {}).get(k) == provider},
                    sort_keys=True,
                ),
                "SourceURL": diagnostic.get("source_url", ""),
                "HTTPDiagnosticsJSON": json.dumps(
                    diagnostic.get("last_http", {}), sort_keys=True,
                ),
                "EndpointRowsJSON": json.dumps(
                    diagnostic.get("rows", {}), sort_keys=True,
                ),
                "IdentityStatus": diagnostic.get("identity_status", ""),
                "ElapsedSeconds": round(time.monotonic() - symbol_started, 3),
            })
        print(json.dumps({
            "symbol": symbol,
            "providers": providers,
            "metrics": metrics,
            "metric_sources": result.get("metric_sources", {}),
            "metric_periods": result.get("metric_periods", {}),
        }, sort_keys=True, default=str))
        if index + 1 < len(SAMPLES):
            time.sleep(0.5)

    frame = pd.DataFrame(rows)
    frame.to_csv(OUT_DIR / "provider_results.csv", index=False)
    status_counts = Counter(row["Status"] for row in rows)
    provider_counts = {}
    for provider in sorted({row["Provider"] for row in rows}):
        subset = [row for row in rows if row["Provider"] == provider]
        provider_counts[provider] = {
            "symbols_attempted": len(subset),
            "data_found": sum(row["Status"] == "DATA_FOUND" for row in subset),
            "identity_unverified": sum(row["Status"] == "IDENTITY_UNVERIFIED" for row in subset),
            "provider_errors": sum(
                row["Status"] in {"PROVIDER_ERROR", "HTTP_ERROR", "RATE_LIMITED"}
                for row in subset
            ),
            "statuses": dict(Counter(row["Status"] for row in subset)),
        }
    summary = {
        "purpose": "Research-only live source validation; not a production backfill",
        "sample_method": "12 evenly spaced symbols from the dated missing Mainboard universe",
        "symbols": SAMPLES,
        "symbols_tested": len(SAMPLES),
        "provider_rows": len(rows),
        "provider_status_counts": dict(status_counts),
        "providers": provider_counts,
        "total_elapsed_seconds": round(time.monotonic() - started, 3),
        "production_cache_write": False,
        "production_scanner_write": False,
        "nse_shareholding_cache": str(SHAREHOLDING_CACHE),
        "warning": "Values are diagnostic observations only; period, identity, units and filing evidence require review before any use.",
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print("RESEARCH_FREE_FUNDAMENTAL_VALIDATION=" + json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
