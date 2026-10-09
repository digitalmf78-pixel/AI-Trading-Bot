"""Populate V8 sector membership and 20-session sector-index history.

Membership is downloaded from NSE Indices' public constituent CSVs. Historical
index closes are fetched from Yahoo Finance's chart endpoint. A failed source is
never silently converted to a PASS: missing mappings/history remain WAIT_FOR_DATA.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

INPUT_DIR = Path("data") / "inputs"
MAP_PATH = INPUT_DIR / "sector_map.csv"
HISTORY_PATH = INPUT_DIR / "sector_history.csv"
MAP_COLUMNS = ["TckrSymb", "Sector", "SectorIndexSymbol"]
HISTORY_COLUMNS = ["Date", "Sector", "Close"]

# Index constituent files are official NSE Indices downloads. Yahoo symbols are
# used only for daily historical close series; they are also the symbols expected
# in intraday_bars.csv if index/opening confirmation is later supplied.
SECTOR_INDICES = [
    ("Nifty Auto", "ind_niftyauto_list.csv", "^CNXAUTO"),
    ("Nifty Bank", "ind_niftybank_list.csv", "^NSEBANK"),
    ("Nifty Financial Services", "ind_niftyfinancialservices_list.csv", "^CNXFINANCE"),
    ("Nifty FMCG", "ind_niftyfmcg_list.csv", "^CNXFMCG"),
    ("Nifty IT", "ind_niftyit_list.csv", "^CNXIT"),
    ("Nifty Media", "ind_niftymedia_list.csv", "^CNXMEDIA"),
    ("Nifty Metal", "ind_niftymetal_list.csv", "^CNXMETAL"),
    ("Nifty Pharma", "ind_niftypharma_list.csv", "^CNXPHARMA"),
    ("Nifty PSU Bank", "ind_niftypsubank_list.csv", "^CNXPSUBANK"),
    ("Nifty Realty", "ind_niftyrealty_list.csv", "^CNXREALTY"),
    ("Nifty Consumer Durables", "ind_niftyconsumerdurables_list.csv", "^CNXCONSUM"),
    ("Nifty Oil and Gas", "ind_niftyoilgas_list.csv", "^CNXENERGY"),
    ("Nifty Healthcare", "ind_niftyhealthcare_list.csv", "^CNXHEALTH"),
    ("Nifty Capital Goods", "ind_niftycapitalgoods_list.csv", "^CNXCG"),
    ("Nifty Chemicals", "ind_niftychemicals_list.csv", "^CNXCHEM"),
    ("Nifty Power", "ind_niftypower_list.csv", "^CNXPOWER"),
    ("Nifty Private Bank", "ind_nifty_privatebank_list.csv", "^NSEBANK"),
    ("Nifty Insurance", "ind_niftyinsurance_list.csv", "^CNXINSUR"),
    ("Nifty Consumer Services", "ind_niftyconsumerservices_list.csv", "^CNXCONS"),
    ("Nifty Telecommunications", "ind_niftytelecom_list.csv", "^CNXTELECOM"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept": "text/csv,text/plain,application/json,*/*",
    "Referer": "https://www.niftyindices.com/",
}


def _clean_symbol(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    value = str(value).strip().upper()
    return value if value and value not in {"NAN", "NONE", "-"} else ""


def _download_constituents(session: requests.Session, sector: str, filename: str, index_symbol: str) -> list[dict[str, str]]:
    url = f"https://www.niftyindices.com/IndexConstituent/{filename}"
    try:
        response = session.get(url, headers=HEADERS, timeout=12)
        response.raise_for_status()
        content = response.content
        if not content or b"<html" in content[:500].lower():
            raise ValueError("download returned HTML instead of CSV")
        from io import BytesIO
        frame = pd.read_csv(BytesIO(content))
        symbol_col = next((c for c in frame.columns if str(c).strip().casefold() in {"symbol", "ticker", "ticker symbol"}), None)
        if symbol_col is None:
            raise ValueError(f"no Symbol column; received columns: {list(frame.columns)}")
        symbols = sorted({_clean_symbol(v) for v in frame[symbol_col].tolist()} - {""})
        return [{"TckrSymb": symbol, "Sector": sector, "SectorIndexSymbol": index_symbol} for symbol in symbols]
    except Exception as exc:
        print(f"[SECTOR] Constituents unavailable for {sector}: {exc}")
        return []


def _download_index_history(session: requests.Session, sector: str, index_symbol: str, asof_date: pd.Timestamp) -> list[dict[str, Any]]:
    # A six-month range provides enough buffer for 21 distinct trading closes,
    # holidays and a delayed EOD feed. Never substitute the latest close for asof.
    import urllib.parse
    encoded_symbol = urllib.parse.quote(index_symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=6mo&interval=1d&events=history"
    headers = dict(HEADERS)
    headers["Accept"] = "application/json"
    try:
        response = session.get(url, headers=headers, timeout=12)
        response.raise_for_status()
        payload = response.json()
        chart = payload.get("chart", {})
        if chart.get("error"):
            raise ValueError(str(chart["error"]))
        result = (chart.get("result") or [None])[0]
        if not result:
            raise ValueError("no chart result")
        timestamps = result.get("timestamp") or []
        quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quotes.get("close") or []
        rows: list[dict[str, Any]] = []
        for stamp, close in zip(timestamps, closes):
            if close is None:
                continue
            date = pd.to_datetime(int(stamp), unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None).normalize()
            if date > asof_date.normalize():
                continue
            value = float(close)
            if value > 0:
                rows.append({"Date": date.strftime("%Y-%m-%d"), "Sector": sector, "Close": value})
        if not rows or pd.Timestamp(rows[-1]["Date"]).normalize() != asof_date.normalize():
            print(f"[SECTOR] {sector}: no exact close for EOD date {asof_date.date()}; kept as unavailable")
            return []
        return rows
    except Exception as exc:
        print(f"[SECTOR] History unavailable for {sector} ({index_symbol}): {exc}")
        return []


def refresh_sector_inputs(asof_date: Any, force: bool = False) -> dict[str, Any]:
    """Refresh sector_map.csv and sector_history.csv for a specific EOD date.

    Writes files only when at least one official constituent map and one sector
    history series have been retrieved. Any sector without a matching EOD close
    remains absent, so v8_layers_14_41 correctly marks it WAIT_FOR_DATA.
    """
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    asof = pd.to_datetime(asof_date, errors="coerce")
    if pd.isna(asof):
        raise ValueError(f"Invalid sector EOD date: {asof_date!r}")
    asof = pd.Timestamp(asof).normalize()

    # Always try refreshing so a partial earlier download cannot freeze the sector
    # universe. Successfully fetched rows replace matching old rows; failed feeds
    # retain prior rows, but only an exact EOD-date close can pass Layer 14.
    session = requests.Session()
    mappings: list[dict[str, str]] = []
    history: list[dict[str, Any]] = []
    # First matching sector wins for symbols present in more than one index.
    seen_symbols: set[str] = set()
    successful_maps = 0
    successful_history = 0
    for sector, filename, index_symbol in SECTOR_INDICES:
        rows = _download_constituents(session, sector, filename, index_symbol)
        if rows:
            successful_maps += 1
            for row in rows:
                symbol = row["TckrSymb"]
                if symbol not in seen_symbols:
                    mappings.append(row)
                    seen_symbols.add(symbol)
        hist_rows = _download_index_history(session, sector, index_symbol, asof)
        if hist_rows:
            successful_history += 1
            history.extend(hist_rows)
        time.sleep(0.12)

    new_map = pd.DataFrame(mappings, columns=MAP_COLUMNS).drop_duplicates(subset=["TckrSymb"], keep="first")
    old_map = pd.DataFrame(columns=MAP_COLUMNS)
    if MAP_PATH.exists():
        try:
            old_map = pd.read_csv(MAP_PATH)
            if not set(MAP_COLUMNS).issubset(old_map.columns):
                old_map = pd.DataFrame(columns=MAP_COLUMNS)
            else:
                old_map = old_map[MAP_COLUMNS]
        except Exception:
            old_map = pd.DataFrame(columns=MAP_COLUMNS)
    # Fresh official membership takes precedence; keep old rows only for feeds
    # that failed, without marking those rows as verified current membership.
    map_frame = pd.concat([new_map, old_map], ignore_index=True).drop_duplicates(subset=["TckrSymb"], keep="first")

    new_history = pd.DataFrame(history, columns=HISTORY_COLUMNS)
    old_history = pd.DataFrame(columns=HISTORY_COLUMNS)
    if HISTORY_PATH.exists():
        try:
            old_history = pd.read_csv(HISTORY_PATH)
            if not set(HISTORY_COLUMNS).issubset(old_history.columns):
                old_history = pd.DataFrame(columns=HISTORY_COLUMNS)
            else:
                old_history = old_history[HISTORY_COLUMNS]
        except Exception:
            old_history = pd.DataFrame(columns=HISTORY_COLUMNS)
    # New exact-date closes replace old values; historical rows remain cached.
    history_frame = pd.concat([old_history, new_history], ignore_index=True)
    if not map_frame.empty:
        map_frame = map_frame.sort_values("TckrSymb")
    if not history_frame.empty:
        history_frame["Date"] = pd.to_datetime(history_frame["Date"], errors="coerce")
        history_frame["Close"] = pd.to_numeric(history_frame["Close"], errors="coerce")
        history_frame = history_frame.dropna(subset=["Date", "Sector", "Close"])
        history_frame = history_frame.drop_duplicates(subset=["Date", "Sector"], keep="last").sort_values(["Sector", "Date"])
        history_frame["Date"] = history_frame["Date"].dt.strftime("%Y-%m-%d")

    # Do not overwrite valid existing data with an empty result.
    if not map_frame.empty:
        map_frame.to_csv(MAP_PATH, index=False)
    else:
        print("[SECTOR] No official constituent mappings retrieved; existing map preserved if present")
    if not history_frame.empty:
        history_frame.to_csv(HISTORY_PATH, index=False)
    else:
        print("[SECTOR] No sector history retrieved; existing history preserved if present")

    exact_history = history_frame[pd.to_datetime(history_frame["Date"], errors="coerce").dt.normalize().eq(asof)] if not history_frame.empty else pd.DataFrame()
    sectors_with_asof = int(exact_history["Sector"].nunique()) if not exact_history.empty else 0
    print(f"[SECTOR] Mapping rows: {len(map_frame)}; constituent feeds: {successful_maps}/{len(SECTOR_INDICES)}")
    print(f"[SECTOR] History rows: {len(history_frame)}; index histories: {successful_history}/{len(SECTOR_INDICES)}; exact EOD sector closes: {sectors_with_asof}")
    if sectors_with_asof == 0:
        print("[SECTOR] No exact-date sector history available; SectorStrengthStatus remains WAIT_FOR_DATA")
    return {"mapping_rows": len(map_frame), "history_rows": len(history_frame), "sectors_with_asof": sectors_with_asof, "reused": False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Refresh V8 sector inputs")
    parser.add_argument("--date", required=True, help="EOD date, YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Force refresh even if current-date inputs exist")
    args = parser.parse_args()
    result = refresh_sector_inputs(args.date, force=args.force)
    print(json.dumps(result, default=str))
