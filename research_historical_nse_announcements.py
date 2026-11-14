"""Research-only historical NSE corporate-announcement backfill.

Uses the official NSE issuer/date-filtered corporate-announcements endpoint.
Only exact-symbol, date-valid records are accepted. This is not a complete
historical media-news archive and does not score catalysts or alter production.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

UNIVERSE_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
API_URL = "https://www.nseindia.com/api/corporate-announcements"
LANDING_URL = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
ROOT = Path("data/research")
LEDGER = ROOT / "historical_nse_announcements.csv"
DIAGNOSTICS = ROOT / "historical_nse_announcement_diagnostics.csv"
MANIFEST = ROOT / "historical_nse_announcement_manifest.json"
COLUMNS = [
    "Symbol", "CompanyName", "PublishedAtUTC", "PublishedAtIST", "Headline",
    "Description", "AnnouncementType", "EventID", "AttachmentURL",
    "Source", "SourceURL", "RetrievedAtUTC", "IdentityStatus", "DateStatus",
]
DIAG_COLUMNS = [
    "Symbol", "Status", "HTTPStatus", "RecordCount", "AcceptedCount",
    "RejectedSymbolCount", "RejectedDateCount", "Error", "AttemptedAtUTC",
]


def load_universe() -> pd.DataFrame:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "text/csv,*/*", "Referer": "https://www.nseindia.com/",
    })
    response = session.get(UNIVERSE_URL, timeout=(15, 40))
    response.raise_for_status()
    raw = pd.read_csv(io.BytesIO(response.content), dtype=str).fillna("")
    symbol_col = next((c for c in raw.columns if c.strip().upper() == "SYMBOL"), None)
    name_col = next((c for c in raw.columns if "NAME OF COMPANY" in c.strip().upper()), None)
    if not symbol_col:
        raise RuntimeError(f"NSE equity master missing SYMBOL: {list(raw.columns)}")
    out = pd.DataFrame({
        "Symbol": raw[symbol_col].str.strip().str.upper(),
        "CompanyName": raw[name_col].str.strip() if name_col else "",
    })
    out = out[out.Symbol.ne("") & ~out.Symbol.isin({"NAN", "NONE"})]
    return out.drop_duplicates("Symbol").sort_values("Symbol").reset_index(drop=True)


def parse_stamp(value):
    if not str(value or "").strip():
        return None
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            return None
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("Asia/Kolkata")
        return stamp.tz_convert("UTC")
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_symbol(session: requests.Session, symbol: str, start: pd.Timestamp, end: pd.Timestamp):
    params = {
        "index": "equities", "symbol": symbol,
        "from_date": start.strftime("%d-%m-%Y"),
        "to_date": end.strftime("%d-%m-%Y"),
    }
    response = session.get(API_URL, params=params, timeout=(15, 35))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"Unexpected NSE payload type: {type(payload).__name__}")
    return payload, response.status_code


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    universe = load_universe()
    batch_size = max(1, min(50, int(os.getenv("ANNOUNCEMENT_BATCH_SIZE", "15"))))
    offset = max(0, int(os.getenv("ANNOUNCEMENT_BATCH_OFFSET", "0")))
    start = pd.Timestamp(os.getenv("ANNOUNCEMENT_START_DATE", "2025-11-14")).normalize()
    end_value = os.getenv("ANNOUNCEMENT_END_DATE", "").strip() or pd.Timestamp.now(tz="Asia/Kolkata").date().isoformat()
    end = pd.Timestamp(end_value).normalize()
    if end < start:
        raise ValueError("ANNOUNCEMENT_END_DATE must be on/after ANNOUNCEMENT_START_DATE")

    old = pd.read_csv(LEDGER, dtype=str).fillna("") if LEDGER.exists() else pd.DataFrame(columns=COLUMNS)
    old_diag = pd.read_csv(DIAGNOSTICS, dtype=str).fillna("") if DIAGNOSTICS.exists() else pd.DataFrame(columns=DIAG_COLUMNS)
    completed = set(old.loc[old.get("IdentityStatus", pd.Series(dtype=str)).eq("EXACT_SYMBOL"), "Symbol"].astype(str).str.upper()) if not old.empty else set()
    # Also remember symbols that were queried successfully but had zero announcements.
    failed_recent = set()
    retry_cooldown_hours = max(1, int(os.getenv("ANNOUNCEMENT_FAILED_RETRY_HOURS", "24")))
    if not old_diag.empty and {"Symbol", "Status"}.issubset(old_diag.columns):
        completed.update(old_diag.loc[old_diag.Status.isin(["SUCCESS", "SUCCESS_EMPTY"]), "Symbol"].astype(str).str.upper())
        if "AttemptedAtUTC" in old_diag.columns:
            failed = old_diag[old_diag.Status.eq("FAILED")].copy()
            failed["_attempted"] = pd.to_datetime(failed["AttemptedAtUTC"], errors="coerce", utc=True)
            cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=retry_cooldown_hours)
            failed_recent = set(
                failed.loc[failed["_attempted"].ge(cutoff), "Symbol"].astype(str).str.upper()
            )
    # Avoid repeatedly retrying the same failed symbols at the head of the
    # sorted universe; let untouched symbols progress, then retry failures later.
    eligible = universe[
        ~universe.Symbol.isin(completed) & ~universe.Symbol.isin(failed_recent)
    ].reset_index(drop=True)
    batch = eligible.iloc[offset:offset + batch_size]

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*", "Referer": LANDING_URL,
    })
    session.get(LANDING_URL, timeout=(15, 25)).raise_for_status()

    retrieved = datetime.now(timezone.utc).isoformat()
    rows, diagnostics = [], []
    for index, item in enumerate(batch.to_dict("records")):
        symbol, company = item["Symbol"], item["CompanyName"]
        http_status = ""
        try:
            payload, http_status = fetch_symbol(session, symbol, start, end)
            accepted = rejected_symbol = rejected_date = 0
            for record in payload:
                if not isinstance(record, dict):
                    continue
                raw_symbol = str(record.get("symbol", "")).strip().upper()
                if raw_symbol and raw_symbol != symbol:
                    rejected_symbol += 1
                    continue
                raw_date = record.get("an_dt") or record.get("sort_date") or record.get("dt") or ""
                stamp = parse_stamp(raw_date)
                if stamp is None or stamp < start.tz_localize("Asia/Kolkata").tz_convert("UTC") or stamp > (end + pd.Timedelta(days=1)).tz_localize("Asia/Kolkata").tz_convert("UTC"):
                    rejected_date += 1
                    continue
                headline = str(record.get("desc") or record.get("subject") or "").strip()
                description = str(record.get("attchmntText") or record.get("desc") or "").strip()
                attachment = str(record.get("attchmntFile") or "").strip()
                event_id = str(record.get("seq_id") or "").strip()
                if not event_id:
                    seed = "|".join((symbol, stamp.isoformat(), headline, attachment))
                    event_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
                rows.append({
                    "Symbol": symbol, "CompanyName": company,
                    "PublishedAtUTC": stamp.isoformat(),
                    "PublishedAtIST": stamp.tz_convert("Asia/Kolkata").isoformat(),
                    "Headline": headline, "Description": description,
                    "AnnouncementType": str(record.get("an_category") or record.get("category") or record.get("attchmntText") or "").strip()[:500],
                    "EventID": event_id, "AttachmentURL": attachment,
                    "Source": "NSE India", "SourceURL": API_URL,
                    "RetrievedAtUTC": retrieved,
                    "IdentityStatus": "EXACT_SYMBOL" if raw_symbol == symbol else "ENDPOINT_SYMBOL_FILTER_ONLY",
                    "DateStatus": "VALID_IST_NORMALIZED",
                })
                accepted += 1
            status = "SUCCESS" if accepted else "SUCCESS_EMPTY"
            diagnostics.append({
                "Symbol": symbol, "Status": status, "HTTPStatus": http_status,
                "RecordCount": len(payload), "AcceptedCount": accepted,
                "RejectedSymbolCount": rejected_symbol, "RejectedDateCount": rejected_date,
                "Error": "", "AttemptedAtUTC": retrieved,
            })
            print(json.dumps({"symbol": symbol, "status": status, "records": len(payload), "accepted": accepted, "rejected_symbol": rejected_symbol, "rejected_date": rejected_date}))
        except Exception as exc:
            diagnostics.append({
                "Symbol": symbol, "Status": "FAILED", "HTTPStatus": http_status,
                "RecordCount": 0, "AcceptedCount": 0, "RejectedSymbolCount": 0,
                "RejectedDateCount": 0, "Error": f"{type(exc).__name__}: {exc}"[:500],
                "AttemptedAtUTC": retrieved,
            })
            print(json.dumps({"symbol": symbol, "status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}))
        if index + 1 < len(batch):
            time.sleep(0.7)

    combined = pd.concat([old, pd.DataFrame(rows, columns=COLUMNS)], ignore_index=True).fillna("")
    if not combined.empty:
        combined = combined.drop_duplicates(["Symbol", "EventID"], keep="last").sort_values(["Symbol", "PublishedAtUTC"])
    combined.reindex(columns=COLUMNS).to_csv(LEDGER, index=False)
    diag = pd.concat([old_diag, pd.DataFrame(diagnostics, columns=DIAG_COLUMNS)], ignore_index=True).fillna("")
    if not diag.empty:
        diag = diag.drop_duplicates(["Symbol", "AttemptedAtUTC"], keep="last")
    diag.reindex(columns=DIAG_COLUMNS).to_csv(DIAGNOSTICS, index=False)

    success_symbols = set(diag.loc[diag.Status.isin(["SUCCESS", "SUCCESS_EMPTY"]), "Symbol"].astype(str).str.upper()) if not diag.empty else set()
    failed_symbols = sorted(set(universe.Symbol) - success_symbols)
    manifest = {
        "generated_at_utc": retrieved, "universe_source": UNIVERSE_URL,
        "universe_count": int(len(universe)), "start_date_ist": start.date().isoformat(),
        "end_date_ist": end.date().isoformat(), "batch_size": batch_size,
        "batch_offset": offset, "batch_symbols": batch.Symbol.tolist(),
        "symbols_attempted_this_batch": len(batch),
        "symbols_successfully_queried_total": len(success_symbols),
        "symbols_remaining_or_failed": len(failed_symbols),
        "symbols_failed_recently_deferred": len(failed_recent),
        "failed_retry_cooldown_hours": retry_cooldown_hours,
        "announcement_rows_total": int(len(combined)),
        "collection_complete": len(success_symbols) >= len(universe),
        "ledger_path": str(LEDGER), "diagnostics_path": str(DIAGNOSTICS),
        "scope_note": "Official NSE corporate announcements only. This is not a complete third-party/media news archive. SUCCESS_EMPTY means query succeeded with no records, not missing data.",
        "production_files_modified": False, "production_scanner_modified": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("ANNOUNCEMENT_BACKFILL_MANIFEST=" + json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
