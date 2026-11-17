"""Research-only T1/T2 data-readiness audit for NSE V8; no fills or production changes."""
from __future__ import annotations
import argparse, math, re
from pathlib import Path
import pandas as pd
from nse_trading_calendar import is_trading_session, CalendarCoverageError

PRICE_DIR = Path("data/bhavcopy")
OUTPUT_DIR = Path("outputs/t1_t2_readiness")
DATE_COLUMNS = ("EODDate", "AsOfDate", "SignalEODDate", "Date")
SYMBOL_COLUMNS = ("TckrSymb", "Symbol", "SYMBOL")
ENTRY_COLUMNS = ("EntryPricePlan", "EntryZoneHigh")
STOP_COLUMNS = ("StopLossPlan",)
RESISTANCE_FIELDS = (
    ("SRResistance", "SR_RESISTANCE"), ("SRSwingHigh", "SR_SWING_HIGH"),
    ("RecentSwingHigh", "RECENT_SWING_HIGH"), ("SR20DHigh", "SR_20D_HIGH"),
    ("High20D", "HIGH_20D"), ("SR50DHigh", "SR_50D_HIGH"),
    ("High50D", "HIGH_50D"), ("SR100DHigh", "SR_100D_HIGH"),
    ("High100D", "HIGH_100D"), ("SR200DHigh", "SR_200D_HIGH"),
    ("High200D", "HIGH_200D"),
)
PRICE_FILE_RE = re.compile(r"^bhavcopy_(\d{8})\.csv$", re.I)

def first_present(row, names):
    for name in names:
        if name in row.index and pd.notna(row[name]) and str(row[name]).strip():
            return row[name], name
    return None, None

def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else float("nan")
    except (TypeError, ValueError):
        return float("nan")

def signal_date(row):
    value, _ = first_present(row, DATE_COLUMNS)
    parsed = pd.to_datetime(value, errors="coerce") if value is not None else pd.NaT
    return None if pd.isna(parsed) else parsed.date()

def symbol_value(row):
    value, _ = first_present(row, SYMBOL_COLUMNS)
    return str(value).strip().upper() if value is not None else ""

def resistance_levels(row, entry):
    """Sorted unique explicit source levels above entry; no synthetic levels."""
    if not math.isfinite(entry) or entry <= 0:
        return []
    candidates = []
    for priority, (field, source) in enumerate(RESISTANCE_FIELDS):
        level = number(row[field]) if field in row.index else float("nan")
        if math.isfinite(level) and level > entry:
            candidates.append((level, source, priority))
    planned = number(row.get("TargetPricePlan"))
    planned_source = str(row.get("TargetSource", "")).strip()
    if math.isfinite(planned) and planned > entry and planned_source not in {"", "WAIT_FOR_DATA", "nan", "None"}:
        candidates.append((planned, planned_source, -1))
    candidates.sort(key=lambda x: (x[0], x[2]))
    unique, seen = [], set()
    for level, source, _ in candidates:
        if level not in seen:
            seen.add(level)
            unique.append((level, source))
    return unique

def load_price_cache(price_dir):
    """Read cached EQ OHLC; malformed, duplicate or invalid files are not used."""
    records, errors = {}, []
    if not price_dir.exists():
        return records, [f"PRICE_DIR_MISSING:{price_dir}"]
    for path in sorted(price_dir.glob("*.csv")):
        match = PRICE_FILE_RE.match(path.name)
        if not match:
            continue
        token = match.group(1)
        fmt = "%Y%m%d"
        try:
            day = pd.to_datetime(token, format=fmt, errors="raise").date()
        except Exception:
            errors.append(f"INVALID_FILENAME_DATE:{path.name}")
            continue
        try:
            frame = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            errors.append(f"CSV_READ_ERROR:{path.name}:{type(exc).__name__}")
            continue
        frame.columns = [str(c).strip() for c in frame.columns]
        date_col = next((name for name in ("BizDt", "TradDt", "TRADDT", "BUSINESS_DATE", "DATE") if name in frame.columns), None)
        if date_col is None:
            errors.append(f"INTERNAL_DATE_COLUMN_MISSING:{path.name}")
            continue
        internal_dates = set(pd.to_datetime(frame[date_col], errors="coerce", dayfirst=False).dt.date.dropna().tolist())
        if internal_dates != {day}:
            errors.append(f"INTERNAL_DATE_MISMATCH:{path.name}:{sorted(str(x) for x in internal_dates)}")
            continue
        upper = {c.upper(): c for c in frame.columns}
        aliases = {
            "SYMBOL": ("SYMBOL", "TCKRSYMB"), "SERIES": ("SERIES", "SCTYSRS"),
            "OPEN": ("OPEN", "OPNPRIC"), "HIGH": ("HIGH", "HGHPRIC"),
            "LOW": ("LOW", "LWPRIC"), "CLOSE": ("CLOSE", "CLSPRIC"),
        }
        chosen = {k: next((upper[v] for v in variants if v in upper), None) for k, variants in aliases.items()}
        if any(v is None for v in chosen.values()):
            errors.append(f"REQUIRED_OHLC_COLUMNS_MISSING:{path.name}")
            continue
        subset = frame[[chosen[k] for k in aliases]].copy()
        subset.columns = list(aliases)
        subset["SYMBOL"] = subset["SYMBOL"].astype(str).str.strip().str.upper()
        subset["SERIES"] = subset["SERIES"].astype(str).str.strip().str.upper()
        for col in ("OPEN", "HIGH", "LOW", "CLOSE"):
            subset[col] = pd.to_numeric(subset[col], errors="coerce")
        subset = subset[subset["SERIES"].eq("EQ")]
        if subset.empty:
            errors.append(f"NO_EQ_ROWS:{path.name}")
            continue
        try:
            if not is_trading_session(day):
                errors.append(f"BHAVCOPY_NON_SESSION:{path.name}")
                continue
        except CalendarCoverageError:
            raise
        if subset.duplicated(["SYMBOL", "SERIES"], keep=False).any():
            errors.append(f"DUPLICATE_SYMBOL_SERIES:{path.name}")
            continue
        bad = (subset[["OPEN","HIGH","LOW","CLOSE"]].isna().any(axis=1) |
               (subset["LOW"] <= 0) | (subset["LOW"] > subset["OPEN"]) |
               (subset["LOW"] > subset["CLOSE"]) | (subset["HIGH"] < subset["OPEN"]) |
               (subset["HIGH"] < subset["CLOSE"]) | (subset["HIGH"] < subset["LOW"]))
        if bad.any():
            errors.append(f"INVALID_OHLC:{path.name}:{int(bad.sum())}")
            continue
        for item in subset.to_dict("records"):
            records[(item["SYMBOL"], day)] = item
    return records, errors

def official_sessions_after(day, count):
    result = []
    cursor = pd.Timestamp(day).date() + pd.Timedelta(days=1)
    for _ in range(800):
        if is_trading_session(cursor):
            result.append(cursor)
            if len(result) == count:
                return result
        cursor += pd.Timedelta(days=1)
    raise RuntimeError(f"Could not resolve {count} official sessions after {day}")

def audit_signal_frame(frame, prices, source_name):
    output = []
    for idx, row in frame.iterrows():
        symbol, day = symbol_value(row), signal_date(row)
        entry_raw, entry_field = first_present(row, ENTRY_COLUMNS)
        stop_raw, stop_field = first_present(row, STOP_COLUMNS)
        entry, stop = number(entry_raw), number(stop_raw)
        reasons = []
        if not symbol: reasons.append("SYMBOL_MISSING")
        if day is None: reasons.append("SIGNAL_DATE_MISSING")
        if not math.isfinite(entry) or entry <= 0: reasons.append("ENTRY_MISSING_OR_INVALID")
        if not math.isfinite(stop) or stop <= 0: reasons.append("STOP_MISSING_OR_INVALID")
        next_session, forward_dates, coverage = None, [], "WAIT_FOR_DATA"
        horizon_coverage = {}
        if day is not None:
            try:
                forward_dates = official_sessions_after(day, 20)
                next_session = forward_dates[0]
                for horizon in (5, 10, 20):
                    required = forward_dates[:horizon]
                    missing = [d for d in required if (symbol, d) not in prices]
                    horizon_coverage[horizon] = (
                        f"COMPLETE_{horizon}_SESSIONS" if not missing
                        else f"MISSING_{len(missing)}_OF_{horizon}"
                    )
                coverage = horizon_coverage[20]
                if any(value.startswith("MISSING") for value in horizon_coverage.values()):
                    reasons.append("FORWARD_OHLC_COVERAGE_INCOMPLETE")
            except CalendarCoverageError as exc:
                reasons.append("OFFICIAL_CALENDAR_COVERAGE_MISSING:" + str(exc))
            except Exception as exc:
                reasons.append("SESSION_SEQUENCE_ERROR:" + type(exc).__name__)
        next_open = prices.get((symbol, next_session), {}).get("OPEN") if next_session else None
        next_open_value = number(next_open)
        entry_fill_valid = math.isfinite(next_open_value) and next_open_value > 0
        if not entry_fill_valid:
            reasons.append("NEXT_SESSION_OPEN_MISSING_OR_INVALID")
        if entry_fill_valid and math.isfinite(stop) and stop > 0 and next_open_value <= stop:
            entry_fill_valid = False
            reasons.append("NEXT_SESSION_OPEN_AT_OR_BELOW_STOP")
        common_plan_valid = bool(
            symbol and day is not None and math.isfinite(entry) and entry > 0
            and math.isfinite(stop) and stop > 0 and entry_fill_valid
        )
        # Structural targets must remain overhead resistance above the actual
        # assumed fill, not merely above the earlier planned entry-zone price.
        resistance_basis = next_open_value if entry_fill_valid else entry
        levels = resistance_levels(row, resistance_basis)
        t1 = levels[0] if len(levels) > 0 else (float("nan"), "WAIT_FOR_DATA")
        t2 = levels[1] if len(levels) > 1 else (float("nan"), "WAIT_FOR_DATA")
        if not math.isfinite(t1[0]): reasons.append("T1_VERIFIED_RESISTANCE_MISSING_ABOVE_ENTRY_FILL")
        if not math.isfinite(t2[0]): reasons.append("T2_DISTINCT_VERIFIED_RESISTANCE_MISSING_ABOVE_ENTRY_FILL")
        t1_valid, t2_valid = math.isfinite(t1[0]), math.isfinite(t2[0])
        horizon_ready = {}
        for horizon in (5, 10, 20):
            complete = horizon_coverage.get(horizon, "").startswith("COMPLETE_")
            horizon_ready[f"T1DataReady{horizon}D"] = "DATA_READY" if common_plan_valid and t1_valid and complete else "WAIT_FOR_DATA"
            horizon_ready[f"T2DataReady{horizon}D"] = "DATA_READY" if common_plan_valid and t2_valid and complete else "WAIT_FOR_DATA"
        any_horizon_ready = any(value == "DATA_READY" for value in horizon_ready.values())
        output.append({
            "SourceFile": source_name, "SourceRow": int(idx)+1,
            "EODDate": day.isoformat() if day else "", "Symbol": symbol,
            "EntryPricePlan": entry if math.isfinite(entry) else "", "EntrySourceField": entry_field or "",
            "StopLossPlan": stop if math.isfinite(stop) else "", "StopSourceField": stop_field or "",
            "Target1": t1[0] if math.isfinite(t1[0]) else "", "Target1Source": t1[1],
            "Target2": t2[0] if math.isfinite(t2[0]) else "", "Target2Source": t2[1],
            "NextOfficialSession": next_session.isoformat() if next_session else "",
            "NextSessionOpen": next_open if next_open is not None else "",
            "EntryExecutionRule": "NEXT_OFFICIAL_SESSION_OPEN",
            "EntryExecutionPrice": next_open_value if entry_fill_valid else "",
            "EntryExecutionStatus": "ENTRY_READY" if entry_fill_valid else "WAIT_FOR_DATA",
            "ForwardOHLC5Coverage": horizon_coverage.get(5, "WAIT_FOR_DATA"),
            "ForwardOHLC10Coverage": horizon_coverage.get(10, "WAIT_FOR_DATA"),
            "ForwardOHLC20Coverage": horizon_coverage.get(20, "WAIT_FOR_DATA"),
            **horizon_ready,
            "ResistanceCandidateCount": len(levels),
            "ReadinessStatus": "PARTIAL_DATA_READY" if any_horizon_ready else "WAIT_FOR_DATA",
            "ReadinessReasons": ";".join(reasons),
        })
    return pd.DataFrame(output)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signals", nargs="+", required=True, help="Archived EOD report CSV paths")
    parser.add_argument("--prices-dir", type=Path, default=PRICE_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    prices, errors = load_price_cache(args.prices_dir)
    frames = []
    for item in args.signals:
        path = Path(item)
        if not path.exists():
            print(f"SIGNAL_FILE_MISSING={path}")
            continue
        try:
            data = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            print(f"SIGNAL_FILE_READ_ERROR={path}:{type(exc).__name__}")
            continue
        if data.empty:
            print(f"SIGNAL_FILE_EMPTY={path}")
            continue
        frames.append(audit_signal_frame(data, prices, path.name))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    report = args.output_dir / "t1_t2_data_readiness.csv"
    result.to_csv(report, index=False)
    (args.output_dir / "price_cache_validation_errors.txt").write_text("\n".join(errors) + ("\n" if errors else ""), encoding="utf-8")
    print(f"PRICE_CACHE_ROWS_VALIDATED={len(prices)}")
    print(f"PRICE_CACHE_VALIDATION_ERRORS={len(errors)}")
    print(f"SIGNAL_ROWS_AUDITED={len(result)}")
    if not result.empty:
        print("READINESS_COUNTS=" + str(result["ReadinessStatus"].value_counts().to_dict()))
        print("T1_READY_ROWS=" + str(pd.to_numeric(result["Target1"], errors="coerce").notna().sum()))
        print("T2_READY_ROWS=" + str(pd.to_numeric(result["Target2"], errors="coerce").notna().sum()))
    print(f"REPORT={report}")
    return 0 if not result.empty and not errors else 1

if __name__ == "__main__":
    raise SystemExit(main())
