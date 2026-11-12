"""Backfill NSE Delivery reports for the latest sessions in the existing Bhavcopy cache.

This utility never downloads or modifies price Bhavcopy. It validates each cached
price file's internal EOD date, then fetches only missing/invalid official Delivery
reports for those exact sessions.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from delivery_filter import BASE_URL, CACHE_DIR, HEADERS, REQUIRED_COLUMNS, validate_delivery_report_date
from nse_trading_calendar import CalendarCoverageError, is_trading_session
from volume_gainer import validate_bhavcopy_date

PRICE_DIR = Path("data/bhavcopy")
OUTPUT_DIR = Path("outputs/delivery_history_backfill")
DEFAULT_TARGET_SESSIONS = 200
REQUEST_INTERVAL_SECONDS = 1.05
MAX_RETRIES = 3


def price_session_dates(price_dir: Path = PRICE_DIR, target_sessions: int = DEFAULT_TARGET_SESSIONS) -> list[date]:
    """Return the latest N consecutive official sessions with valid cached Bhavcopy files."""
    if target_sessions < 1:
        raise ValueError("target_sessions must be at least 1")
    found: dict[date, Path] = {}
    for path in price_dir.glob("bhavcopy_????????.csv"):
        match = re.fullmatch(r"bhavcopy_(\d{8})\.csv", path.name)
        if not match:
            continue
        try:
            day = datetime.strptime(match.group(1), "%Y%m%d").date()
            if not is_trading_session(day):
                continue
            frame = pd.read_csv(path, low_memory=False)
            validate_bhavcopy_date(frame, day, source=f"Delivery backfill price cache {path}")
            found[day] = path
        except CalendarCoverageError:
            raise
        except Exception as exc:
            print(f"[DELIVERY BACKFILL] IGNORE_INVALID_PRICE_CACHE={path.name} reason={type(exc).__name__}")

    if not found:
        raise RuntimeError("No internally validated official price-cache sessions are available.")
    latest = max(found)
    expected: list[date] = []
    cursor = latest
    calendar_days_scanned = 0
    while len(expected) < target_sessions and calendar_days_scanned <= target_sessions * 2 + 30:
        if is_trading_session(cursor):
            expected.append(cursor)
        cursor -= timedelta(days=1)
        calendar_days_scanned += 1
    if len(expected) < target_sessions:
        raise RuntimeError(
            f"Official calendar coverage yielded only {len(expected)} sessions; "
            f"{target_sessions} are required."
        )
    missing = [day for day in expected if day not in found]
    if missing:
        sample = ",".join(day.isoformat() for day in missing[:12])
        raise RuntimeError(
            f"Bhavcopy cache is not contiguous for the latest {target_sessions} official sessions; "
            f"{len(missing)} session files are missing/invalid (sample: {sample}). "
            "Price cache was not downloaded or modified."
        )
    return sorted(expected)

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
    cache_dir.mkdir(parents=True, exist_ok=True)
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
            records.append({
                "SessionDate": day.isoformat(), "Status": status,
                "ValidEQDeliveryRows": rows, "Bytes": size, "SHA256": digest,
            })
            print(f"[DELIVERY BACKFILL] {index}/{len(dates)} {day} {status} rows={rows}", flush=True)
    finally:
        session.close()

    coverage = pd.DataFrame(records)
    coverage.to_csv(output_dir / "coverage.csv", index=False)
    valid_count = int(coverage["Status"].isin(["REUSED_CACHE", "DOWNLOADED"]).sum())
    summary = {
        "RequestedPriceSessions": len(dates), "RequestedStartDate": dates[0].isoformat(),
        "RequestedEndDate": dates[-1].isoformat(), "ValidDeliveryReports": valid_count,
        "Downloaded": int(coverage["Status"].eq("DOWNLOADED").sum()),
        "ReusedCache": int(coverage["Status"].eq("REUSED_CACHE").sum()),
        "MissingOrRejected": len(dates) - valid_count, "PriceCacheModified": False,
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
    summary = run_backfill(target_sessions=args.sessions)
    return 0 if summary["Status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
