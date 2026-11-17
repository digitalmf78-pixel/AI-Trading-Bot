"""Independent official NSE calendar and corporate-action validation for U-Turn pilot."""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path


def expected_nse_sessions(start: date, end: date, holidays: set[date]) -> list[str]:
    """Weekday equity sessions after removing official NSE holidays."""
    sessions = []
    day = start
    while day <= end:
        if day.weekday() < 5 and day not in holidays:
            sessions.append(day.isoformat())
        day += timedelta(days=1)
    return sessions


def next_nse_session(event_date: date, holidays: set[date]) -> date:
    """Return the first weekday equity session strictly after the event date."""
    day = event_date + timedelta(days=1)
    while day.weekday() >= 5 or day in holidays:
        day += timedelta(days=1)
    return day


def dividend_inclusive_simple_return_pct(start_close: float, end_close: float, gross_cash_dividends: float) -> float:
    """Gross cash-dividend-inclusive simple return; no reinvestment or tax adjustment."""
    if start_close <= 0:
        raise ValueError("start_close must be positive")
    return ((end_close + gross_cash_dividends - start_close) / start_close) * 100.0

def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def run_audit(root: Path = Path(".")) -> dict:
    research = root / "research/ecms_uturn"
    output = root / "v8_cache_audit"
    output.mkdir(exist_ok=True)

    holiday_rows = _read_csv(research / "nse_equity_holidays_2026.csv")
    holidays = {date.fromisoformat(row["Date"]) for row in holiday_rows}
    manifest = _read_csv(research / "nse_ohlc_download_manifest.csv")
    events = _read_csv(research / "backtest_events.csv")
    event_audit = _read_csv(research / "event_announcement_audit.csv")
    actions = _read_csv(research / "corporate_action_audit.csv")

    strict_rows = _read_csv(output / "cached_ohlc_session_audit.csv")
    strict_summary = _read_csv(output / "cached_ohlc_window_summary.csv")
    post_closes = _read_csv(output / "cached_post_result_close.csv")
    delivery_rows = _read_csv(output / "cached_delivery_coverage.csv")
    event_results_path = root / "uturn_cache_backtest/event_study_results.csv"
    event_results = _read_csv(event_results_path)

    errors: list[str] = []
    calendar_results = []
    symbols = sorted({row["Symbol"] for row in manifest})

    for symbol in symbols:
        rows = sorted(
            [row for row in manifest if row["Symbol"] == symbol],
            key=lambda row: row["Expected_NSE_Session"],
        )
        dates = [date.fromisoformat(row["Expected_NSE_Session"]) for row in rows]
        if len(rows) != 20 or len(set(dates)) != 20:
            errors.append(f"{symbol}: expected exactly 20 unique manifest sessions; found {len(rows)}")
            continue
        expected = expected_nse_sessions(dates[0], dates[-1], holidays)
        actual = [item.isoformat() for item in dates]
        if expected != actual:
            errors.append(
                f"{symbol}: manifest does not match official NSE calendar; "
                f"missing={sorted(set(expected)-set(actual))}; extra={sorted(set(actual)-set(expected))}"
            )
        if any(day.weekday() >= 5 or day in holidays for day in dates):
            errors.append(f"{symbol}: manifest contains weekend or official NSE holiday")

        strict = [row for row in strict_rows if row["Symbol"] == symbol]
        ready_dates = sorted(row["Date"] for row in strict if row["Status"] == "READY")
        if len(strict) != 20 or ready_dates != actual:
            errors.append(f"{symbol}: strict cache evidence is not 20/20 READY")

        delivery = [row for row in delivery_rows if row["Symbol"] == symbol]
        delivery_dates = sorted(row["Date"] for row in delivery if row["Status"] == "READY")
        if len(delivery) != 20 or delivery_dates != actual:
            errors.append(f"{symbol}: delivery cache coverage is not 20/20 READY")
        strict_window = next((row for row in strict_summary if row["Symbol"] == symbol), None)
        event_result = next((row for row in event_results if row["Symbol"] == symbol), None)
        if not strict_window or strict_window["Status"] != "READY":
            errors.append(f"{symbol}: strict window summary is not READY")
        if not event_result or int(event_result["PreResultSessionsInCache"]) != 20:
            errors.append(f"{symbol}: event-study did not use exactly 20 pre-result sessions")
        if strict_window and event_result:
            if strict_window["PeakDate"] != event_result["PeakHighDate"]:
                errors.append(f"{symbol}: strict/event-study peak date mismatch")
            if abs(float(strict_window["PeakHigh"]) - float(event_result["PeakHigh"])) > 1e-6:
                errors.append(f"{symbol}: strict/event-study peak High mismatch")

        calendar_results.append({
            "Symbol": symbol,
            "ExpectedSessions": 20,
            "ManifestSessions": len(actual),
            "CacheRowsReady": len(ready_dates),
            "CalendarStatus": "PASS" if expected == actual else "FAIL",
            "WindowStart": actual[0],
            "WindowEnd": actual[-1],
        })

    event_results_audit = []
    for event in event_audit:
        symbol = event["Symbol"]
        event_date = date.fromisoformat(event["EventDate"])
        expected_first = next_nse_session(event_date, holidays).isoformat()
        if event["FirstPostResultSession"] != expected_first:
            errors.append(
                f"{symbol}: first post-result session {event['FirstPostResultSession']} "
                f"does not equal next NSE session {expected_first}"
            )
        source_event = next((row for row in events if row["Symbol"] == symbol), None)
        if not source_event or source_event["Result_Announcement_Date"] != event["EventDate"]:
            errors.append(f"{symbol}: event date does not match backtest event register")
        result = next((row for row in event_results if row["Symbol"] == symbol), None)
        if not result or result["FirstPostResultSession"] != event["FirstPostResultSession"]:
            errors.append(f"{symbol}: event-study first post-result session mismatch")
        event_results_audit.append({
            "Symbol": symbol,
            "EventDate": event["EventDate"],
            "EventTimingIST": event["EventTimingIST"],
            "FirstPostResultSession": event["FirstPostResultSession"],
            "Status": "DATE_AND_SEQUENCE_VERIFIED",
            "EvidenceURL": event["AnnouncementEvidenceURL"],
        })

    close_ready = {row["Symbol"] for row in post_closes if row["Status"] == "READY"}
    if close_ready != set(symbols):
        errors.append(f"Latest close cache coverage not READY for all symbols: {sorted(close_ready)}")

    stock_action_reviewed = {
        row["Symbol"] for row in actions
        if row["ActionType"] == "NO_STOCK_ACTION_FOUND" and row["ReviewStatus"] == "REVIEWED"
    }
    if stock_action_reviewed != set(symbols):
        errors.append("Every pilot symbol must have an explicit reviewed stock-action status")

    dividends = []
    for row in actions:
        if row["ActionType"] != "CASH_DIVIDEND":
            continue
        if row["ReviewStatus"] != "VERIFIED":
            errors.append(f"{row['Symbol']}: dividend action not verified")
            continue
        dividends.append({
            "Symbol": row["Symbol"],
            "ExDate": row["ExDate"],
            "RecordDate": row["RecordDate"],
            "AmountINRPerShare": float(row["AmountINRPerShare"]),
            "Treatment": "EXCLUDED_FROM_PRICE_ONLY_RETURN; total-return series not computed",
            "SourceURL": row["SourceURL"],
        })

    horizon_path = root / "uturn_cache_backtest/post_result_horizon_observations.csv"
    horizon_rows = _read_csv(horizon_path)
    dividend_return_rows = []
    for row in horizon_rows:
        symbol = row["Symbol"]
        start_session = date.fromisoformat(row["StartSession"])
        end_session = date.fromisoformat(row["EndSession"])
        gross_cash = sum(
            item["AmountINRPerShare"]
            for item in dividends
            if item["Symbol"] == symbol
            and start_session < date.fromisoformat(item["ExDate"]) <= end_session
        )
        row["GrossCashDividendPerShare"] = f"{gross_cash:.2f}"
        if row["HorizonStatus"] == "COMPLETE":
            adjusted_return = dividend_inclusive_simple_return_pct(
                float(row["StartClose"]), float(row["EndClose"]), gross_cash
            )
            row["DividendInclusiveSimpleReturnPct"] = f"{adjusted_return:.6f}"
        else:
            row["DividendInclusiveSimpleReturnPct"] = ""
        row["DividendReturnMethod"] = "Gross cash added; no reinvestment, tax or fees; not a full total-return index"
        dividend_return_rows.append({
            "Symbol": symbol,
            "HorizonSessions": int(row["HorizonSessions"]),
            "GrossCashDividendPerShare": round(gross_cash, 2),
            "PriceOnlyReturnPct": float(row["CloseReturnPct"]) if row["CloseReturnPct"] else None,
            "DividendInclusiveSimpleReturnPct": float(row["DividendInclusiveSimpleReturnPct"]) if row["DividendInclusiveSimpleReturnPct"] else None,
        })
    if horizon_rows:
        with horizon_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(horizon_rows[0].keys()))
            writer.writeheader()
            writer.writerows(horizon_rows)
    audit = {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "calendar_source": "NSE Capital Market Segment Circular NSE/CMTR/71775 dated 12-Dec-2025",
        "calendar_source_url": "https://archives.nseindia.com/content/circulars/CMTR71775.pdf",
        "calendar_method": "All weekdays in each 20-session date range, excluding official NSE 2026 equity holidays; exact match required",
        "calendar_results": calendar_results,
        "event_announcement_results": event_results_audit,
        "latest_post_result_close_ready_symbols": sorted(close_ready),
        "delivery_window_rows_ready": sum(1 for row in delivery_rows if row["Status"] == "READY"),
        "delivery_window_rows_expected": 20 * len(symbols),
        "stock_action_review": "No bonus/split/rights/demerger found in reviewed event-window sources; explicit evidence links are in corporate_action_audit.csv",
        "cash_dividends": dividends,
        "dividend_inclusive_simple_horizon_returns": dividend_return_rows,
        "dividend_treatment": "Price-only returns retained; gross cash dividends separately added to horizon return as a no-reinvestment simple estimate; not a full total-return index",
        "sample_scope": "Three-stock descriptive pilot; not randomized and not statistically representative",
        "promotion_status": "PROVISIONAL_RESEARCH_ONLY; not a trade signal or production approval",
    }
    (output / "official_calendar_corporate_action_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )

    if not errors:
        for row in event_results:
            row["PreResultCalendarCrossCheck"] = "VERIFIED_OFFICIAL_NSE_2026_EQUITY_HOLIDAYS"
            row["CorporateActionStatus"] = "REVIEWED_NO_STOCK_ACTION; CASH_DIVIDENDS_ADDED_SEPARATELY"
        columns = list(event_results[0].keys()) if event_results else []
        with event_results_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(event_results)

        summary_path = root / "uturn_cache_backtest/backtest_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["calendar_cross_check"] = "VERIFIED: all 20-session windows exactly match official NSE 2026 equity holiday calendar"
        summary["corporate_action_review"] = "REVIEWED: no stock action found in event windows; gross cash dividends added separately to horizon simple-return estimate; no reinvestment or tax adjustment"
        summary["event_timing_audit"] = "Official company/NSE event evidence recorded; ACI exact public release minute remains unverified"
        summary["dividend_return_method"] = "Price-only and gross cash-dividend-inclusive simple returns reported separately; no reinvestment, taxes, fees or P&L simulation"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(audit, indent=2))
    if errors:
        raise SystemExit(2)
    return audit


if __name__ == "__main__":
    run_audit()
