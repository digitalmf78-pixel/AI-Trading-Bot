"""Refresh NSE V8 sector membership and historical index closes.

Sector membership is fetched from official NSE Indices constituent CSVs using
known filename variants. Sector index closes are read from NSE's official daily
all-indices archive (ind_close_all_DDMMYYYY.csv), not guessed Yahoo symbols.
Unavailable/invalid feeds remain absent and are never converted to PASS.
"""
from __future__ import annotations

import json
import re
import time
from html import unescape
from html.parser import HTMLParser
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
    ("Nifty Financial Services", ["ind_niftyfinancelist.csv", "ind_niftyfinancialserviceslist.csv", "ind_niftyfinancialservices_list.csv"], "Nifty Financial Services", "NIFTY FINANCIAL SERVICES"),
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
    ("Nifty Telecommunications", ["ind_niftyTelecommunications_list.csv", "ind_niftytelecommunications_list.csv", "ind_niftytelecommunicationslist.csv", "ind_niftytelecomlist.csv", "ind_niftytelecom_list.csv"], "Nifty Telecommunications", "NIFTY TELECOMMUNICATIONS"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-auto",
}
NSE_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Referer": "https://www.nseindia.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
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
    """Load one official NSE all-indices EOD CSV, with explicit archive diagnostics.

    A 404 can mean a holiday or an unpublished report, so both official archive
    hosts are tried. Every outcome is logged to distinguish 404s from access,
    server, HTML/challenge, and CSV-schema problems. Existing cache files are
    preserved and are never deleted by this diagnostic change.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    date_key = day.strftime("%d%m%Y")
    cache_path = CACHE_DIR / f"ind_close_all_{date_key}.csv"
    if cache_path.exists():
        try:
            cached = pd.read_csv(cache_path)
            if not cached.empty:
                print(
                    f"[SECTOR][ARCHIVE] CACHE_HIT date={day.date()} "
                    f"rows={len(cached)} columns={list(cached.columns)}"
                )
                return cached
            print(f"[SECTOR][ARCHIVE] CACHE_EMPTY date={day.date()} path={cache_path}")
        except Exception as exc:
            print(f"[SECTOR][ARCHIVE] CACHE_READ_ERROR date={day.date()} error={exc}")

    urls = [
        f"https://archives.nseindia.com/content/indices/ind_close_all_{date_key}.csv",
        f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{date_key}.csv",
    ]
    errors: list[str] = []
    for url in urls:
        host = url.split('/')[2]
        try:
            response = session.get(url, headers=NSE_HEADERS, timeout=25)
            content = response.content or b""
            content_type = response.headers.get("Content-Type", "(missing)")
            preview = content[:100].decode("utf-8", "replace").replace("\r", " ").replace("\n", " ")
            redirect_chain = []
            for prior in getattr(response, "history", []) or []:
                redirect_chain.append({
                    "status": getattr(prior, "status_code", None),
                    "url": getattr(prior, "url", ""),
                    "location": getattr(getattr(prior, "headers", {}), "get", lambda *_: "")("Location", ""),
                })
            final_url = getattr(response, "url", url)
            print(
                f"[SECTOR][ARCHIVE] FETCH date={day.date()} host={host} "
                f"status={response.status_code} content_type={content_type!r} "
                f"bytes={len(content)} final_url={final_url!r} "
                f"redirects={redirect_chain!r} preview={preview!r}"
            )
            if response.status_code == 404:
                errors.append(f"HTTP 404 from {host}")
                continue
            if response.status_code != 200:
                errors.append(f"HTTP {response.status_code} from {host}")
                continue
            if (
                not content
                or b"<html" in content[:1500].lower()
                or b"<!doctype html" in content[:1500].lower()
            ):
                errors.append(f"HTTP 200 but non-CSV/HTML response from {host}")
                continue
            try:
                frame = pd.read_csv(BytesIO(content))
            except Exception as exc:
                errors.append(f"CSV parse error from {host}: {exc}")
                continue
            if frame.empty:
                errors.append(f"empty CSV from {host}")
                continue
            print(
                f"[SECTOR][ARCHIVE] CSV_OK date={day.date()} host={host} "
                f"rows={len(frame)} columns={list(frame.columns)}"
            )
            frame.to_csv(cache_path, index=False)
            return frame
        except Exception as exc:
            errors.append(f"{host}: {type(exc).__name__}: {exc}")
            print(f"[SECTOR][ARCHIVE] REQUEST_ERROR date={day.date()} host={host} error={type(exc).__name__}: {exc}")

    if errors and all("HTTP 404" in item for item in errors):
        print(
            f"[SECTOR][ARCHIVE] DATE_UNAVAILABLE date={day.date()} "
            "both official archive hosts returned HTTP 404 (holiday, unpublished report, or unavailable date)"
        )
    elif errors:
        print(f"[SECTOR][ARCHIVE] FETCH_FAILED date={day.date()} details={' ; '.join(errors)}")
    return pd.DataFrame()


def _history_from_nse_archive(session: requests.Session, asof: pd.Timestamp) -> tuple[list[dict[str, Any]], int]:
    """Fetch 45 prior weekdays of official NSE index closes; retain exact-date rows only."""
    index_lookup = {
        _normalise_name(index_name): sector
        for sector, _files, index_name, _symbol in SECTOR_INDICES
    }
    # NSE's official daily all-indices archive uses "Nifty Healthcare Index",
    # while the configured sector label is "Nifty Healthcare". Treat this as
    # an explicit official-name alias; do not infer or synthesize any values.
    archive_index_aliases = {
        "NIFTY HEALTHCARE INDEX": "Nifty Healthcare",
    }
    index_lookup.update(archive_index_aliases)
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
            # NSE's documented archive header is usually "Closing Index Value".
            # Accept older/alternate spellings as well.
            close_col = next((cols[k] for k in (
                "closing index value", "close index value", "closing value",
                "close value", "closing", "close",
            ) if k in cols), None)
            if name_col is None or close_col is None:
                print(f"[SECTOR] Unrecognized index CSV schema for {day.date()}: {list(frame.columns)}")
            if name_col is not None and close_col is not None:
                # Diagnostic only: expose official Healthcare-labelled rows on the
                # exact as-of archive date so a naming mismatch can be proven from
                # source data. This does not map aliases or infer a close.
                if pd.Timestamp(day).normalize() == pd.Timestamp(asof).normalize():
                    health_rows = []
                    for _, health_row in frame.iterrows():
                        raw_name = str(health_row.get(name_col, "")).strip()
                        norm_name = _normalise_name(raw_name)
                        if "HEALTH" in norm_name:
                            health_rows.append({
                                "raw_name": raw_name,
                                "normalized_name": norm_name,
                                "date": str(health_row.get(date_col, "")) if date_col is not None else "(no date column)",
                                "close": str(health_row.get(close_col, "")),
                                "lookup_match": index_lookup.get(norm_name),
                            })
                    print(
                        f"[SECTOR][ARCHIVE][HEALTHCARE_DIAGNOSTIC] "
                        f"url_date={pd.Timestamp(day).date()} asof={pd.Timestamp(asof).date()} "
                        f"rows={health_rows!r}"
                    )
                for _, row in frame.iterrows():
                    norm = _normalise_name(row.get(name_col, ""))
                    sector = index_lookup.get(norm)
                    if not sector:
                        continue
                    close = pd.to_numeric(row.get(close_col), errors="coerce")
                    if pd.isna(close) or float(close) <= 0:
                        continue
                    date_value = pd.to_datetime(row.get(date_col), errors="coerce", dayfirst=True) if date_col is not None else pd.Timestamp(day)
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


def _history_from_niftyindices_api(
    session: requests.Session,
    asof: pd.Timestamp,
    sectors_to_fetch: set[str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch official Nifty Indices historical closes for missing sector indices.

    The public historical-data page is requested first to establish a normal
    session/cookie jar before calling its ASP.NET data endpoint. Some requests
    otherwise return an HTML page instead of the expected JSON payload. The
    bootstrap is best-effort: if it fails, the data request is still attempted.
    Only valid, dated closes returned by the official service are accepted;
    missing/invalid responses remain missing and are never synthesized.
    """
    endpoint = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
    history_page = "https://www.niftyindices.com/reports/historical-data"
    start_date = (asof - pd.Timedelta(days=75)).strftime("%d %b %Y")
    end_date = asof.strftime("%d %b %Y")
    headers = {
        **HEADERS,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json; charset=utf-8",
        "Origin": "https://www.niftyindices.com",
        "Referer": history_page,
        "X-Requested-With": "XMLHttpRequest",
    }

    def bootstrap_session(reason: str) -> None:
        try:
            page_response = session.get(
                history_page,
                headers={**HEADERS, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                timeout=5,
            )
            content_type = page_response.headers.get("Content-Type", "(missing)") if hasattr(page_response, "headers") else "(missing)"
            body_size = len(getattr(page_response, "content", b"") or b"")
            print(
                f"[SECTOR][NIFTYINDICES] SESSION_BOOTSTRAP reason={reason} "
                f"status={getattr(page_response, 'status_code', '(missing)')} "
                f"content_type={content_type!r} bytes={body_size}"
            )
        except Exception as exc:
            print(
                f"[SECTOR][NIFTYINDICES] SESSION_BOOTSTRAP_FAILED reason={reason} "
                f"error={type(exc).__name__}: {exc}; continuing with data request"
            )

    # Bootstrap once for this fallback call. Failure is diagnostic, not fatal.
    bootstrap_session("initial")

    rows: list[dict[str, Any]] = []
    exact_sectors: set[str] = set()
    wanted = set(sectors_to_fetch) if sectors_to_fetch is not None else {item[0] for item in SECTOR_INDICES}
    for sector, _files, official_index_name, _symbol in SECTOR_INDICES:
        if sector not in wanted:
            continue
        api_name = official_index_name.upper().replace("AND", "&")
        inner = (
            "{'name':'" + api_name + "','startDate':'" + start_date
            + "','endDate':'" + end_date + "','indexName':'" + api_name + "'}"
        )
        payload_body = {"cinfo": inner}
        try:
            response = None
            for attempt in (1, 2):
                response = session.post(endpoint, json=payload_body, headers=headers, timeout=20)
                content_type = response.headers.get("Content-Type", "(missing)") if hasattr(response, "headers") else "(missing)"
                body_preview = str(getattr(response, "text", "") or "")[:120].replace("\r", " ").replace("\n", " ")
                if response.status_code == 200:
                    try:
                        payload = response.json()
                        break
                    except Exception as exc:
                        redirect_chain = [
                            {
                                "status": getattr(prior, "status_code", None),
                                "url": getattr(prior, "url", ""),
                                "location": getattr(getattr(prior, "headers", {}), "get", lambda *_: "")("Location", ""),
                            }
                            for prior in (getattr(response, "history", []) or [])
                        ]
                        print(
                            f"[SECTOR][NIFTYINDICES] NON_JSON index={official_index_name} "
                            f"attempt={attempt}/2 status={response.status_code} "
                            f"requested_url={endpoint!r} final_url={getattr(response, 'url', endpoint)!r} "
                            f"redirects={redirect_chain!r} content_type={content_type!r} "
                            f"preview={body_preview!r} error={type(exc).__name__}"
                        )
                else:
                    print(
                        f"[SECTOR][NIFTYINDICES] HTTP {response.status_code} "
                        f"index={official_index_name} attempt={attempt}/2 "
                        f"content_type={content_type!r} preview={body_preview!r}"
                    )
                if attempt == 1:
                    # Retry once after refreshing the official page session when
                    # the endpoint returned an HTTP error or non-JSON HTML.
                    bootstrap_session("retry-" + official_index_name)
            else:
                continue

            raw = payload.get("d") if isinstance(payload, dict) else None
            if isinstance(raw, str):
                try:
                    data = json.loads(raw)
                except Exception as exc:
                    print(f"[SECTOR][NIFTYINDICES] INVALID_JSON_PAYLOAD index={official_index_name}: {type(exc).__name__}")
                    data = []
            else:
                data = raw
            if not isinstance(data, list) or not data:
                print(f"[SECTOR][NIFTYINDICES] NO_DATA index={official_index_name} date={asof.date()}")
                continue
            accepted = 0
            for item in data:
                if not isinstance(item, dict):
                    continue
                raw_date = item.get("HistoricalDate") or item.get("Date") or item.get("date")
                raw_close = item.get("CLOSE") or item.get("Close") or item.get("close")
                parsed_date = pd.to_datetime(raw_date, errors="coerce", dayfirst=True)
                close = pd.to_numeric(raw_close, errors="coerce")
                if pd.isna(parsed_date) or pd.isna(close) or float(close) <= 0:
                    continue
                parsed_date = pd.Timestamp(parsed_date).normalize()
                if parsed_date > asof or parsed_date < asof - pd.Timedelta(days=75):
                    continue
                date_text = parsed_date.strftime("%Y-%m-%d")
                rows.append({"Date": date_text, "Sector": sector, "Close": float(close)})
                accepted += 1
                if parsed_date == asof:
                    exact_sectors.add(sector)
            sector_dates = {pd.Timestamp(r["Date"]).date() for r in rows if r["Sector"] == sector}
            print(
                f"[SECTOR][NIFTYINDICES] index={official_index_name} "
                f"accepted_rows={accepted} exact_date={asof.date() in sector_dates}"
            )
        except Exception as exc:
            print(f"[SECTOR][NIFTYINDICES] REQUEST_ERROR index={official_index_name}: {type(exc).__name__}: {exc}")
        time.sleep(0.1)

    # Deduplicate exact date/index rows returned by the official service.
    deduped = {(r["Date"], r["Sector"]): r["Close"] for r in rows}
    output = [{"Date": d, "Sector": sec, "Close": close} for (d, sec), close in deduped.items()]
    print(f"[SECTOR][NIFTYINDICES] fallback rows={len(output)} exact_date_sectors={len(exact_sectors)}/{len(SECTOR_INDICES)}")
    return output, len(exact_sectors)




# Official NSE equity quote classification for shortlisted stocks that are not
# constituents of one of the tracked sector indices. This is a conservative
# bridge: only explicit NSE sector labels with a corresponding tracked sector
# benchmark are mapped. Unmatched labels remain unmapped/WAIT_FOR_DATA.
NIFTY500_CONSTITUENTS_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"

# Exact official Industry labels -> tracked sector benchmark. This is a
# conservative taxonomy bridge, not a claim that every mapped stock is itself
# a constituent of that sector index. Unknown/ambiguous labels stay unmapped.
INDUSTRY_TO_TRACKED_INDEX = {
    "AUTO COMPONENTS": ("Nifty Auto", "NIFTY AUTO"),
    "AUTOMOBILES": ("Nifty Auto", "NIFTY AUTO"),
    "AUTOMOBILE AND AUTO COMPONENTS": ("Nifty Auto", "NIFTY AUTO"),
    "BANKS": ("Nifty Bank", "NIFTY BANK"),
    "PRIVATE BANKS": ("Nifty Private Bank", "NIFTY PRIVATE BANK"),
    "PSU BANKS": ("Nifty PSU Bank", "NIFTY PSU BANK"),
    "FINANCE": ("Nifty Financial Services", "NIFTY FINANCIAL SERVICES"),
    "FINANCIAL SERVICES": ("Nifty Financial Services", "NIFTY FINANCIAL SERVICES"),
    "NBFC": ("Nifty Financial Services", "NIFTY FINANCIAL SERVICES"),
    "INSURANCE": ("Nifty Insurance", "NIFTY INSURANCE"),
    "FAST MOVING CONSUMER GOODS": ("Nifty FMCG", "NIFTY FMCG"),
    "FMCG": ("Nifty FMCG", "NIFTY FMCG"),
    "IT - SOFTWARE": ("Nifty IT", "NIFTY IT"),
    "INFORMATION TECHNOLOGY": ("Nifty IT", "NIFTY IT"),
    "MEDIA": ("Nifty Media", "NIFTY MEDIA"),
    "MEDIA ENTERTAINMENT AND PUBLICATION": ("Nifty Media", "NIFTY MEDIA"),
    "METALS AND MINING": ("Nifty Metal", "NIFTY METAL"),
    "METALS & MINING": ("Nifty Metal", "NIFTY METAL"),
    "PHARMACEUTICALS": ("Nifty Pharma", "NIFTY PHARMA"),
    "PHARMACEUTICALS AND BIOTECHNOLOGY": ("Nifty Pharma", "NIFTY PHARMA"),
    "REALTY": ("Nifty Realty", "NIFTY REALTY"),
    "CONSUMER DURABLES": ("Nifty Consumer Durables", "NIFTY CONSUMER DURABLES"),
    "OIL GAS AND CONSUMABLE FUELS": ("Nifty Oil and Gas", "NIFTY OIL & GAS"),
    "OIL, GAS AND CONSUMABLE FUELS": ("Nifty Oil and Gas", "NIFTY OIL & GAS"),
    "HEALTHCARE": ("Nifty Healthcare", "NIFTY HEALTHCARE"),
    "CAPITAL GOODS": ("Nifty Capital Goods", "NIFTY CAPITAL GOODS"),
    "CHEMICALS": ("Nifty Chemicals", "NIFTY CHEMICALS"),
    "CHEMICALS AND PETROCHEMICALS": ("Nifty Chemicals", "NIFTY CHEMICALS"),
    "POWER": ("Nifty Power", "NIFTY POWER"),
    "TELECOMMUNICATION": ("Nifty Telecommunications", "NIFTY TELECOMMUNICATIONS"),
    "TELECOMMUNICATIONS": ("Nifty Telecommunications", "NIFTY TELECOMMUNICATIONS"),
    "CONSUMER SERVICES": ("Nifty Consumer Services", "NIFTY CONSUMER SERVICES"),
    # NSE official Basic Industry labels that map directly to tracked sectors.
    "RETAILING": ("Nifty Consumer Services", "NIFTY CONSUMER SERVICES"),
    # Official NSE Indices classification structure places these Basic Industries
    # under the named sectors; use the matching tracked Nifty sector benchmark.
    "OTHER AGRICULTURAL PRODUCTS": ("Nifty FMCG", "NIFTY FMCG"),
    "CERAMICS": ("Nifty Consumer Durables", "NIFTY CONSUMER DURABLES"),
    "GRANITES & MARBLES": ("Nifty Consumer Durables", "NIFTY CONSUMER DURABLES"),
    "GRANITES AND MARBLES": ("Nifty Consumer Durables", "NIFTY CONSUMER DURABLES"),
}


def _download_nifty500_industries(session: requests.Session) -> dict[str, str]:
    """Read official Nifty 500 Symbol/Industry classification; reject HTML/bad schemas."""
    try:
        response = session.get(NIFTY500_CONSTITUENTS_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        content = response.content or b""
        if not content or b"<html" in content[:1500].lower() or b"<!doctype html" in content[:1500].lower():
            print("[SECTOR] Nifty 500 industry fallback unavailable: non-CSV response")
            return {}
        frame = pd.read_csv(BytesIO(content))
        cols = {str(c).strip().casefold(): c for c in frame.columns}
        symbol_col = next((cols[k] for k in ("symbol", "ticker", "ticker symbol") if k in cols), None)
        industry_col = next((cols[k] for k in ("industry", "basic industry") if k in cols), None)
        if symbol_col is None or industry_col is None:
            print(f"[SECTOR] Nifty 500 industry fallback schema missing Symbol/Industry: {list(frame.columns)}")
            return {}
        result = {}
        for _, row in frame[[symbol_col, industry_col]].dropna().iterrows():
            symbol = _clean_symbol(row[symbol_col])
            industry = _normalise_name(row[industry_col])
            if symbol and industry:
                result[symbol] = industry
        print(f"[SECTOR] Official Nifty 500 industry classifications loaded: {len(result)} symbols")
        return result
    except Exception as exc:
        print(f"[SECTOR] Nifty 500 industry fallback unavailable: {exc}")
        return {}


# Official NSE list of securities available for trading in ETF segment.
# ETFs are not ordinary operating companies and must not receive a company-sector
# mapping from the quote/industry fallback. Their underlying index is handled
# separately only when a verified scheme-to-index mapping is available.
NSE_ETF_SECURITIES_URL = "https://nsearchives.nseindia.com/content/equities/eq_etfseclist.csv"

# Reviewed ETF scheme-to-benchmark evidence. Never infer an ETF benchmark from
# its ticker alone. Only ETFs whose verified underlying benchmark is one of the
# tracked Nifty sector indices may be mapped into sector strength.
VERIFIED_ETF_UNDERLYING_INDEX = {
    "BANKADD": {
        "sector": "Nifty Bank",
        "index_symbol": "NIFTY BANK",
        "status": "ETF_UNDERLYING_INDEX_VERIFIED",
        "reason": (
            "Verified DSP Nifty Bank ETF; official DSP scheme page states the underlying index is "
            "Nifty Bank Index. Official source: "
            "https://www.dspim.com/invest/mutual-fund-schemes/exchange-traded-funds/nifty-bank-etf/dsnbe-direct-growth"
        ),
    },
    "PSUBANKADD": {
        "sector": "Nifty PSU Bank",
        "index_symbol": "NIFTY PSU BANK",
        "status": "ETF_UNDERLYING_INDEX_VERIFIED",
        "reason": (
            "Verified DSP Nifty PSU Bank ETF; the official DSP scheme page states the scheme tracks "
            "the Nifty PSU Bank Index and identifies NSE symbol PSUBANKADD. Official source: "
            "https://www.dspim.com/invest/mutual-fund-schemes/exchange-traded-funds/nifty-psu-bank-etf/dpsub-direct-growth"
        ),
    },
    "TECH": {
        "sector": "Nifty IT",
        "index_symbol": "NIFTY IT",
        "status": "ETF_UNDERLYING_INDEX_VERIFIED",
        "reason": (
            "Verified Aditya Birla Sun Life Nifty IT ETF; the official AMC scheme page identifies "
            "NSE symbol TECH and states that the scheme tracks Nifty IT TRI. Official source: "
            "https://mutualfund.adityabirlacapital.com/empower/Passive-ETFs/Nifty-IT-ETF.html"
        ),
    },
}
VERIFIED_ETF_UNSUPPORTED = {
    "INSUREIETF": (
        "ETF_UNDERLYING_INDEX_UNSUPPORTED",
        "Official NSE listing identifies ICICI Prudential BSE Insurance ETF; this module tracks "
        "Nifty sector indices and has no verified BSE Insurance index history. Do not map it to "
        "Nifty Insurance. Official NSE quote: "
        "https://www.nseindia.com/get-quote/equity/INSUREIETF/ICICI-Prudential-BSE-Insurance-ETF",
    ),
    "AONELIQUID": (
        "ETF_UNDERLYING_INDEX_UNSUPPORTED",
        "Official Angel One AMC product note identifies Angel One Nifty 1D Rate Liquid ETF and "
        "Nifty 1D Rate Index as its benchmark. This is a liquid/rate benchmark, not a tracked Nifty "
        "sector index, so it must not be mapped to a company sector. Official source: "
        "https://cms.angelonemf.com/amc-cms/wp-content/uploads/formidable/23/Product-Note-Angel-One-Nifty-1D-Rate-Liquid-ETF-Growth-Dec-2025.pdf",
    ),
    "HDFCBSE500": (
        "ETF_UNDERLYING_INDEX_UNSUPPORTED",
        "Official HDFC AMC scheme page identifies HDFCBSE500 as tracking the BSE 500 Index (TRI). "
        "This module stores Nifty sector index history and has no BSE 500 index history, so do not "
        "assign this ETF to an arbitrary Nifty sector. Official source: "
        "https://www.hdfcfund.com/explore/mutual-funds/hdfc-bse-500-etf/regular",
    ),
    "VALUE": (
        "ETF_UNDERLYING_INDEX_UNSUPPORTED",
        "Official Mirae Asset scheme documents identify VALUE as Mirae Asset Nifty 500 Value 50 ETF, "
        "tracking the Nifty 500 Value 50 Total Return Index. This is a broad-market factor index, "
        "not one of this module's tracked Nifty sector indices; do not assign it to a sector. "
        "Official source: "
        "https://nsearchives.nseindia.com/corporate/MIRAEAMC_10042026161745_HalfYearlyPortfolio.pdf",
    ),
    "DIVIDEND": (
        "ETF_UNDERLYING_INDEX_UNSUPPORTED",
        "Official Mirae Asset portfolio statement identifies DIVIDEND as Mirae Asset BSE 500 Dividend "
        "Leaders 50 ETF, tracking the BSE 500 Dividend Leaders 50 Total Return Index. This module "
        "stores Nifty sector index history and has no matching BSE sector benchmark history; do not "
        "assign it to an arbitrary Nifty sector. Official source: "
        "https://nsearchives.nseindia.com/corporate/MIRAEAMC_09042026145504_Monthlyportfolio.pdf",
    ),
}


def _download_official_etf_symbols(session: requests.Session) -> set[str]:
    """Return symbols in NSE's official ETF securities CSV; fail closed on bad data."""
    try:
        response = session.get(
            NSE_ETF_SECURITIES_URL,
            headers={**HEADERS, "Referer": "https://www.nseindia.com/static/market-data/securities-available-for-trading"},
            timeout=20,
        )
        response.raise_for_status()
        content = response.content or b""
        if not content or b"<html" in content[:1500].lower() or b"<!doctype html" in content[:1500].lower():
            print("[SECTOR] Official ETF list unavailable: non-CSV response")
            return set()
        frame = pd.read_csv(BytesIO(content))
        cols = {str(c).strip().casefold(): c for c in frame.columns}
        symbol_col = next((cols[k] for k in ("symbol", "trading symbol", "ticker", "ticker symbol") if k in cols), None)
        if symbol_col is None:
            print(f"[SECTOR] Official ETF list schema missing Symbol column: {list(frame.columns)}")
            return set()
        symbols = {_clean_symbol(value) for value in frame[symbol_col].tolist()} - {""}
        print(f"[SECTOR] Official NSE ETF symbols loaded: {len(symbols)}")
        return symbols
    except Exception as exc:
        print(f"[SECTOR] Official ETF list unavailable: {exc}")
        return set()


NSE_QUOTE_URL = "https://www.nseindia.com/api/quote-equity"

# Keys are normalized NSE Indices classification "sector" labels.
# Values are the exact Sector labels used by SECTOR_INDICES / sector_history.
OFFICIAL_SECTOR_TO_TRACKED_INDEX = {
    "AUTO": ("Nifty Auto", "NIFTY AUTO"),
    "AUTOMOBILES": ("Nifty Auto", "NIFTY AUTO"),
    "BANKS": ("Nifty Bank", "NIFTY BANK"),
    "FINANCIAL SERVICES": ("Nifty Financial Services", "NIFTY FINANCIAL SERVICES"),
    "CONSUMER DURABLES": ("Nifty Consumer Durables", "NIFTY CONSUMER DURABLES"),
    "FAST MOVING CONSUMER GOODS": ("Nifty FMCG", "NIFTY FMCG"),
    "FMCG": ("Nifty FMCG", "NIFTY FMCG"),
    "INFORMATION TECHNOLOGY": ("Nifty IT", "NIFTY IT"),
    "IT": ("Nifty IT", "NIFTY IT"),
    "MEDIA": ("Nifty Media", "NIFTY MEDIA"),
    "MEDIA ENTERTAINMENT AND PUBLICATION": ("Nifty Media", "NIFTY MEDIA"),
    "METALS AND MINING": ("Nifty Metal", "NIFTY METAL"),
    "METAL": ("Nifty Metal", "NIFTY METAL"),
    "PHARMACEUTICALS": ("Nifty Pharma", "NIFTY PHARMA"),
    "PHARMACEUTICALS AND BIOTECHNOLOGY": ("Nifty Pharma", "NIFTY PHARMA"),
    "HEALTHCARE": ("Nifty Healthcare", "NIFTY HEALTHCARE"),
    "PSU BANKS": ("Nifty PSU Bank", "NIFTY PSU BANK"),
    "REALTY": ("Nifty Realty", "NIFTY REALTY"),
    "CONSUMER SERVICES": ("Nifty Consumer Services", "NIFTY CONSUMER SERVICES"),
    "TELECOMMUNICATION": ("Nifty Telecommunications", "NIFTY TELECOMMUNICATIONS"),
    "TELECOMMUNICATIONS": ("Nifty Telecommunications", "NIFTY TELECOMMUNICATIONS"),
    "CAPITAL GOODS": ("Nifty Capital Goods", "NIFTY CAPITAL GOODS"),
    "CHEMICALS": ("Nifty Chemicals", "NIFTY CHEMICALS"),
    "POWER": ("Nifty Power", "NIFTY POWER"),
    "OIL GAS AND CONSUMABLE FUELS": ("Nifty Oil and Gas", "NIFTY OIL & GAS"),
    "OIL AND GAS": ("Nifty Oil and Gas", "NIFTY OIL & GAS"),
    "INSURANCE": ("Nifty Insurance", "NIFTY INSURANCE"),
    "PRIVATE BANKS": ("Nifty Private Bank", "NIFTY PRIVATE BANK"),
}


def _warm_nse_session(session: requests.Session) -> None:
    """Warm NSE's own browser session before using its JSON quote endpoint."""
    for url in (
        "https://www.nseindia.com/",
        "https://www.nseindia.com/market-data/live-equity-market",
    ):
        try:
            response = session.get(url, headers=NSE_HEADERS, timeout=12)
            print(f"[SECTOR] NSE session warm-up: {url} -> HTTP {response.status_code}")
            if response.status_code == 200:
                # One successful page response is sufficient to seed NSE cookies.
                break
        except Exception as exc:
            print(f"[SECTOR] NSE session warm-up failed for {url}: {exc}")


class _NSEVisibleTextParser(HTMLParser):
    """Extract visible text from the official NSE quote page without extra deps."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join((data or "").split())
        if value:
            self.parts.append(value)


def _nse_quote_page_basic_industry(session: requests.Session, symbol: str) -> str:
    """Fetch Basic Industry from an official NSE quote page using supported routes.

    NSE's old singular URL /get-quote/equity/SYMBOL returns 404 for symbols
    whose canonical quote page includes a company slug. Try the current plural
    query route first, then the canonical symbol/company route for the targeted
    symbols. Only an explicit Basic Industry label is returned.
    """
    headers = {
        **NSE_HEADERS,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.nseindia.com/market-data/live-equity-market",
    }
    urls: list[tuple[str, dict[str, str] | None]] = [
        ("https://www.nseindia.com/get-quotes/equity", {"symbol": symbol}),
    ]
    quote_slugs = {
        "SPENCERS": "Spencer's-Retail-Limited",
        "BEDMUTHA": "Bedmutha-Industries-Limited",
        "MODINATUR": "Modi-Naturals-Limited",
        "JKIPL": "Jinkushal-Industries-Limited",
        "AROGRANITE": "Aro-Granite-Industries-Limited",
    }
    slug = quote_slugs.get(_clean_symbol(symbol))
    if slug:
        urls.append((f"https://www.nseindia.com/get-quote/equity/{_clean_symbol(symbol)}/{slug}", None))

    for url, params in urls:
        try:
            response = session.get(url, params=params, headers=headers, timeout=18)
            print(f"[SECTOR] NSE quote page {symbol}: HTTP {response.status_code} route={url}")
            if response.status_code != 200:
                continue
            body = response.text or ""
            if not body:
                continue
            parser = _NSEVisibleTextParser()
            parser.feed(body)
            text = unescape(" ".join(parser.parts))
            match = re.search(
                r"\bBasic Industry\s+(.+?)\s+(?:Corporate Announcements|Trading Window|Annual Reports|Financial Result|Peer Comparison)\b",
                text,
                flags=re.I,
            )
            if not match:
                print(f"[SECTOR] NSE quote page {symbol}: Basic Industry label not found on this route")
                continue
            value = " ".join(match.group(1).split()).strip(" :-")
            if not value or value.casefold() in {"-", "na", "n/a", "undefined"}:
                continue
            print(f"[SECTOR] NSE official Basic Industry {symbol}: {value}")
            return value
        except Exception as exc:
            print(f"[SECTOR] NSE quote page fallback unavailable for {symbol}: {type(exc).__name__}: {exc}")
    return ""


def _nse_quote_industry_classification(session: requests.Session, symbol: str) -> dict[str, str]:
    """Fetch official NSE industryInfo, falling back to NSE's rendered quote page."""
    headers = {
        **NSE_HEADERS,
        "Referer": f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}",
    }
    last_error = "no response"
    for attempt in range(1, 3):
        try:
            response = session.get(
                NSE_QUOTE_URL,
                params={"symbol": symbol},
                headers=headers,
                timeout=18,
            )
            if response.status_code == 200:
                payload = response.json()
                info = payload.get("industryInfo") or {}
                if isinstance(info, dict):
                    return {
                        "macro": str(info.get("macro") or "").strip(),
                        "sector": str(info.get("sector") or "").strip(),
                        "industry": str(info.get("industry") or "").strip(),
                        "basicIndustry": str(info.get("basicIndustry") or "").strip(),
                    }
                last_error = "industryInfo is not an object"
                break
            last_error = f"HTTP {response.status_code}"
            print(f"[SECTOR] NSE quote {symbol}: {last_error} (attempt {attempt}/2)")
            if response.status_code not in {403, 429, 500, 502, 503, 504}:
                break
            time.sleep(0.8 * attempt)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"[SECTOR] NSE quote {symbol} request failed (attempt {attempt}/2): {last_error}")
            time.sleep(0.5 * attempt)

    basic_industry = _nse_quote_page_basic_industry(session, symbol)
    if basic_industry:
        return {"macro": "", "sector": "", "industry": "", "basicIndustry": basic_industry}
    raise requests.RequestException(
        f"NSE quote API failed ({last_error}) and official quote-page fallback had no Basic Industry"
    )


def _targeted_shortlist_mappings(
    candidate_symbols: list[str],
    existing_mapping_by_symbol: dict[str, dict[str, str]],
    nifty500_industries: dict[str, str],
    asof: pd.Timestamp,
    nse_classifications: dict[str, dict[str, str]] | None = None,
    etf_symbols: set[str] | None = None,
) -> list[dict[str, str]]:
    """Map shortlist symbols using official index membership, NSE quote sector,
    or an exact official Nifty 500 Industry-to-benchmark rule.

    No sector is inferred from a ticker/company name. Unknown labels remain
    WAIT_FOR_DATA and never become PASS.
    """
    nse_classifications = nse_classifications or {}
    etf_symbols = {_clean_symbol(symbol) for symbol in (etf_symbols or set())} - {""}
    audit_rows: list[dict[str, str]] = []
    mapping_rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw_symbol in candidate_symbols:
        symbol = _clean_symbol(raw_symbol)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)

        existing = existing_mapping_by_symbol.get(symbol)
        industry = nifty500_industries.get(symbol, "")
        nse_info = nse_classifications.get(symbol, {})
        macro = _normalise_name(nse_info.get("macro", ""))
        nse_sector = _normalise_name(nse_info.get("sector", ""))
        nse_industry = _normalise_name(nse_info.get("industry", ""))
        basic_industry = _normalise_name(nse_info.get("basicIndustry", ""))

        # ETFs need scheme/underlying-index evidence, not company-industry mapping.
        if symbol in etf_symbols and symbol in VERIFIED_ETF_UNDERLYING_INDEX:
            reviewed = VERIFIED_ETF_UNDERLYING_INDEX[symbol]
            sector, index_symbol = reviewed["sector"], reviewed["index_symbol"]
            status, reason = reviewed["status"], reviewed["reason"]
            mapping_rows.append({
                "TckrSymb": symbol, "Sector": sector,
                "SectorIndexSymbol": index_symbol,
            })
            print(f"[SECTOR] ETF benchmark verified {symbol}: {sector} ({index_symbol})")
        elif symbol in etf_symbols and symbol in VERIFIED_ETF_UNSUPPORTED:
            status, reason = VERIFIED_ETF_UNSUPPORTED[symbol]
            sector, index_symbol = "", ""
            print(f"[SECTOR] ETF benchmark unsupported {symbol}: {reason}")
        elif symbol in etf_symbols:
            sector, index_symbol = "", ""
            status = "ETF_UNDERLYING_INDEX_REQUIRED"
            reason = (
                "Symbol appears in the official NSE ETF securities list; ordinary company-sector "
                "mapping skipped until a verified scheme-to-underlying-index mapping is available"
            )
        # Official tracked-index membership is the strongest mapping evidence for equities.
        elif existing:
            sector = existing.get("Sector", "")
            index_symbol = existing.get("SectorIndexSymbol", "")
            status = "INDEX_CONSTITUENT"
            reason = "Mapped from official tracked-sector index constituent CSV"
        else:
            official_sector_mapping = OFFICIAL_SECTOR_TO_TRACKED_INDEX.get(nse_sector)

            # Use exact official classification labels in a conservative order.
            # The previous implementation ignored NSE's own `industry` and
            # `basicIndustry` fields and only checked the Nifty 500 `Industry`
            # value. That left valid official classifications unmapped whenever
            # the symbol was outside Nifty 500 or the Nifty 500 file was stale.
            industry_mapping = None
            industry_mapping_source = ""
            for source_name, source_value in (
                ("NSE industry", nse_industry),
                ("NSE basicIndustry", basic_industry),
                ("Nifty 500 Industry", industry),
            ):
                candidate_mapping = INDUSTRY_TO_TRACKED_INDEX.get(source_value)
                if candidate_mapping:
                    industry_mapping = candidate_mapping
                    industry_mapping_source = source_name
                    break

            if official_sector_mapping:
                sector, index_symbol = official_sector_mapping
                status = "OFFICIAL_NSE_SECTOR_MAPPED"
                reason = (
                    f"Official NSE quote sector='{nse_sector}' mapped to tracked benchmark; "
                    f"macro='{macro}', industry='{nse_industry}', basicIndustry='{basic_industry}'"
                )
                mapping_rows.append({
                    "TckrSymb": symbol, "Sector": sector,
                    "SectorIndexSymbol": index_symbol,
                })
                print(f"[SECTOR] Candidate classification {symbol}: {sector} via official NSE sector='{nse_sector}'")
            elif industry_mapping:
                sector, index_symbol = industry_mapping
                status = {
                    "NSE industry": "OFFICIAL_NSE_INDUSTRY_MAPPED",
                    "NSE basicIndustry": "OFFICIAL_NSE_BASIC_INDUSTRY_MAPPED",
                    "Nifty 500 Industry": "OFFICIAL_NIFTY500_INDUSTRY_MAPPED",
                }.get(industry_mapping_source, "OFFICIAL_INDUSTRY_MAPPED")
                source_value = {
                    "NSE industry": nse_industry,
                    "NSE basicIndustry": basic_industry,
                    "Nifty 500 Industry": industry,
                }.get(industry_mapping_source, industry)
                reason = (
                    f"Official {industry_mapping_source}='{source_value}' mapped by exact taxonomy "
                    "rule to tracked benchmark"
                )
                mapping_rows.append({
                    "TckrSymb": symbol, "Sector": sector,
                    "SectorIndexSymbol": index_symbol,
                })
                print(f"[SECTOR] Candidate classification {symbol}: {sector} via {industry_mapping_source}='{source_value}'")
            else:
                sector, index_symbol = "", ""
                status = "WAIT_FOR_DATA"
                labels = [
                    label for label in (
                        f"NSE sector='{nse_sector}'" if nse_sector else "",
                        f"NSE industry='{nse_industry}'" if nse_industry else "",
                        f"NSE basicIndustry='{basic_industry}'" if basic_industry else "",
                        f"Nifty 500 Industry='{industry}'" if industry else "",
                    ) if label
                ]
                if labels:
                    reason = (
                        "Official classification found but no exact tracked benchmark mapping: "
                        + "; ".join(labels)
                        + "; no sector guessed"
                    )
                else:
                    reason = (
                        "Not found in refreshed tracked-sector constituent feeds, official NSE "
                        "quote classification, or official Nifty 500 classification; no sector guessed"
                    )
                print(f"[SECTOR] Candidate classification {symbol}: WAIT_FOR_DATA ({reason})")

        # Preserve the official NSE labels in the audit even when Nifty 500
        # Industry was the source that supplied the benchmark mapping.
        audit_rows.append({
            "Date": asof.strftime("%Y-%m-%d"),
            "TckrSymb": symbol,
            "MappingStatus": status,
            "NSEMacro": macro,
            "NSESector": nse_sector,
            "NSEIndustry": nse_industry or industry,
            "NSEBasicIndustry": basic_industry,
            "MappedSector": sector,
            "SectorIndexSymbol": index_symbol,
            "Reason": reason,
        })

    report_dir = Path("data") / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    audit_path = report_dir / f"sector_candidate_mapping_{asof.strftime('%Y%m%d')}.csv"
    pd.DataFrame(audit_rows, columns=[
        "Date", "TckrSymb", "MappingStatus", "NSEMacro", "NSESector",
        "NSEIndustry", "NSEBasicIndustry", "MappedSector", "SectorIndexSymbol", "Reason",
    ]).to_csv(audit_path, index=False)
    print(f"[SECTOR] Candidate mapping audit: {audit_path} ({len(audit_rows)} symbols)")
    print(
        "[SECTOR] Candidate sector mapping statuses: "
        f"{pd.Series([r['MappingStatus'] for r in audit_rows]).value_counts().to_dict() if audit_rows else {}}"
    )
    return mapping_rows



def _remove_stale_unverified_candidate_mappings(
    old_map: pd.DataFrame,
    audit_path: Path,
    fresh_symbols: set[str] | None = None,
) -> pd.DataFrame:
    """Drop cached mappings for shortlisted symbols whose current audit is unresolved.

    Cached sector rows remain useful for non-candidate symbols. But when a current
    shortlist audit explicitly says WAIT_FOR_DATA or says an ETF benchmark is
    unsupported/required, an older cached mapping must not silently override it.
    Fresh official constituent/targeted mappings always take precedence.
    """
    if old_map.empty or not audit_path.exists():
        return old_map
    try:
        audit = pd.read_csv(audit_path)
    except Exception as exc:
        print(f"[SECTOR] Could not read candidate mapping audit for cache reconciliation: {exc}")
        return old_map
    required = {"TckrSymb", "MappingStatus"}
    if not required.issubset(audit.columns):
        print("[SECTOR] Candidate mapping audit missing required columns; cached map left unchanged")
        return old_map
    unresolved_statuses = {
        "WAIT_FOR_DATA",
        "ETF_UNDERLYING_INDEX_UNSUPPORTED",
        "ETF_UNDERLYING_INDEX_REQUIRED",
    }
    unresolved = {
        _clean_symbol(row.TckrSymb)
        for row in audit.itertuples(index=False)
        if str(row.MappingStatus).strip().upper() in unresolved_statuses
    } - {""}
    fresh_symbols = {_clean_symbol(symbol) for symbol in (fresh_symbols or set())} - {""}
    stale_to_drop = unresolved - fresh_symbols
    if not stale_to_drop:
        return old_map
    before = len(old_map)
    filtered = old_map[~old_map["TckrSymb"].map(_clean_symbol).isin(stale_to_drop)].copy()
    removed = before - len(filtered)
    if removed:
        print(
            "[SECTOR] Removed stale cached candidate mappings after current audit: "
            f"symbols={sorted(stale_to_drop)}, rows_removed={removed}"
        )
    return filtered


def refresh_sector_inputs(asof_date: Any, force: bool = False, candidate_symbols: list[str] | None = None) -> dict[str, Any]:
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

    # Targeted shortlist mapping: tracked-index membership first, then official
    # NSE quote sector classification, then the exact official Nifty 500 Industry
    # taxonomy fallback. NSE quote data is requested only when the Nifty 500
    # label cannot already map to a tracked benchmark.
    candidate_symbols = candidate_symbols or []
    nifty500_industries = _download_nifty500_industries(session) if candidate_symbols else {}
    etf_symbols = _download_official_etf_symbols(session) if candidate_symbols else set()
    existing_mapping_by_symbol = {
        row["TckrSymb"]: row for row in mappings if row.get("TckrSymb")
    }

    nse_classifications: dict[str, dict[str, str]] = {}
    quote_candidates = []
    for raw_symbol in candidate_symbols:
        symbol = _clean_symbol(raw_symbol)
        if not symbol or symbol in existing_mapping_by_symbol or symbol in etf_symbols:
            continue
        if INDUSTRY_TO_TRACKED_INDEX.get(nifty500_industries.get(symbol, "")):
            continue
        quote_candidates.append(symbol)

    if quote_candidates:
        _warm_nse_session(session)
        for symbol in quote_candidates:
            try:
                info = _nse_quote_industry_classification(session, symbol)
                if any(str(value or "").strip() for value in info.values()):
                    nse_classifications[symbol] = info
                else:
                    print(f"[SECTOR] NSE quote classification empty for {symbol}")
            except Exception as exc:
                # A failed quote must not break the refresh or create a guessed mapping.
                print(f"[SECTOR] NSE quote classification unavailable for {symbol}: {exc}")
            time.sleep(0.25)

    targeted_mappings = _targeted_shortlist_mappings(
        candidate_symbols=candidate_symbols,
        existing_mapping_by_symbol=existing_mapping_by_symbol,
        nifty500_industries=nifty500_industries,
        asof=asof,
        nse_classifications=nse_classifications,
        etf_symbols=etf_symbols,
    )
    for row in targeted_mappings:
        symbol = row["TckrSymb"]
        if symbol not in seen_symbols:
            mappings.append(row)
            seen_symbols.add(symbol)

    new_map = pd.DataFrame(mappings, columns=MAP_COLUMNS)
    old_map = pd.DataFrame(columns=MAP_COLUMNS)
    if MAP_PATH.exists():
        try:
            candidate = pd.read_csv(MAP_PATH)
            if set(MAP_COLUMNS).issubset(candidate.columns):
                old_map = candidate[MAP_COLUMNS]
                # A current official ETF-list match overrides stale cached company-sector rows.
                if etf_symbols and not old_map.empty:
                    old_map = old_map[
                        ~old_map["TckrSymb"].map(_clean_symbol).isin(etf_symbols)
                    ]
        except Exception:
            pass
    # Reconcile current candidate audit against the persistent cache. Without this,
    # old sector rows (e.g. a prior SPENCERS/MODINATUR mapping) can survive even
    # when today's official audit explicitly says WAIT_FOR_DATA. Do not remove
    # symbols supported by the current official refresh.
    audit_path = Path("data") / "reports" / f"sector_candidate_mapping_{asof.strftime('%Y%m%d')}.csv"
    old_map = _remove_stale_unverified_candidate_mappings(
        old_map, audit_path, fresh_symbols=set(new_map["TckrSymb"].map(_clean_symbol))
    )

    # Fresh official membership takes precedence; cached rows only fill symbols absent from refresh.
    map_frame = pd.concat([new_map, old_map], ignore_index=True).drop_duplicates(subset=["TckrSymb"], keep="first")
    if not map_frame.empty:
        map_frame = map_frame.sort_values("TckrSymb")
        map_frame.to_csv(MAP_PATH, index=False)
    else:
        print("[SECTOR] No official constituent mappings retrieved; existing map preserved if present")

    new_history_rows, sectors_with_asof_new = _history_from_nse_archive(session, asof)
    # If the daily NSE all-indices archive does not provide exact-date closes,
    # retry through the official Nifty Indices historical-data service. Merge
    # only actual dated closes; never fill missing values synthetically.
    if sectors_with_asof_new < len(SECTOR_INDICES):
        exact_date_text = asof.strftime("%Y-%m-%d")
        archive_exact_sectors = {row["Sector"] for row in new_history_rows if row.get("Date") == exact_date_text}
        missing_sectors = {item[0] for item in SECTOR_INDICES} - archive_exact_sectors
        print(f"[SECTOR] Index-history fallback limited to missing exact-date sectors: {sorted(missing_sectors)}")
        fallback_rows, fallback_exact = _history_from_niftyindices_api(session, asof, sectors_to_fetch=missing_sectors)
        if fallback_rows:
            merged = {(row["Date"], row["Sector"]): row["Close"] for row in new_history_rows}
            for row in fallback_rows:
                merged[(row["Date"], row["Sector"])] = row["Close"]
            new_history_rows = [
                {"Date": date, "Sector": sector, "Close": close}
                for (date, sector), close in merged.items()
            ]
            sectors_with_asof_new = len({row["Sector"] for row in new_history_rows if row["Date"] == asof.strftime("%Y-%m-%d")})
            print(f"[SECTOR] Official Nifty Indices fallback exact-date sectors={sectors_with_asof_new}/{len(SECTOR_INDICES)} (fallback reported {fallback_exact})")
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
    targeted_count = len(targeted_mappings)
    print(f"[SECTOR] Mapping rows: {len(map_frame)}; constituent feeds: {successful_maps}/{len(SECTOR_INDICES)}; targeted shortlist mappings added: {targeted_count}")
    print(f"[SECTOR] History rows: {len(history_frame)}; official NSE exact-date sector closes: {sectors_with_asof}; fresh archive sectors: {history_success}")
    if sectors_with_asof == 0:
        print("[SECTOR] No exact-date sector history available; SectorStrengthStatus remains WAIT_FOR_DATA")
    return {
        "mapping_rows": len(map_frame),
        "history_rows": len(history_frame),
        "sectors_with_asof": sectors_with_asof,
        "fresh_archive_sectors": history_success,
        "constituent_feeds": successful_maps,
        "targeted_shortlist_mappings": len(targeted_mappings),
        "reused": False,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Refresh V8 sector inputs")
    parser.add_argument("--date", required=True, help="EOD date, YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Force refresh cached inputs")
    args = parser.parse_args()
    print(json.dumps(refresh_sector_inputs(args.date, force=args.force), default=str))
