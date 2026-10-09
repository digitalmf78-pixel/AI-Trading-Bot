"""Refresh NSE V8 sector membership and historical index closes.

Sector membership is fetched from official NSE Indices constituent CSVs using
known filename variants. Sector index closes are read from NSE's official daily
all-indices archive (ind_close_all_DDMMYYYY.csv), not guessed Yahoo symbols.
Unavailable/invalid feeds remain absent and are never converted to PASS.
"""
from __future__ import annotations

import json
import time
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

INPUT_DIR = Path("data") / "inputs"
CACHE_DIR = Path("data") / "cache" / "sector_index_daily"
MAP_PATH = INPUT_DIR / "sector_map.csv"
HISTORY_PATH = INPUT_DIR / "sector_history.csv"
MAP_COLUMNS = ["TckrSymb", "Sector", "SectorIndexSymbol"]
HISTORY_COLUMNS = ["Date", "Sector", "Close"]

# (sector label, candidate official constituent CSV names, NSE daily index name,
#  symbol reserved for optional intraday_bars.csv index confirmation)
SECTOR_INDICES = [
    ("Nifty Auto", ["ind_niftyautolist.csv", "ind_niftyauto_list.csv"], "Nifty Auto", "NIFTY AUTO"),
    ("Nifty Bank", ["ind_niftybanklist.csv", "ind_niftybank_list.csv"], "Nifty Bank", "NIFTY BANK"),
    ("Nifty Financial Services", ["ind_niftyfinancialserviceslist.csv", "ind_niftyfinancialservices_list.csv"], "Nifty Financial Services", "NIFTY FINANCIAL SERVICES"),
    ("Nifty FMCG", ["ind_niftyfmcglist.csv", "ind_niftyfmcg_list.csv"], "Nifty FMCG", "NIFTY FMCG"),
    ("Nifty IT", ["ind_niftyitlist.csv", "ind_niftyit_list.csv"], "Nifty IT", "NIFTY IT"),
    ("Nifty Media", ["ind_niftymedialist.csv", "ind_niftymedia_list.csv"], "Nifty Media", "NIFTY MEDIA"),
    ("Nifty Metal", ["ind_niftymetallist.csv", "ind_niftymetal_list.csv"], "Nifty Metal", "NIFTY METAL"),
    ("Nifty Pharma", ["ind_niftypharmalist.csv", "ind_niftypharma_list.csv"], "Nifty Pharma", "NIFTY PHARMA"),
    ("Nifty PSU Bank", ["ind_niftypsubanklist.csv", "ind_niftypsubank_list.csv"], "Nifty PSU Bank", "NIFTY PSU BANK"),
    ("Nifty Realty", ["ind_niftyrealtylist.csv", "ind_niftyrealty_list.csv"], "Nifty Realty", "NIFTY REALTY"),
    ("Nifty Consumer Durables", ["ind_niftyconsumerdurableslist.csv", "ind_niftyconsumerdurables_list.csv"], "Nifty Consumer Durables", "NIFTY CONSUMER DURABLES"),
    ("Nifty Oil and Gas", ["ind_niftyoilgaslist.csv", "ind_niftyoilgas_list.csv"], "Nifty Oil & Gas", "NIFTY OIL & GAS"),
    ("Nifty Healthcare", ["ind_niftyhealthcarelist.csv", "ind_niftyhealthcare_list.csv"], "Nifty Healthcare", "NIFTY HEALTHCARE"),
    ("Nifty Capital Goods", ["ind_niftycapitalgoodslist.csv", "ind_niftycapitalgoods_list.csv"], "Nifty Capital Goods", "NIFTY CAPITAL GOODS"),
    ("Nifty Chemicals", ["ind_niftychemicalslist.csv", "ind_niftychemicals_list.csv"], "Nifty Chemicals", "NIFTY CHEMICALS"),
    ("Nifty Power", ["ind_niftypowerlist.csv", "ind_niftypower_list.csv"], "Nifty Power", "NIFTY POWER"),
    ("Nifty Private Bank", ["ind_nifty_privatebanklist.csv", "ind_nifty_privatebank_list.csv", "ind_niftyprivatebanklist.csv"], "Nifty Private Bank", "NIFTY PRIVATE BANK"),
    ("Nifty Insurance", ["ind_niftyinsurancelist.csv", "ind_niftyinsurance_list.csv"], "Nifty Insurance", "NIFTY INSURANCE"),
    ("Nifty Consumer Services", ["ind_niftyconsumerserviceslist.csv", "ind_niftyconsumerservices_list.csv"], "Nifty Consumer Services", "NIFTY CONSUMER SERVICES"),
    ("Nifty Telecommunications", ["ind_niftytelecommunicationslist.csv", "ind_niftytelecomlist.csv", "ind_niftytelecom_list.csv"], "Nifty Telecommunications", "NIFTY TELECOMMUNICATIONS"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-auto",
}
NSE_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.nseindia.com/all-reports",
}


def _clean_symbol(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    value = str(value).strip().upper()
    return value if value and value not in {"NAN", "NONE", "-"} else ""


def _normalise_name(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().replace("&", "AND").split())


def _download_constituents(session: requests.Session, sector: str, filenames: list[str], index_symbol: str) -> list[dict[str, str]]:
    """Try official filename variants; reject HTML/error pages and malformed CSVs."""
    last_error = "no candidate filenames"
    for filename in filenames:
        url = f"https://www.niftyindices.com/IndexConstituent/{filename}"
        try:
            response = session.get(url, headers=HEADERS, timeout=15)
            if response.status_code != 200:
                last_error = f"HTTP {response.status_code} for {filename}"
                continue
            content = response.content or b""
            if not content or b"<html" in content[:1500].lower() or b"<!doctype html" in content[:1500].lower():
                last_error = f"HTML response for {filename}"
                continue
            frame = pd.read_csv(BytesIO(content))
            symbol_col = next((c for c in frame.columns if str(c).strip().casefold() in {"symbol", "ticker", "ticker symbol"}), None)
            if symbol_col is None:
                last_error = f"no Symbol column in {filename}: {list(frame.columns)}"
                continue
            symbols = sorted({_clean_symbol(v) for v in frame[symbol_col].tolist()} - {""})
            if not symbols:
                last_error = f"empty Symbol column in {filename}"
                continue
            print(f"[SECTOR] Constituents OK: {sector} via {filename} ({len(symbols)} symbols)")
            return [{"TckrSymb": symbol, "Sector": sector, "SectorIndexSymbol": index_symbol} for symbol in symbols]
        except Exception as exc:
            last_error = f"{filename}: {exc}"
    print(f"[SECTOR] Constituents unavailable for {sector}: {last_error}")
    return []


def _download_daily_index_file(session: requests.Session, day: pd.Timestamp) -> pd.DataFrame:
    """Load one official NSE all-indices EOD CSV, cached by date."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    date_key = day.strftime("%d%m%Y")
    cache_path = CACHE_DIR / f"ind_close_all_{date_key}.csv"
    if cache_path.exists():
        try:
            cached = pd.read_csv(cache_path)
            if not cached.empty:
                return cached
        except Exception:
            pass
    url = f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{date_key}.csv"
    try:
        response = session.get(url, headers=NSE_HEADERS, timeout=20)
        if response.status_code == 404:
            # A missing weekday is usually an exchange holiday or not-yet-published file.
            return pd.DataFrame()
        response.raise_for_status()
        content = response.content or b""
        if not content or b"<html" in content[:1500].lower() or b"<!doctype html" in content[:1500].lower():
            print(f"[SECTOR] NSE index archive returned non-CSV for {day.date()}")
            return pd.DataFrame()
        frame = pd.read_csv(BytesIO(content))
        if frame.empty:
            return pd.DataFrame()
        frame.to_csv(cache_path, index=False)
        return frame
    except Exception as exc:
        print(f"[SECTOR] Index archive unavailable for {day.date()}: {exc}")
        return pd.DataFrame()


def _history_from_nse_archive(session: requests.Session, asof: pd.Timestamp) -> tuple[list[dict[str, Any]], int]:
    """Fetch 45 prior weekdays of official NSE index closes; retain exact-date rows only."""
    index_lookup = {
        _normalise_name(index_name): sector
        for sector, _files, index_name, _symbol in SECTOR_INDICES
    }
    collected: dict[tuple[str, str], float] = {}
    exact_sectors: set[str] = set()
    # 45 weekdays gives a buffer for holidays and should exceed the required 21 closes.
    for offset in range(0, 64):
        day = asof - pd.Timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        frame = _download_daily_index_file(session, day)
        if not frame.empty:
            cols = {str(c).strip().casefold(): c for c in frame.columns}
            name_col = next((cols[k] for k in ("index name", "index_name", "index") if k in cols), None)
            date_col = next((cols[k] for k in ("index date", "index_date", "date") if k in cols), None)
            close_col = next((cols[k] for k in ("closing", "close", "closing value") if k in cols), None)
            if name_col is not None and close_col is not None:
                for _, row in frame.iterrows():
                    norm = _normalise_name(row.get(name_col, ""))
                    sector = index_lookup.get(norm)
                    if not sector:
                        continue
                    close = pd.to_numeric(row.get(close_col), errors="coerce")
                    if pd.isna(close) or float(close) <= 0:
                        continue
                    date_value = pd.to_datetime(row.get(date_col), errors="coerce") if date_col is not None else pd.Timestamp(day)
                    if pd.isna(date_value):
                        date_value = pd.Timestamp(day)
                    actual_date = pd.Timestamp(date_value).normalize()
                    # Trust the date in the CSV, not the URL date.
                    if actual_date > asof or actual_date < asof - pd.Timedelta(days=70):
                        continue
                    collected[(actual_date.strftime("%Y-%m-%d"), sector)] = float(close)
                    if actual_date == asof:
                        exact_sectors.add(sector)
        # stop once each tracked sector has >=21 distinct dates through asof and exact asof close
        if offset >= 28:
            enough = True
            for sector, _files, _name, _symbol in SECTOR_INDICES:
                dates = [pd.Timestamp(d) for (d, sec) in collected if sec == sector and pd.Timestamp(d) <= asof]
                if sector not in exact_sectors or len(set(dates)) < 21:
                    enough = False
                    break
            if enough:
                break
        time.sleep(0.08)

    rows = [{"Date": date, "Sector": sector, "Close": close} for (date, sector), close in collected.items()]
    return rows, len(exact_sectors)


def refresh_sector_inputs(asof_date: Any, force: bool = False) -> dict[str, Any]:
    """Refresh sector_map.csv and sector_history.csv for a specific EOD date."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    asof = pd.to_datetime(asof_date, errors="coerce")
    if pd.isna(asof):
        raise ValueError(f"Invalid sector EOD date: {asof_date!r}")
    asof = pd.Timestamp(asof).normalize()
    session = requests.Session()
    mappings: list[dict[str, str]] = []
    successful_maps = 0
    seen_symbols: set[str] = set()

    # Warm the official host session before downloading its CSV files.
    try:
        session.get("https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-auto", headers=HEADERS, timeout=12)
    except Exception:
        pass
    for sector, filenames, _index_name, index_symbol in SECTOR_INDICES:
        rows = _download_constituents(session, sector, filenames, index_symbol)
        if rows:
            successful_maps += 1
            for row in rows:
                symbol = row["TckrSymb"]
                # First matching tracked sector wins for symbols in multiple indices.
                if symbol not in seen_symbols:
                    mappings.append(row)
                    seen_symbols.add(symbol)
        time.sleep(0.1)

    new_map = pd.DataFrame(mappings, columns=MAP_COLUMNS)
    old_map = pd.DataFrame(columns=MAP_COLUMNS)
    if MAP_PATH.exists():
        try:
            candidate = pd.read_csv(MAP_PATH)
            if set(MAP_COLUMNS).issubset(candidate.columns):
                old_map = candidate[MAP_COLUMNS]
        except Exception:
            pass
    # Fresh official membership takes precedence; cached rows only fill symbols absent from refresh.
    map_frame = pd.concat([new_map, old_map], ignore_index=True).drop_duplicates(subset=["TckrSymb"], keep="first")
    if not map_frame.empty:
        map_frame = map_frame.sort_values("TckrSymb")
        map_frame.to_csv(MAP_PATH, index=False)
    else:
        print("[SECTOR] No official constituent mappings retrieved; existing map preserved if present")

    new_history_rows, sectors_with_asof_new = _history_from_nse_archive(session, asof)
    new_history = pd.DataFrame(new_history_rows, columns=HISTORY_COLUMNS)
    old_history = pd.DataFrame(columns=HISTORY_COLUMNS)
    if HISTORY_PATH.exists():
        try:
            candidate = pd.read_csv(HISTORY_PATH)
            if set(HISTORY_COLUMNS).issubset(candidate.columns):
                old_history = candidate[HISTORY_COLUMNS]
        except Exception:
            pass
    history_frame = pd.concat([old_history, new_history], ignore_index=True)
    if not history_frame.empty:
        history_frame["Date"] = pd.to_datetime(history_frame["Date"], errors="coerce")
        history_frame["Close"] = pd.to_numeric(history_frame["Close"], errors="coerce")
        history_frame = history_frame.dropna(subset=["Date", "Sector", "Close"])
        history_frame = history_frame.drop_duplicates(subset=["Date", "Sector"], keep="last").sort_values(["Sector", "Date"])
        history_frame["Date"] = history_frame["Date"].dt.strftime("%Y-%m-%d")
        history_frame.to_csv(HISTORY_PATH, index=False)
    else:
        print("[SECTOR] No official sector history retrieved; existing history preserved if present")

    exact_history = history_frame[pd.to_datetime(history_frame["Date"], errors="coerce").dt.normalize().eq(asof)] if not history_frame.empty else pd.DataFrame()
    sectors_with_asof = int(exact_history["Sector"].nunique()) if not exact_history.empty else 0
    history_success = len({r["Sector"] for r in new_history_rows if r["Date"] == asof.strftime("%Y-%m-%d")})
    print(f"[SECTOR] Mapping rows: {len(map_frame)}; constituent feeds: {successful_maps}/{len(SECTOR_INDICES)}")
    print(f"[SECTOR] History rows: {len(history_frame)}; official NSE exact-date sector closes: {sectors_with_asof}; fresh archive sectors: {history_success}")
    if sectors_with_asof == 0:
        print("[SECTOR] No exact-date sector history available; SectorStrengthStatus remains WAIT_FOR_DATA")
    return {
        "mapping_rows": len(map_frame),
        "history_rows": len(history_frame),
        "sectors_with_asof": sectors_with_asof,
        "fresh_archive_sectors": history_success,
        "constituent_feeds": successful_maps,
        "reused": False,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Refresh V8 sector inputs")
    parser.add_argument("--date", required=True, help="EOD date, YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Force refresh cached inputs")
    args = parser.parse_args()
    print(json.dumps(refresh_sector_inputs(args.date, force=args.force), default=str))
