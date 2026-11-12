"""Audit and maintain the durable 200-official-session NSE Delivery cache.

The scanner continues to use its independent 30-calendar-day Delivery window.
Only verified official-session report CSVs older than the latest 200 validated
Bhavcopy sessions may be pruned. The Bhavcopy cache is read-only here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import re

import pandas as pd

from delivery_history_backfill import price_session_dates
from nse_trading_calendar import CalendarCoverageError, is_trading_session
from volume_gainer import validate_bhavcopy_date

DELIVERY_CACHE_DIR = Path("data/cache/delivery")
BHAVCOPY_DIR = Path("data/bhavcopy")
DELIVERY_FILE_RE = re.compile(r"^sec_bhavdata_full_(\d{8})\.csv$")
REQUIRED_COLUMNS = {"SYMBOL", "SERIES", "DELIV_PER"}
DEFAULT_TARGET_SESSIONS = 200


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
        frame = pd.read_csv(path, low_memory=False)
        frame.columns = [str(c).strip().upper().replace(" ", "_") for c in frame.columns]
        if frame.empty or not REQUIRED_COLUMNS.issubset(frame.columns) or "DATE1" not in frame.columns:
            return False
        parsed = pd.to_datetime(frame["DATE1"].astype(str).str.strip(), errors="coerce", dayfirst=True)
        if parsed.isna().any() or set(parsed.dt.date.tolist()) != {expected_date}:
            return False
        delivery = pd.to_numeric(frame["DELIV_PER"], errors="coerce")
        return bool(delivery.between(0, 100, inclusive="both").any())
    except Exception:
        return False


def delivery_cache_inventory(asof_date: date, cache_dir: Path = DELIVERY_CACHE_DIR) -> dict:
    """Validate reports in the scanner's inclusive 30-calendar-day window."""
    asof = pd.Timestamp(asof_date).date()
    start = asof - timedelta(days=29)
    expected = [asof - timedelta(days=offset) for offset in range(30)
                if is_trading_session(asof - timedelta(days=offset))]
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
            elif _valid_delivery_file(path, day):
                valid[day] = path
            else:
                invalid.append(path.name)
    missing = [day for day in expected if day not in valid]
    latest = max(valid) if valid else None
    age = (asof - latest).days if latest else None
    return {
        "asof_date": asof, "window_start": start, "expected_sessions": expected,
        "valid_files": valid, "missing_sessions": missing, "invalid_files": invalid,
        "non_session_files": non_sessions, "latest_report_date": latest,
        "latest_report_age_days": age, "stale": age is None or age > 7,
    }


def audit_delivery_cache(asof_date: date, cache_dir: Path = DELIVERY_CACHE_DIR) -> dict:
    """Log the independent 30-calendar-day scanner coverage."""
    inventory = delivery_cache_inventory(asof_date, cache_dir)
    expected, valid = len(inventory["expected_sessions"]), len(inventory["valid_files"])
    print(f"DELIVERY_CACHE_WINDOW_30D={inventory['window_start']}..{inventory['asof_date']}")
    print(f"DELIVERY_CACHE_VALID_REPORTS_30D={valid}")
    print(f"DELIVERY_CACHE_EXPECTED_NSE_SESSIONS_30D={expected}")
    print(f"DELIVERY_CACHE_COVERAGE_30D={valid}/{expected}")
    print(f"DELIVERY_CACHE_LATEST_REPORT={inventory['latest_report_date'] or 'NONE'}")
    print(f"DELIVERY_CACHE_LATEST_REPORT_AGE_DAYS={inventory['latest_report_age_days']}")
    print(f"DELIVERY_CACHE_STALE={inventory['stale']}")
    print("DELIVERY_CACHE_MISSING_SESSIONS_30D=" + (",".join(d.isoformat() for d in inventory["missing_sessions"]) or "NONE"))
    print("DELIVERY_CACHE_INVALID_FILES_30D=" + (",".join(inventory["invalid_files"]) or "NONE"))
    print("DELIVERY_CACHE_NON_SESSION_FILES_30D=" + (",".join(inventory["non_session_files"]) or "NONE"))
    return inventory


def delivery_history_inventory(
    cache_dir: Path = DELIVERY_CACHE_DIR,
    bhavcopy_dir: Path = BHAVCOPY_DIR,
    target_sessions: int = DEFAULT_TARGET_SESSIONS,
) -> dict:
    """Validate Delivery reports against the exact latest N validated Bhavcopy sessions."""
    expected = price_session_dates(bhavcopy_dir, target_sessions)
    valid: dict[date, Path] = {}
    invalid: list[str] = []
    if cache_dir.exists():
        for day in expected:
            path = cache_dir / f"sec_bhavdata_full_{day.strftime('%d%m%Y')}.csv"
            if _valid_delivery_file(path, day):
                valid[day] = path
            elif path.exists():
                invalid.append(path.name)
    missing = [day for day in expected if day not in valid]
    return {
        "expected_sessions": expected, "valid_files": valid, "missing_sessions": missing,
        "invalid_files": invalid, "complete": len(valid) == target_sessions,
        "oldest_session": min(expected), "latest_session": max(expected),
        "target_sessions": target_sessions,
    }


def audit_delivery_history_cache(
    cache_dir: Path = DELIVERY_CACHE_DIR,
    bhavcopy_dir: Path = BHAVCOPY_DIR,
    target_sessions: int = DEFAULT_TARGET_SESSIONS,
) -> dict:
    inventory = delivery_history_inventory(cache_dir, bhavcopy_dir, target_sessions)
    print(f"DELIVERY_HISTORY_TARGET_SESSIONS={target_sessions}")
    print(f"DELIVERY_HISTORY_RANGE={inventory['oldest_session']}..{inventory['latest_session']}")
    print(f"DELIVERY_HISTORY_VALID_REPORTS={len(inventory['valid_files'])}")
    print(f"DELIVERY_HISTORY_COVERAGE={len(inventory['valid_files'])}/{target_sessions}")
    print(f"DELIVERY_HISTORY_MISSING_SESSIONS=" + (",".join(d.isoformat() for d in inventory["missing_sessions"]) or "NONE"))
    print(f"DELIVERY_HISTORY_INVALID_FILES=" + (",".join(inventory["invalid_files"]) or "NONE"))
    print(f"DELIVERY_HISTORY_COMPLETE={inventory['complete']}")
    return inventory


def prune_old_delivery_reports(
    cache_dir: Path = DELIVERY_CACHE_DIR,
    bhavcopy_dir: Path = BHAVCOPY_DIR,
    target_sessions: int = DEFAULT_TARGET_SESSIONS,
) -> list[str]:
    """Prune only verified official reports older than the latest complete N-session cache."""
    inventory = delivery_history_inventory(cache_dir, bhavcopy_dir, target_sessions)
    if not inventory["complete"]:
        raise RuntimeError(
            f"Refusing to prune Delivery cache: only {len(inventory['valid_files'])}/"
            f"{target_sessions} required reports are valid."
        )
    retained = set(inventory["expected_sessions"])
    oldest = inventory["oldest_session"]
    removed: list[str] = []
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
        if day >= oldest or day in retained or not is_trading_session(day):
            continue
        if _valid_delivery_file(path, day):
            path.unlink()
            removed.append(path.name)
    return sorted(removed)


def main() -> int:
    asof = latest_bhavcopy_date()
    if asof is None:
        print("DELIVERY_CACHE_ASOF=WAIT_FOR_DATA (no validated cached Bhavcopy date)")
        return 0
    audit_delivery_cache(asof)
    audit_delivery_history_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
