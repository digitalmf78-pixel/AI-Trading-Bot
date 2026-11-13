"""Isolated, research-only NSE CM Bhavcopy archive backfill.

Never reads, writes, prunes, or imports the production data/bhavcopy cache.
Only validated official NSE archive CSVs are atomically persisted beneath
data/research/bhavcopy_backtest/. Missing dates and invalid responses remain
explicit in the manifest; no data is synthesized.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from nse_trading_calendar import CalendarCoverageError, is_trading_session

NSE_BASE_URL = "https://nsearchives.nseindia.com/content/cm/"
DEFAULT_CACHE_DIR = Path("data/research/bhavcopy_backtest")
DEFAULT_OUTPUT_DIR = Path("outputs/research_bhavcopy_backfill")
REQUEST_INTERVAL_SECONDS = 1.10
MAX_RETRIES = 3
DATE_COLUMNS = ("BizDt", "TradDt", "TRADDT", "BUSINESS_DATE", "DATE")
REQUIRED_COLUMNS = {
    "TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric",
    "ClsPric", "TtlTradgVol",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}


def expected_sessions(end_date: date, count: int) -> list[date]:
    """Get exactly the latest N official sessions ending on/before end_date."""
    if count < 1:
        raise ValueError("sessions must be >= 1")
    start = date(end_date.year - 1, 1, 1)
    found = []
    try:
        cursor = start
        while cursor <= end_date:
            if is_trading_session(cursor):
                found.append(cursor)
            cursor += timedelta(days=1)
    except CalendarCoverageError:
        raise
    if len(found) < count:
        raise RuntimeError(
            f"Official NSE calendar yielded only {len(found)} sessions; {count} required. "
            "Extend the calendar only from official NSE notices; do not infer sessions."
        )
    return found[-count:]


def validate_bhavcopy(frame: pd.DataFrame, expected: date, source: str = "Bhavcopy") -> None:
    """Validate archive date, required fields, EQ identity uniqueness and OHLCV."""
    if frame is None or frame.empty:
        raise ValueError(f"{source}: empty CSV")
    date_col = next((name for name in DATE_COLUMNS if name in frame.columns), None)
    if not date_col:
        raise ValueError(f"{source}: internal business-date column missing")
    parsed = pd.to_datetime(frame[date_col], errors="coerce", dayfirst=False).dt.date
    observed = set(parsed.dropna())
    if observed != {expected}:
        raise ValueError(f"{source}: internal date mismatch; expected={expected}, observed={sorted(map(str, observed))}")
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{source}: missing required columns {sorted(missing)}")

    eq = frame[frame["SctySrs"].astype(str).str.strip().str.upper().eq("EQ")].copy()
    if eq.empty:
        raise ValueError(f"{source}: no EQ rows")
    eq["TckrSymb"] = eq["TckrSymb"].astype(str).str.strip().str.upper()
    if eq["TckrSymb"].eq("").any() or eq["TckrSymb"].duplicated().any():
        raise ValueError(f"{source}: blank or duplicate EQ symbol/session rows")

    numeric = eq[["OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"]].apply(
        pd.to_numeric, errors="coerce"
    )
    if numeric.isna().any().any():
        raise ValueError(f"{source}: missing/non-numeric EQ OHLCV values")
    if not numeric.apply(lambda col: col.map(lambda x: pd.notna(x) and math.isfinite(float(x)) and float(x) >= 0)).all().all():
        raise ValueError(f"{source}: negative or non-finite OHLCV values")
    if (numeric[["OpnPric", "HghPric", "LwPric", "ClsPric"]] <= 0).any().any():
        raise ValueError(f"{source}: non-positive EQ price")
    if (
        (numeric["HghPric"] < numeric["LwPric"]).any()
        or (numeric["OpnPric"] < numeric["LwPric"]).any()
        or (numeric["OpnPric"] > numeric["HghPric"]).any()
        or (numeric["ClsPric"] < numeric["LwPric"]).any()
        or (numeric["ClsPric"] > numeric["HghPric"]).any()
    ):
        raise ValueError(f"{source}: invalid EQ OHLC candle structure")


def read_archive_csv(content: bytes, expected: date, source: str = "NSE archive") -> pd.DataFrame:
    if not content or content.lstrip().lower().startswith((b"<html", b"<!doctype")):
        raise ValueError(f"{source}: empty or HTML response")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError(f"{source}: expected exactly one CSV in ZIP, found {len(csv_names)}")
            with archive.open(csv_names[0]) as stream:
                frame = pd.read_csv(stream, low_memory=False)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{source}: response is not a valid ZIP") from exc
    validate_bhavcopy(frame, expected, source)
    return frame


def _cached_frame(path: Path, day: date) -> tuple[bool, str]:
    if not path.is_file():
        return False, "NOT_PRESENT"
    try:
        frame = pd.read_csv(path, low_memory=False)
        validate_bhavcopy(frame, day, f"Research cache {path.name}")
        return True, hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception as exc:
        return False, f"INVALID_CACHE:{type(exc).__name__}:{exc}"


def download_one(session: requests.Session, day: date, cache_dir: Path,
                 retries: int = MAX_RETRIES, sleep=time.sleep) -> dict:
    token = day.strftime("%Y%m%d")
    destination = cache_dir / f"bhavcopy_{token}.csv"
    valid, cache_state = _cached_frame(destination, day)
    if valid:
        return {"date": day.isoformat(), "status": "REUSED_VALID_CACHE",
                "sha256": cache_state, "rows": int(len(pd.read_csv(destination)))}

    url = f"{NSE_BASE_URL}BhavCopy_NSE_CM_0_0_0_{token}_F_0000.csv.zip"
    last_error = cache_state
    for attempt in range(retries):
        try:
            response = session.get(url, timeout=(15, 45))
            if response.status_code == 404:
                return {"date": day.isoformat(), "status": "NSE_ARCHIVE_NOT_FOUND",
                        "http_status": 404, "reason": "Official archive returned HTTP 404"}
            if response.status_code in (403, 429) or response.status_code >= 500:
                last_error = f"HTTP_{response.status_code}"
                if attempt + 1 < retries:
                    sleep((2 ** attempt) * 2)
                    continue
                break
            response.raise_for_status()
            frame = read_archive_csv(response.content, day, url)
            cache_dir.mkdir(parents=True, exist_ok=True)
            temp = destination.with_suffix(".csv.tmp")
            frame.to_csv(temp, index=False)
            # Re-read the exact bytes that will be persisted before atomic replace.
            check = pd.read_csv(temp, low_memory=False)
            validate_bhavcopy(check, day, f"Staged research cache {temp.name}")
            temp.replace(destination)
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            return {"date": day.isoformat(), "status": "DOWNLOADED_VALIDATED",
                    "http_status": response.status_code, "rows": int(len(frame)),
                    "eq_rows": int(frame["SctySrs"].astype(str).str.strip().str.upper().eq("EQ").sum()),
                    "sha256": digest, "url": url}
        except requests.RequestException as exc:
            last_error = f"REQUEST_ERROR:{type(exc).__name__}:{exc}"
            if attempt + 1 < retries:
                sleep((2 ** attempt) * 2)
        except Exception as exc:
            return {"date": day.isoformat(), "status": "REJECTED_INVALID_RESPONSE",
                    "reason": f"{type(exc).__name__}:{exc}", "url": url}
    return {"date": day.isoformat(), "status": "DOWNLOAD_FAILED",
            "reason": last_error, "url": url}


def run_backfill(sessions: int = 420, end_date: date | None = None,
                 cache_dir: Path = DEFAULT_CACHE_DIR, output_dir: Path = DEFAULT_OUTPUT_DIR,
                 max_new_downloads: int | None = None, request_interval: float = REQUEST_INTERVAL_SECONDS,
                 session: requests.Session | None = None) -> dict:
    end = end_date or date.today()
    dates = expected_sessions(end, sessions)
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    http = session or requests.Session()
    http.headers.update(HEADERS)

    results = []
    new_download_attempts = 0
    for day in dates:
        destination = cache_dir / f"bhavcopy_{day:%Y%m%d}.csv"
        valid, _ = _cached_frame(destination, day)
        if valid:
            results.append(download_one(http, day, cache_dir))
            continue
        if max_new_downloads is not None and new_download_attempts >= max_new_downloads:
            results.append({"date": day.isoformat(), "status": "NOT_ATTEMPTED_DOWNLOAD_LIMIT"})
            continue
        if new_download_attempts:
            time.sleep(max(0.0, request_interval))
        result = download_one(http, day, cache_dir)
        new_download_attempts += 1
        results.append(result)

    counts = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    summary = {
        "source": "Official NSE CM Bhavcopy ZIP archive",
        "cache_dir": str(cache_dir),
        "production_bhavcopy_cache_touched": False,
        "requested_sessions": sessions,
        "end_date_inclusive": end.isoformat(),
        "first_requested_session": dates[0].isoformat(),
        "last_requested_session": dates[-1].isoformat(),
        "status_counts": counts,
        "validated_coverage": sum(counts.get(key, 0) for key in ("REUSED_VALID_CACHE", "DOWNLOADED_VALIDATED")),
        "complete": sum(counts.get(key, 0) for key in ("REUSED_VALID_CACHE", "DOWNLOADED_VALIDATED")) == sessions,
        "results": results,
    }
    manifest = output_dir / "research_bhavcopy_backfill_manifest.json"
    temp = manifest.with_suffix(".json.tmp")
    temp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    temp.replace(manifest)
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=420)
    parser.add_argument("--end-date", type=date.fromisoformat, default=None, help="Inclusive YYYY-MM-DD")
    parser.add_argument("--max-new-downloads", type=int, default=None,
                        help="Optional cap; remaining sessions are explicitly NOT_ATTEMPTED")
    parser.add_argument("--request-interval", type=float, default=REQUEST_INTERVAL_SECONDS)
    args = parser.parse_args()
    summary = run_backfill(args.sessions, args.end_date, max_new_downloads=args.max_new_downloads,
                           request_interval=args.request_interval)
    return 0 if summary["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
