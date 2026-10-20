"""Official NSE Main Board eligibility gate for NSE Swing Trading V8.

Uses NSE's own downloadable securities lists, not symbol-name/price heuristics.
Unknown classification fails closed so an unverified symbol cannot reach the
strategy's delivery, liquidity, or technical gates.
"""
from __future__ import annotations

import io
import os
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

NSE_MAIN_BOARD_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_SME_URL = "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv"
CACHE_DIR = Path("data/cache/universe")
CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.nseindia.com/static/market-data/securities-available-for-trading",
}


def _symbol_column(frame: pd.DataFrame) -> str:
    normalized = {str(col).strip().upper().replace(" ", "").replace("_", ""): col for col in frame.columns}
    for candidate in ("SYMBOL", "TCKRSYMB", "TRADINGSYMBOL", "SECURITYSYMBOL"):
        if candidate in normalized:
            return normalized[candidate]
    raise ValueError(f"Official NSE list has no recognized symbol column; columns={list(frame.columns)}")


def _symbols_from_csv(payload: bytes) -> set[str]:
    frame = pd.read_csv(io.BytesIO(payload), dtype=str)
    if frame.empty:
        raise ValueError("Official NSE classification CSV is empty")
    col = _symbol_column(frame)
    symbols = {
        str(value).strip().upper()
        for value in frame[col].dropna().tolist()
        if str(value).strip() and str(value).strip().lower() not in {"nan", "symbol"}
    }
    if not symbols:
        raise ValueError("Official NSE classification CSV contained no symbols")
    return symbols


def _get_official_symbols(name: str, url: str, session: requests.Session | None = None) -> tuple[set[str], str]:
    """Fetch official CSV; use a previously validated cache if fetch fails."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{name}.csv"
    timestamp_path = CACHE_DIR / f"{name}.fetched_at"
    client = session or requests.Session()
    client.headers.update(HEADERS)
    fetch_error: Exception | None = None

    try:
        response = client.get(url, timeout=25)
        response.raise_for_status()
        symbols = _symbols_from_csv(response.content)
        cache_path.write_bytes(response.content)
        timestamp_path.write_text(str(int(time.time())), encoding="utf-8")
        return symbols, "OFFICIAL_LIVE"
    except Exception as exc:
        fetch_error = exc

    if cache_path.exists():
        try:
            symbols = _symbols_from_csv(cache_path.read_bytes())
            fetched_at = int(timestamp_path.read_text(encoding="utf-8").strip()) if timestamp_path.exists() else 0
            age = max(0, int(time.time()) - fetched_at) if fetched_at else None
            age_text = f"age_seconds={age}" if age is not None else "cache_age=unknown"
            print(f"[MAIN_BOARD] {name} live fetch failed; using validated cache ({age_text}): {fetch_error}")
            return symbols, "OFFICIAL_CACHED"
        except Exception as cache_exc:
            raise RuntimeError(f"Official NSE {name} list unavailable and cache invalid: live={fetch_error}; cache={cache_exc}") from cache_exc
    raise RuntimeError(f"Official NSE {name} list unavailable and no validated cache exists: {fetch_error}") from fetch_error


def load_official_board_lists(session: requests.Session | None = None) -> tuple[set[str], set[str], dict[str, str]]:
    """Return (Main Board symbols, SME symbols, source statuses)."""
    main_symbols, main_source = _get_official_symbols("nse_main_board_equity", NSE_MAIN_BOARD_URL, session)
    sme_symbols, sme_source = _get_official_symbols("nse_sme_equity", NSE_SME_URL, session)
    if not main_symbols or not sme_symbols:
        raise RuntimeError("Official Main Board/SME symbol lists must both be non-empty")
    return main_symbols, sme_symbols, {"main_board_source": main_source, "sme_source": sme_source}


def apply_main_board_filter(
    frame: pd.DataFrame,
    main_board_symbols: Iterable[str],
    sme_symbols: Iterable[str],
    source_status: str = "OFFICIAL_NSE_LISTS",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep only officially classified Main Board symbols and create an audit."""
    audit_columns = ["TckrSymb", "BoardClassification", "MainBoardStatus", "ClassificationSource"]
    if frame is None or frame.empty:
        return (frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame(), pd.DataFrame(columns=audit_columns))
    if "TckrSymb" not in frame.columns:
        raise ValueError("Main Board filter requires TckrSymb column")

    main_set = {str(s).strip().upper() for s in main_board_symbols if str(s).strip()}
    sme_set = {str(s).strip().upper() for s in sme_symbols if str(s).strip()}
    if not main_set or not sme_set:
        raise ValueError("Official Main Board and SME symbol sets must both be non-empty")

    symbols = frame["TckrSymb"].astype(str).str.strip().str.upper()
    is_sme = symbols.isin(sme_set)
    is_main = symbols.isin(main_set) & ~is_sme
    classifications = []
    statuses = []
    for symbol, sme, main in zip(symbols, is_sme, is_main):
        if sme:
            classifications.append("SME")
            statuses.append("EXCLUDED_SME")
        elif main:
            classifications.append("MAIN_BOARD")
            statuses.append("PASS_MAIN_BOARD")
        else:
            classifications.append("UNKNOWN_NOT_IN_OFFICIAL_MAIN_BOARD_LIST")
            statuses.append("EXCLUDED_UNVERIFIED_CLASSIFICATION")
    audit = pd.DataFrame({
        "TckrSymb": symbols,
        "BoardClassification": classifications,
        "MainBoardStatus": statuses,
        "ClassificationSource": source_status,
    }, columns=audit_columns)
    keep_mask = pd.Series(statuses, index=frame.index).eq("PASS_MAIN_BOARD")
    filtered = frame.loc[keep_mask].copy()
    return filtered, audit.drop_duplicates(subset=["TckrSymb"], keep="first").reset_index(drop=True)


def apply_official_main_board_filter(frame: pd.DataFrame, session: requests.Session | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch official NSE lists and apply strict Main Board-only eligibility."""
    main_symbols, sme_symbols, source_status = load_official_board_lists(session=session)
    source_label = f"NSE_MAIN={source_status['main_board_source']};NSE_SME={source_status['sme_source']}"
    filtered, audit = apply_main_board_filter(frame, main_symbols, sme_symbols, source_status=source_label)
    print(
        f"[MAIN_BOARD] Official classification applied: input={len(frame)}; "
        f"eligible={len(filtered)}; excluded_sme={(audit['MainBoardStatus'] == 'EXCLUDED_SME').sum()}; "
        f"excluded_unverified={(audit['MainBoardStatus'] == 'EXCLUDED_UNVERIFIED_CLASSIFICATION').sum()}; "
        f"sources={source_label}"
    )
    return filtered, audit
