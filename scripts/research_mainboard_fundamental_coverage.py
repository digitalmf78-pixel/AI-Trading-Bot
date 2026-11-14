"""Research-only dated NSE Main Board universe and fundamental-cache coverage.

Downloads only the two official NSE classification CSVs. It writes outputs under
outputs/research_mainboard_coverage and never changes production caches.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

MAIN_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
SME_URL = "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv"
CACHE = Path("data/inputs/fundamental_metrics.csv")
OUT = Path("outputs/research_mainboard_coverage")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.nseindia.com/static/market-data/securities-available-for-trading",
}


def download(url: str) -> bytes:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=30) as response:
        payload = response.read()
    if not payload or len(payload) < 100:
        raise ValueError(f"Official NSE response too small/empty: {url}")
    return payload


def symbol_column(frame: pd.DataFrame) -> str:
    normalized = {str(c).strip().upper().replace(" ", "").replace("_", ""): c for c in frame.columns}
    for key in ("SYMBOL", "TCKRSYMB", "TRADINGSYMBOL", "SECURITYSYMBOL"):
        if key in normalized:
            return normalized[key]
    raise ValueError(f"No symbol column in official NSE CSV: {list(frame.columns)}")


def parse_symbols(payload: bytes) -> set[str]:
    frame = pd.read_csv(pd.io.common.BytesIO(payload), dtype=str)
    if frame.empty:
        raise ValueError("Official NSE CSV parsed empty")
    col = symbol_column(frame)
    values = {str(x).strip().upper() for x in frame[col].dropna()
              if str(x).strip() and str(x).strip().lower() not in {"nan", "symbol"}}
    if not values:
        raise ValueError("No symbols in official NSE CSV")
    return values


def compare(main_symbols: set[str], sme_symbols: set[str], cache_symbols: set[str]):
    main = main_symbols - sme_symbols
    if not main or not sme_symbols or not cache_symbols:
        raise ValueError("Mainboard, SME, and fundamental cache symbol sets must be non-empty")
    cached_main = main & cache_symbols
    missing = main - cache_symbols
    outside = cache_symbols - main
    return main, cached_main, missing, outside


def main() -> int:
    retrieved = datetime.now(timezone.utc)
    main_raw = download(MAIN_URL)
    sme_raw = download(SME_URL)
    main_raw_symbols = parse_symbols(main_raw)
    sme_symbols = parse_symbols(sme_raw)
    cache = pd.read_csv(CACHE, dtype=str, keep_default_na=False, low_memory=False)
    if "TckrSymb" not in cache.columns:
        raise ValueError("Fundamental cache missing TckrSymb")
    cache_symbols = {str(x).strip().upper() for x in cache["TckrSymb"]
                     if str(x).strip() and str(x).strip().upper() not in {"NAN", "NONE"}}
    main, cached, missing, outside = compare(main_raw_symbols, sme_symbols, cache_symbols)
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"Symbol": sorted(main)}).to_csv(OUT / "dated_mainboard_universe.csv", index=False)
    pd.DataFrame({"Symbol": sorted(missing)}).to_csv(OUT / "missing_fundamental_symbols.csv", index=False)
    pd.DataFrame({"Symbol": sorted(outside)}).to_csv(OUT / "cache_symbols_outside_current_mainboard.csv", index=False)
    summary = {
        "GeneratedAtUTC": retrieved.isoformat(),
        "UniverseAsOfDateUTC": retrieved.date().isoformat(),
        "MainBoardSourceURL": MAIN_URL,
        "SMESourceURL": SME_URL,
        "MainBoardRawSHA256": hashlib.sha256(main_raw).hexdigest(),
        "SMERawSHA256": hashlib.sha256(sme_raw).hexdigest(),
        "MainBoardRawBytes": len(main_raw),
        "SMERawBytes": len(sme_raw),
        "MainBoardRawUniqueSymbols": len(main_raw_symbols),
        "SMEUniqueSymbols": len(sme_symbols),
        "MainBoardUniqueSymbolsAfterSMEExclusion": len(main),
        "FundamentalCacheUniqueSymbols": len(cache_symbols),
        "CachedMainBoardSymbols": len(cached),
        "MissingFundamentalSymbols": len(missing),
        "CacheSymbolsOutsideCurrentMainBoard": len(outside),
        "CoveragePercent": round(100.0 * len(cached) / len(main), 4),
        "MissingPercent": round(100.0 * len(missing) / len(main), 4),
        "Method": "NSE official equity list minus NSE official SME list; symbol-set comparison against current fundamental_metrics.csv",
        "ProductionCachesModified": False,
        "BhavcopyModified": False,
        "MasterSpecificationModified": False,
        "ProductionScannerModified": False,
    }
    (OUT / "mainboard_coverage_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
