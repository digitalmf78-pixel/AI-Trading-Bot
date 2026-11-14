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
PERIOD_RE = re.compile(r"^(?:20\d{2}-\d{2}-\d{2}|FY\s?20\d{2}|Q[1-4]\s?FY\s?20\d{2}|[A-Z][a-z]{2}\s20\d{2})$", re.I)
GROWTH_PERIOD_RE = re.compile(r"^FY\s?20\d{2}\s*->\s*FY\s?20\d{2}$", re.I)
CACHE_COLUMNS = ["Symbol", "CompanyName", "Metric", "Value", "Provider", "SourceURL", "FinancialPeriod", "RetrievedAtUTC", "VerificationStatus", "ProviderIdentityStatus"]
DIAGNOSTIC_COLUMNS = ["Symbol", "CompanyName", "Provider", "Status", "Reason", "MetricsObserved", "MetricsPeriodsJSON", "MetricsValuesJSON", "SourceURL", "IdentityStatus", "HTTPDiagnosticsJSON", "AttemptedAtUTC", "ElapsedSeconds"]
QUARANTINE_COLUMNS = ["Symbol", "CompanyName", "Metric", "Value", "Provider", "SourceURL", "ObservedPeriod", "RetrievedAtUTC", "RejectionReason"]


def valid_period(metric: str, period: str) -> bool:
    period = str(period or "").strip()
    if PERIOD_RE.fullmatch(period):
        return True
    return metric in {"RevenueGrowthPct", "ProfitGrowthPct"} and bool(GROWTH_PERIOD_RE.fullmatch(period))


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
    if DIAGNOSTICS_PATH.exists():
        frame = pd.read_csv(DIAGNOSTICS_PATH, dtype=str).fillna("")
        if {"Symbol", "AttemptedAtUTC"}.issubset(frame.columns):
            for _, row in frame.iterrows():
                stamp = pd.to_datetime(row.get("AttemptedAtUTC"), errors="coerce", utc=True)
                sym = str(row.get("Symbol", "")).strip().upper()
                if sym and pd.notna(stamp) and (sym not in attempts or stamp > attempts[sym]):
                    attempts[sym] = stamp
    return attempts



def load_existing_metric_map(research_cache=None):
    """Read existing metric coverage from production (read-only) and research cache."""
    existing = {}
    if PRODUCTION_CACHE.exists():
        try:
            production = pd.read_csv(PRODUCTION_CACHE, dtype=str).fillna("")
        except Exception:
            production = pd.DataFrame()
        if not production.empty and "TckrSymb" in production.columns:
            normalized = {re.sub(r"[^a-z0-9]", "", str(c).lower()): c for c in production.columns}
            aliases = {
                "RevenueGrowthPct": ("revenuegrowthpct", "revenuegrowth", "salesgrowthpct"),
                "ProfitGrowthPct": ("profitgrowthpct", "profitgrowth", "netprofitgrowthpct"),
                "ROEPercent": ("roepercent", "roe", "returnonequity"),
                "ROCEPercent": ("rocepercent", "roce", "returnoncapitalemployed"),
                "DebtToEquity": ("debttoequity", "debtequity"),
                "InterestCoverage": ("interestcoverage", "interestcoverageratio"),
                "OperatingCashFlowINR": ("operatingcashflowinr", "operatingcashflow"),
                "FreeCashFlowINR": ("freecashflowinr", "freecashflow"),
                "GrossMarginPct": ("grossmarginpct", "grossmargin"),
                "OperatingMarginPct": ("operatingmarginpct", "operatingmargin"),
                "NetProfitMarginPct": ("netprofitmarginpct", "netprofitmargin"),
                "CurrentRatio": ("currentratio",), "QuickRatio": ("quickratio",),
                "AssetTurnover": ("assetturnover", "assetturnoverratio"),
                "EPS": ("eps", "earningspershare"),
                "BookValuePerShare": ("bookvaluepershare", "bookvalue"),
                "PromoterHoldingPct": ("promoterholdingpct", "promoterholding"),
                "FIIHoldingPct": ("fiiholdingpct", "fiiholding"),
                "DIIHoldingPct": ("diiholdingpct", "diiholding"),
                "PublicHoldingPct": ("publicholdingpct", "publicholding"),
                "PledgePct": ("pledgepct", "promoterpledgepct"),
            }
            for metric, names in aliases.items():
                col = next((normalized[n] for n in names if n in normalized), None)
                if col is None:
                    continue
                for _, row in production.iterrows():
                    value = str(row.get(col, "")).strip()
                    if value and value.lower() not in {"nan", "none", "null", "na", "n/a"}:
                        symbol = str(row.get("TckrSymb", "")).strip().upper()
                        if symbol:
                            existing.setdefault(symbol, set()).add(metric)
    cache = research_cache
    if cache is None and CACHE_PATH.exists():
        try:
            cache = pd.read_csv(CACHE_PATH, dtype=str).fillna("")
        except Exception:
            cache = pd.DataFrame()
    if cache is not None and not cache.empty and {"Symbol", "Metric", "Value", "FinancialPeriod"}.issubset(cache.columns):
        for row in cache.to_dict("records"):
            symbol = str(row.get("Symbol", "")).strip().upper()
            metric = str(row.get("Metric", "")).strip()
            value = str(row.get("Value", "")).strip()
            period = str(row.get("FinancialPeriod", "")).strip()
            try:
                numeric = float(value.replace(",", ""))
            except (TypeError, ValueError):
                continue
            if symbol and metric in CORE_METRICS and pd.notna(numeric) and valid_period(metric, period):
                existing.setdefault(symbol, set()).add(metric)
    return existing


def symbols_missing_any_accepted_metric(symbols, existing_metrics):
    """Return symbols with no valid metric in either production or research cache."""
    return [str(symbol).strip().upper() for symbol in symbols
            if not existing_metrics.get(str(symbol).strip().upper(), set())]


def main() -> None:
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    batch_size = max(1, min(100, int(os.getenv("FUNDAMENTAL_RESEARCH_BATCH_SIZE", "25"))))
    batch_offset = max(0, int(os.getenv("FUNDAMENTAL_RESEARCH_BATCH_OFFSET", "0")))
    cooldown_days = max(1, int(os.getenv("FUNDAMENTAL_RESEARCH_RETRY_DAYS", "7")))

    universe = load_universe()
    attempts = load_recent_attempts()
    old_cache = pd.read_csv(CACHE_PATH, dtype=str).fillna("") if CACHE_PATH.exists() else pd.DataFrame()
    existing_metrics = load_existing_metric_map(old_cache)
    missing_by_symbol = {
        row["Symbol"]: CORE_METRICS - existing_metrics.get(row["Symbol"], set())
        for row in universe.to_dict("records")
    }
    eligible = []
    for row in universe.to_dict("records"):
        sym = row["Symbol"]
        # Query every symbol that is still missing one or more core metrics.
        # A single accepted metric must not cause the rest of its fundamentals
        # to be skipped. Recent attempts are cooled down to avoid hammering
        # free sources while still allowing a later gap-filling pass.
        if not missing_by_symbol[sym]:
            continue
        last = attempts.get(sym)
        if last is not None and now - last < pd.Timedelta(days=cooldown_days):
            continue
        eligible.append(row)
    batch = eligible[batch_offset:batch_offset + batch_size]
    old_diag = pd.read_csv(DIAGNOSTICS_PATH, dtype=str).fillna("") if DIAGNOSTICS_PATH.exists() else pd.DataFrame(columns=DIAGNOSTIC_COLUMNS)
    quarantine_path = RESEARCH_DIR / "fundamental_free_source_quarantine.csv"
    old_quarantine = pd.read_csv(quarantine_path, dtype=str).fillna("") if quarantine_path.exists() else pd.DataFrame(columns=QUARANTINE_COLUMNS)
    cache_rows, diagnostic_rows, quarantine_rows = [], [], []
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
            missing_metrics=missing_by_symbol.get(symbol, set()),
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
                "MetricsValuesJSON": json.dumps(provider_metrics, sort_keys=True),
                "SourceURL": detail.get("source_url", ""),
                "IdentityStatus": detail.get("identity_status", ""),
                "HTTPDiagnosticsJSON": json.dumps(detail.get("last_http", {}), sort_keys=True),
                "AttemptedAtUTC": now.isoformat(),
                "ElapsedSeconds": round(time.monotonic() - symbol_started, 3),
            })
        for metric, value in metrics.items():
            if metric not in CORE_METRICS:
                continue
            provider = result.get("metric_sources", {}).get(metric, "")
            period = str(result.get("metric_periods", {}).get(metric, "")).strip()
            period_ok = valid_period(metric, period)
            # Values with missing/ambiguous periods (e.g. Tickertape period "0")
            # remain in diagnostics only and are not promoted to the research cache.
            if not period_ok:
                rejected_period_count += 1
                detail = providers.get(provider, {})
                quarantine_rows.append({
                    "Symbol": symbol, "CompanyName": company_name, "Metric": metric,
                    "Value": value, "Provider": provider,
                    "SourceURL": result.get("metric_urls", {}).get(metric, detail.get("source_url", "")),
                    "ObservedPeriod": period, "RetrievedAtUTC": now.isoformat(),
                    "RejectionReason": "MISSING_OR_UNRECOGNIZED_FINANCIAL_PERIOD",
                })
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
                if m in CORE_METRICS and valid_period(
                    m, str(result.get("metric_periods", {}).get(m, "")).strip()
                )
            ),
        }, sort_keys=True))
        if index + 1 < len(batch):
            time.sleep(1.0)

    new_cache = pd.DataFrame(cache_rows)
    new_diag = pd.DataFrame(diagnostic_rows)
    combined = pd.concat([old_cache, pd.DataFrame(cache_rows, columns=CACHE_COLUMNS)], ignore_index=True).fillna("")
    if not combined.empty:
        keys = ["Symbol", "Metric", "Provider", "FinancialPeriod"]
        combined = combined.drop_duplicates(keys, keep="last").sort_values(keys)
    combined.reindex(columns=CACHE_COLUMNS).to_csv(CACHE_PATH, index=False)

    diagnostics = pd.concat([old_diag, pd.DataFrame(diagnostic_rows, columns=DIAGNOSTIC_COLUMNS)], ignore_index=True).fillna("")
    diagnostics.reindex(columns=DIAGNOSTIC_COLUMNS).to_csv(DIAGNOSTICS_PATH, index=False)

    quarantine = pd.concat([old_quarantine, pd.DataFrame(quarantine_rows, columns=QUARANTINE_COLUMNS)], ignore_index=True).fillna("")
    if not quarantine.empty:
        quarantine = quarantine.drop_duplicates(
            ["Symbol", "Metric", "Provider", "ObservedPeriod", "RetrievedAtUTC"], keep="last"
        )
    quarantine.reindex(columns=QUARANTINE_COLUMNS).to_csv(quarantine_path, index=False)

    represented_before = {sym for sym, metrics in existing_metrics.items() if metrics}
    represented_after = represented_before | {
        str(row.get("Symbol", "")).strip().upper() for row in cache_rows
        if str(row.get("Symbol", "")).strip()
    }
    metrics_after = {sym: set(values) for sym, values in existing_metrics.items()}
    for row in cache_rows:
        metrics_after.setdefault(str(row.get("Symbol", "")).strip().upper(), set()).add(
            str(row.get("Metric", "")).strip()
        )
    symbols_with_all_core_metrics = sum(
        1 for symbol in universe["Symbol"]
        if CORE_METRICS.issubset(metrics_after.get(str(symbol).upper(), set()))
    )
    attempted_symbols_after = set()
    if not old_diag.empty and "Symbol" in old_diag.columns:
        attempted_symbols_after.update(old_diag["Symbol"].astype(str).str.upper())
    attempted_symbols_after.update(str(row.get("Symbol", "")).strip().upper() for row in diagnostic_rows)
    attempted_symbols_after.intersection_update(set(universe["Symbol"]))
    manifest = {
        "generated_at_utc": now.isoformat(),
        "universe_source": UNIVERSE_URL,
        "mainboard_universe_count": int(len(universe)),
        "eligible_not_recently_attempted": len(eligible),
        "symbols_with_missing_metrics": sum(bool(v) for v in missing_by_symbol.values()),
        "symbols_with_any_accepted_metric_before": len(represented_before),
        "symbols_with_any_accepted_metric_after": len(represented_after),
        "symbols_without_any_accepted_metric_after": max(0, len(universe) - len(represented_after)),
        "missing_metric_observations_before_batch": sum(len(v) for v in missing_by_symbol.values()),
        "batch_offset": batch_offset,
        "batch_size": batch_size,
        "batch_symbols": [x["Symbol"] for x in batch],
        "symbols_processed": len(batch),
        "observations_returned": len(cache_rows),
        "observations_added_to_research_cache": len(new_cache),
        "observations_rejected_for_invalid_or_missing_period": rejected_period_count,
        "research_cache_path": str(CACHE_PATH),
        "diagnostics_path": str(DIAGNOSTICS_PATH),
        "quarantine_path": str(quarantine_path),
        "quarantined_observations": len(quarantine_rows),
        "production_cache_modified": False,
        "production_scanner_modified": False,
        "bhavcopy_or_delivery_cache_modified": False,
        "master_spec_modified": False,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "next_batch_offset": batch_offset + len(batch),
        "symbols_attempted_at_least_once": len(attempted_symbols_after),
        "symbols_with_all_core_metrics": int(symbols_with_all_core_metrics),
        "symbols_with_any_missing_core_metrics_after": int(len(universe) - symbols_with_all_core_metrics),
        "collection_complete": len(attempted_symbols_after) >= len(universe),
        "collection_completion_criterion": "every NSE Mainboard symbol has been queried at least once for its missing core fundamentals; per-metric gaps remain visible and must be audited before scanner use",
        "symbols_fully_covered": int(symbols_with_all_core_metrics),
        "note": "Research cache only. Non-NSE provider metrics remain unverified and must be reconciled before scanner scoring/backtests. Invalid/missing periods are excluded.",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print("FUNDAMENTAL_RESEARCH_BATCH=" + json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
