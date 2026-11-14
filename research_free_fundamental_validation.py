"""Research-only batched collection of free NSE Mainboard fundamentals.

Writes only data/research/*.csv. It never modifies production fundamental,
Bhavcopy, Delivery, scanner, or Master Specification files.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from free_fundamental_sources import fetch_free_fundamental_sources
from nse_shareholding import fetch_nse_shareholding_metrics

UNIVERSE_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
PRODUCTION_CACHE = Path("data/inputs/fundamental_metrics.csv")  # read-only
RESEARCH_DIR = Path("data/research")
CACHE_PATH = RESEARCH_DIR / "fundamental_free_source_cache.csv"
DIAGNOSTICS_PATH = RESEARCH_DIR / "fundamental_free_source_diagnostics.csv"
MANIFEST_PATH = RESEARCH_DIR / "fundamental_free_source_batch_manifest.json"
CORE_METRICS = {
    "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
    "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR", "FreeCashFlowINR",
    "GrossMarginPct", "OperatingMarginPct", "NetProfitMarginPct", "CurrentRatio",
    "QuickRatio", "AssetTurnover", "EPS", "BookValuePerShare",
    "PromoterHoldingPct", "FIIHoldingPct", "DIIHoldingPct", "PublicHoldingPct",
    "PledgePct",
}
PERIOD_RE = re.compile(r"^(?:20\d{2}-\d{2}-\d{2}|FY\s?20\d{2}|Q[1-4]\s?FY\s?20\d{2})$", re.I)


def load_universe() -> pd.DataFrame:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "text/csv,*/*",
        "Referer": "https://www.nseindia.com/",
    })
    response = session.get(UNIVERSE_URL, timeout=(10, 30))
    response.raise_for_status()
    frame = pd.read_csv(io.BytesIO(response.content))
    symbol_col = next((c for c in frame.columns if str(c).strip().upper() == "SYMBOL"), None)
    name_col = next((c for c in frame.columns if "NAME OF COMPANY" in str(c).strip().upper()), None)
    if not symbol_col:
        raise RuntimeError(f"NSE equity list missing SYMBOL column: {list(frame.columns)}")
    out = pd.DataFrame({
        "Symbol": frame[symbol_col].astype(str).str.strip().str.upper(),
        "CompanyName": frame[name_col].astype(str).str.strip() if name_col else "",
    })
    out = out[out.Symbol.ne("") & ~out.Symbol.isin({"NAN", "NONE"})]
    return out.drop_duplicates("Symbol").sort_values("Symbol").reset_index(drop=True)


def load_recent_attempts() -> dict[str, pd.Timestamp]:
    attempts = {}
    if PRODUCTION_CACHE.exists():
        frame = pd.read_csv(PRODUCTION_CACHE, dtype=str).fillna("")
        if "TckrSymb" in frame and "FreeSourcesAttemptedAtUTC" in frame:
            for _, row in frame.iterrows():
                stamp = pd.to_datetime(row.get("FreeSourcesAttemptedAtUTC"), errors="coerce", utc=True)
                if pd.notna(stamp):
                    attempts[str(row["TckrSymb"]).strip().upper()] = stamp
    if CACHE_PATH.exists():
        frame = pd.read_csv(CACHE_PATH, dtype=str).fillna("")
        if {"Symbol", "RetrievedAtUTC"}.issubset(frame.columns):
            for _, row in frame.iterrows():
                stamp = pd.to_datetime(row["RetrievedAtUTC"], errors="coerce", utc=True)
                sym = str(row["Symbol"]).strip().upper()
                if sym and pd.notna(stamp) and (sym not in attempts or stamp > attempts[sym]):
                    attempts[sym] = stamp
    return attempts


def main() -> None:
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    batch_size = max(1, min(100, int(os.getenv("FUNDAMENTAL_RESEARCH_BATCH_SIZE", "25"))))
    batch_offset = max(0, int(os.getenv("FUNDAMENTAL_RESEARCH_BATCH_OFFSET", "0")))
    cooldown_days = max(1, int(os.getenv("FUNDAMENTAL_RESEARCH_RETRY_DAYS", "7")))

    universe = load_universe()
    attempts = load_recent_attempts()
    eligible = []
    for row in universe.to_dict("records"):
        sym = row["Symbol"]
        last = attempts.get(sym)
        if last is not None and now - last < pd.Timedelta(days=cooldown_days):
            continue
        eligible.append(row)
    batch = eligible[batch_offset:batch_offset + batch_size]

    old_cache = pd.read_csv(CACHE_PATH, dtype=str).fillna("") if CACHE_PATH.exists() else pd.DataFrame()
    old_diag = pd.read_csv(DIAGNOSTICS_PATH, dtype=str).fillna("") if DIAGNOSTICS_PATH.exists() else pd.DataFrame()
    cache_rows, diagnostic_rows = [], []
    rejected_period_count = 0
    shareholding_cache = RESEARCH_DIR / "shareholding_xbrl_cache"
    shareholding_cache.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    def isolated_shareholding(symbol: str):
        return fetch_nse_shareholding_metrics(symbol, cache_dir=shareholding_cache)

    for index, item in enumerate(batch):
        symbol, company_name = item["Symbol"], item["CompanyName"]
        symbol_started = time.monotonic()
        result = fetch_free_fundamental_sources(
            symbol,
            company_name=company_name or None,
            missing_metrics=CORE_METRICS,
            pause_seconds=0.5,
            source_factories={"nse_shareholding": isolated_shareholding},
        )
        providers = result.get("providers", {})
        metrics = result.get("metrics", {})
        for provider, detail in providers.items():
            provider_metrics = {
                metric: value for metric, value in metrics.items()
                if result.get("metric_sources", {}).get(metric) == provider
            }
            provider_periods = result.get("metric_periods", {})
            diagnostic_rows.append({
                "Symbol": symbol,
                "CompanyName": company_name,
                "Provider": provider,
                "Status": detail.get("status", "UNKNOWN"),
                "Reason": str(detail.get("reason", ""))[:500],
                "MetricsObserved": ";".join(sorted(provider_metrics)),
                "MetricsPeriodsJSON": json.dumps(
                    {m: provider_periods.get(m, "") for m in provider_metrics}, sort_keys=True
                ),
                "SourceURL": detail.get("source_url", ""),
                "IdentityStatus": detail.get("identity_status", ""),
                "HTTPDiagnosticsJSON": json.dumps(detail.get("last_http", {}), sort_keys=True),
                "ElapsedSeconds": round(time.monotonic() - symbol_started, 3),
            })
        for metric, value in metrics.items():
            if metric not in CORE_METRICS:
                continue
            provider = result.get("metric_sources", {}).get(metric, "")
            period = str(result.get("metric_periods", {}).get(metric, "")).strip()
            period_ok = bool(PERIOD_RE.fullmatch(period))
            # Values with missing/ambiguous periods (e.g. Tickertape period "0")
            # remain in diagnostics only and are not promoted to the research cache.
            if not period_ok:
                rejected_period_count += 1
                continue
            detail = providers.get(provider, {})
            cache_rows.append({
                "Symbol": symbol,
                "CompanyName": company_name,
                "Metric": metric,
                "Value": value,
                "Provider": provider,
                "SourceURL": result.get("metric_urls", {}).get(metric, detail.get("source_url", "")),
                "FinancialPeriod": period,
                "RetrievedAtUTC": now.isoformat(),
                "VerificationStatus": (
                    "OFFICIAL_NSE_XBRL_SOURCE_PERIOD_CAPTURED"
                    if provider == "NSE Official Shareholding XBRL"
                    else "UNVERIFIED_PUBLIC_PROVIDER_PERIOD_CAPTURED"
                ),
                "ProviderIdentityStatus": detail.get("identity_status", ""),
            })
        print(json.dumps({
            "symbol": symbol,
            "providers": {k: v.get("status") for k, v in providers.items()},
            "metrics_observed": sorted(metrics),
            "metrics_period_accepted": sum(
                1 for m in metrics
                if m in CORE_METRICS and PERIOD_RE.fullmatch(
                    str(result.get("metric_periods", {}).get(m, "")).strip()
                )
            ),
        }, sort_keys=True))
        if index + 1 < len(batch):
            time.sleep(1.0)

    new_cache = pd.DataFrame(cache_rows)
    new_diag = pd.DataFrame(diagnostic_rows)
    if not old_cache.empty or not new_cache.empty:
        combined = pd.concat([old_cache, new_cache], ignore_index=True).fillna("")
        keys = ["Symbol", "Metric", "Provider", "FinancialPeriod"]
        combined = combined.drop_duplicates(keys, keep="last").sort_values(keys)
        combined.to_csv(CACHE_PATH, index=False)
    if not old_diag.empty or not new_diag.empty:
        diagnostics = pd.concat([old_diag, new_diag], ignore_index=True).fillna("")
        diagnostics.to_csv(DIAGNOSTICS_PATH, index=False)

    manifest = {
        "generated_at_utc": now.isoformat(),
        "universe_source": UNIVERSE_URL,
        "mainboard_universe_count": int(len(universe)),
        "eligible_not_recently_attempted": len(eligible),
        "batch_offset": batch_offset,
        "batch_size": batch_size,
        "batch_symbols": [x["Symbol"] for x in batch],
        "symbols_processed": len(batch),
        "observations_returned": len(cache_rows),
        "observations_added_to_research_cache": len(new_cache),
        "observations_rejected_for_invalid_or_missing_period": rejected_period_count,
        "research_cache_path": str(CACHE_PATH),
        "diagnostics_path": str(DIAGNOSTICS_PATH),
        "production_cache_modified": False,
        "production_scanner_modified": False,
        "bhavcopy_or_delivery_cache_modified": False,
        "master_spec_modified": False,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "next_batch_offset": batch_offset + len(batch),
        "note": "Research cache only. Non-NSE provider metrics remain unverified and must be reconciled before scanner scoring/backtests. Invalid/missing periods are excluded.",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print("FUNDAMENTAL_RESEARCH_BATCH=" + json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
