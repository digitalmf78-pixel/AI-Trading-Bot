"""Audit and maintain the durable 30-calendar-day NSE Delivery report cache.

Only date-stamped official Delivery CSVs are pruned. The independent delivery
streak state and all other files in data/cache/delivery are preserved.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import re

import pandas as pd

from nse_trading_calendar import CalendarCoverageError, is_trading_session
from volume_gainer import validate_bhavcopy_date

DELIVERY_CACHE_DIR = Path("data/cache/delivery")
BHAVCOPY_DIR = Path("data/bhavcopy")
DELIVERY_FILE_RE = re.compile(r"^sec_bhavdata_full_(\d{8})\.csv$")
REQUIRED_COLUMNS = {"SYMBOL", "SERIES", "DELIV_PER"}


def latest_bhavcopy_date(bhavcopy_dir: Path = BHAVCOPY_DIR) -> date | None:
    """Return the latest internally validated NSE EOD date in the local cache."""
    candidates = []
    for path in bhavcopy_dir.glob("bhavcopy_????????.csv"):
        try:
            day = datetime.strptime(path.stem.removeprefix("bhavcopy_"), "%Y%m%d").date()
            if not is_trading_session(day):
                continue
            frame = pd.read_csv(path)
            validate_bhavcopy_date(frame, day, source=f"Delivery cache as-of {path}")
            candidates.append(day)
        except CalendarCoverageError:
            raise
        except Exception:
            continue
    return max(candidates) if candidates else None


def _valid_delivery_file(path: Path, expected_date: date) -> bool:
    try:
        frame = pd.read_csv(path)
        frame.columns = [str(c).strip().upper().replace(" ", "_") for c in frame.columns]
        if frame.empty or not REQUIRED_COLUMNS.issubset(frame.columns):
            return False
        if "DATE1" not in frame.columns:
            return False
        parsed = pd.to_datetime(frame["DATE1"].astype(str).str.strip(), errors="coerce", dayfirst=True)
        if parsed.isna().any() or set(parsed.dt.date.tolist()) != {expected_date}:
            return False
        delivery = pd.to_numeric(frame["DELIV_PER"], errors="coerce")
        return bool(delivery.between(0, 100, inclusive="both").any())
    except Exception:
        return False


def delivery_cache_inventory(asof_date: date, cache_dir: Path = DELIVERY_CACHE_DIR) -> dict:
    """Validate all official-session reports in the inclusive 30-calendar-day window."""
    asof = pd.Timestamp(asof_date).date()
    start = asof - timedelta(days=29)
    expected = []
    for offset in range(30):
        day = asof - timedelta(days=offset)
        if is_trading_session(day):
            expected.append(day)

    valid: dict[date, Path] = {}
    invalid: list[str] = []
    non_sessions: list[str] = []
    if cache_dir.exists():
        for path in cache_dir.iterdir():
            match = DELIVERY_FILE_RE.match(path.name)
            if not match:
                continue
            try:
                day = datetime.strptime(match.group(1), "%d%m%Y").date()
            except ValueError:
                invalid.append(path.name)
                continue
            if day < start or day > asof:
                continue
            if day not in expected:
                non_sessions.append(path.name)
                continue
            if _valid_delivery_file(path, day):
                valid[day] = path
            else:
                invalid.append(path.name)

    missing = [day for day in expected if day not in valid]
    latest = max(valid) if valid else None
    age = (asof - latest).days if latest else None
    return {
        "asof_date": asof,
        "window_start": start,
        "expected_sessions": expected,
        "valid_files": valid,
        "missing_sessions": missing,
        "invalid_files": invalid,
        "non_session_files": non_sessions,
        "latest_report_date": latest,
        "latest_report_age_days": age,
        "stale": age is None or age > 7,
    }


def audit_delivery_cache(asof_date: date, cache_dir: Path = DELIVERY_CACHE_DIR) -> dict:
    inventory = delivery_cache_inventory(asof_date, cache_dir)
    expected = len(inventory["expected_sessions"])
    valid = len(inventory["valid_files"])
    missing = inventory["missing_sessions"]
    print(f"DELIVERY_CACHE_WINDOW={inventory['window_start']}..{inventory['asof_date']} (30 calendar days)")
    print(f"DELIVERY_CACHE_VALID_REPORTS_30D={valid}")
    print(f"DELIVERY_CACHE_EXPECTED_NSE_SESSIONS_30D={expected}")
    print(f"DELIVERY_CACHE_COVERAGE={valid}/{expected}")
    print(f"DELIVERY_CACHE_LATEST_REPORT={inventory['latest_report_date'] or 'NONE'}")
    print(f"DELIVERY_CACHE_LATEST_REPORT_AGE_DAYS={inventory['latest_report_age_days']}")
    print(f"DELIVERY_CACHE_STALE={inventory['stale']}")
    print("DELIVERY_CACHE_MISSING_SESSIONS=" + (",".join(d.isoformat() for d in missing) if missing else "NONE"))
    print("DELIVERY_CACHE_INVALID_FILES=" + (",".join(inventory["invalid_files"]) if inventory["invalid_files"] else "NONE"))
    print("DELIVERY_CACHE_NON_SESSION_FILES=" + (",".join(inventory["non_session_files"]) if inventory["non_session_files"] else "NONE"))
    return inventory


def prune_old_delivery_reports(asof_date: date, cache_dir: Path = DELIVERY_CACHE_DIR) -> list[str]:
    """Delete only date-stamped Delivery report CSVs older than the 30-day window."""
    start = pd.Timestamp(asof_date).date() - timedelta(days=29)
    removed = []
    if not cache_dir.exists():
        return removed
    for path in cache_dir.iterdir():
        match = DELIVERY_FILE_RE.match(path.name)
        if not match:
            continue
        try:
            day = datetime.strptime(match.group(1), "%d%m%Y").date()
        except ValueError:
            continue
        if day < start:
            path.unlink()
            removed.append(path.name)
    return removed


def main() -> int:
    asof = latest_bhavcopy_date()
    if asof is None:
        print("DELIVERY_CACHE_ASOF=WAIT_FOR_DATA (no validated cached Bhavcopy date)")
        return 0
    audit_delivery_cache(asof)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
