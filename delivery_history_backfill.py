"""Backfill NSE Full Bhavcopy (price + delivery) for existing cached price sessions.

Research-only utility. It never downloads price Bhavcopy and never changes scanner
selection. It uses the existing data/bhavcopy filenames to choose the most recent
N official sessions, then fills only missing/invalid delivery cache reports.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

from delivery_filter import BASE_URL, CACHE_DIR, HEADERS, REQUIRED_COLUMNS, validate_delivery_report_date
from nse_trading_calendar import is_trading_session

PRICE_DIR = Path("data/bhavcopy")
OUTPUT_DIR = Path("outputs/delivery_history_backfill")
DEFAULT_TARGET_SESSIONS = 200
REQUEST_INTERVAL_SECONDS = 1.05
MAX_RETRIES = 3


def price_session_dates(price_dir: Path = PRICE_DIR, target_sessions: int = DEFAULT_TARGET_SESSIONS) -> list[date]:
    """Return the latest N unique official sessions already represented in price cache."""
    found: set[date] = set()
    for path in price_dir.glob("bhavcopy_????????.csv"):
        match = re.fullmatch(r"bhavcopy_(\d{8})\.csv", path.name)
        if not match:
            continue
        try:
            day = datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        if is_trading_session(day):
            found.add(day)
    ordered = sorted(found)
    if len(ordered) < target_sessions:
        raise RuntimeError(
            f"Only {len(ordered)} official price-cache sessions are available; "
            f"{target_sessions} are required. Price cache was not downloaded or modified."
        )
    return ordered[-target_sessions:]


def _valid_cached_report(path: Path, expected: date) -> tuple[bool, int, str]:
    if not path.exists() or path.stat().st_size <= 1000:
        return False, 0, ""
    try:
        frame = pd.read_csv(path, low_memory=False)
        frame.columns = [str(c).strip().upper().replace(" ", "_") for c in frame.columns]
        if not REQUIRED_COLUMNS.issubset(frame.columns):
            return False, 0, ""
        validate_delivery_report_date(frame, expected, source=f"Cached {path}")
        valid = frame[
            frame["SERIES"].astype(str).str.strip().str.upper().eq("EQ")
            & pd.to_numeric(frame["DELIV_PER"], errors="coerce").between(0, 100)
        ]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return not valid.empty, len(valid), digest
    except Exception:
        return False, 0, ""


def _download_report(session: requests.Session, day: date, cache_dir: Path = CACHE_DIR) -> tuple[str, int, str, int]:
    token = day.strftime("%d%m%Y")
    path = cache_dir / f"sec_bhavdata_full_{token}.csv"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    valid, rows, digest = _valid_cached_report(path, day)
    if valid:
        return "REUSED_CACHE", rows, digest, path.stat().st_size

    url = BASE_URL.format(date=token)
    last_status = 0
    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, timeout=(15, 40))
            last_status = response.status_code
            if response.status_code == 404:
                return "HTTP_404_NOT_AVAILABLE", 0, "", 0
            if response.status_code in (403, 429) or response.status_code >= 500:
                if attempt + 1 < MAX_RETRIES:
                    time.sleep((2 ** attempt) * 2)
                    continue
                return f"HTTP_{response.status_code}", 0, "", 0
            response.raise_for_status()
            content = response.content
            if not content or len(content) <= 1000 or content.lstrip().lower().startswith((b"<html", b"<!doctype")):
                return "INVALID_OR_HTML_RESPONSE", 0, "", 0
            frame = pd.read_csv(io.BytesIO(content), low_memory=False)
            frame.columns = [str(c).strip().upper().replace(" ", "_") for c in frame.columns]
            if not REQUIRED_COLUMNS.issubset(frame.columns):
                return "REQUIRED_COLUMNS_MISSING", 0, "", 0
            validate_delivery_report_date(frame, day, source=f"Downloaded {url}")
            valid_rows = frame[
                frame["SERIES"].astype(str).str.strip().str.upper().eq("EQ")
                & pd.to_numeric(frame["DELIV_PER"], errors="coerce").between(0, 100)
            ]
            if valid_rows.empty:
                return "NO_VALID_EQ_DELIVERY_ROWS", 0, "", 0
            temp = path.with_suffix(path.suffix + ".tmp")
            temp.write_bytes(content)
            temp.replace(path)
            digest = hashlib.sha256(content).hexdigest()
            return "DOWNLOADED", len(valid_rows), digest, len(content)
        except requests.RequestException as exc:
            if attempt + 1 < MAX_RETRIES:
                time.sleep((2 ** attempt) * 2)
                continue
            return f"REQUEST_ERROR_{type(exc).__name__}", 0, "", 0
        except Exception as exc:
            return f"VALIDATION_ERROR_{type(exc).__name__}", 0, "", 0
        finally:
            # NSE archive requests are deliberately paced to avoid aggressive scraping.
            time.sleep(REQUEST_INTERVAL_SECONDS)
    return f"HTTP_{last_status or 'UNKNOWN'}", 0, "", 0


def run_backfill(
    price_dir: Path = PRICE_DIR,
    cache_dir: Path = CACHE_DIR,
    output_dir: Path = OUTPUT_DIR,
    target_sessions: int = DEFAULT_TARGET_SESSIONS,
) -> dict:
    dates = price_session_dates(price_dir, target_sessions)
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    records = []
    try:
        for index, day in enumerate(dates, start=1):
            status, rows, digest, size = _download_report(session, day, cache_dir)
            record = {
                "SessionDate": day.isoformat(),
                "Status": status,
                "ValidEQDeliveryRows": rows,
                "Bytes": size,
                "SHA256": digest,
            }
            records.append(record)
            print(f"[DELIVERY BACKFILL] {index}/{len(dates)} {day} {status} rows={rows}", flush=True)
    finally:
        session.close()

    coverage = pd.DataFrame(records)
    coverage.to_csv(output_dir / "coverage.csv", index=False)
    valid_count = int(coverage["Status"].isin(["REUSED_CACHE", "DOWNLOADED"]).sum())
    downloaded_count = int(coverage["Status"].eq("DOWNLOADED").sum())
    reused_count = int(coverage["Status"].eq("REUSED_CACHE").sum())
    summary = {
        "RequestedPriceSessions": len(dates),
        "RequestedStartDate": dates[0].isoformat(),
        "RequestedEndDate": dates[-1].isoformat(),
        "ValidDeliveryReports": valid_count,
        "Downloaded": downloaded_count,
        "ReusedCache": reused_count,
        "MissingOrRejected": len(dates) - valid_count,
        "PriceCacheModified": False,
        "DeliveryCacheDirectory": str(cache_dir),
        "Status": "COMPLETE" if valid_count == len(dates) else "PARTIAL_DELIVERY_HISTORY",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("[DELIVERY BACKFILL SUMMARY] " + json.dumps(summary, sort_keys=True), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=DEFAULT_TARGET_SESSIONS)
    args = parser.parse_args()
    if args.sessions < 5:
        parser.error("--sessions must be at least 5")
    run_backfill(target_sessions=args.sessions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
