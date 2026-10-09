
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import time

import pandas as pd
import requests


BASE_URL = (
    "https://nsearchives.nseindia.com/"
    "products/content/sec_bhavdata_full_{date}.csv"
)

CACHE_DIR = Path("data/cache/delivery")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _normalise_columns(df):
    df.columns = [
        str(c).strip().upper().replace(" ", "_")
        for c in df.columns
    ]
    return df


def _download_one(session, trading_date):
    date_text = trading_date.strftime("%d%m%Y")
    path = CACHE_DIR / f"sec_bhavdata_full_{date_text}.csv"

    if path.exists() and path.stat().st_size > 1000:
        try:
            cached = _normalise_columns(pd.read_csv(path))
            if {"SYMBOL", "SERIES", "DELIV_PER"} <= set(cached.columns):
                return cached
        except Exception:
            pass

    url = BASE_URL.format(date=date_text)
    response = session.get(url, timeout=25)

    if response.status_code == 404:
        return None

    response.raise_for_status()

    content = response.text
    if not content.strip() or "<html" in content[:500].lower():
        return None

    path.write_text(content, encoding="utf-8")
    df = _normalise_columns(pd.read_csv(path))

    required = {"SYMBOL", "SERIES", "DELIV_PER"}
    if not required.issubset(df.columns):
        raise ValueError(
            f"NSE delivery report columns unexpected: {list(df.columns)}"
        )

    return df


def get_previous_delivery_sessions(asof_date, required_sessions=5):
    """
    Fetch the five most recent available NSE delivery reports
    strictly before asof_date. Current EOD session is excluded.
    """
    if isinstance(asof_date, str):
        asof_date = datetime.strptime(
            asof_date[:10], "%Y-%m-%d"
        ).date()

    session = requests.Session()
    session.headers.update(HEADERS)

    # Warm up the NSE session; access may still be denied by NSE.
    try:
        session.get("https://www.nseindia.com", timeout=15)
    except requests.RequestException:
        pass

    reports = []
    current_day = asof_date - timedelta(days=1)
    earliest_day = asof_date - timedelta(days=25)

    while current_day >= earliest_day and len(reports) < required_sessions:
        if current_day.weekday() < 5:
            try:
                report = _download_one(session, current_day)

                if report is not None and not report.empty:
                    report = _normalise_columns(report)
                    report["REPORT_DATE"] = current_day.isoformat()
                    reports.append(report)

                time.sleep(1.1)

            except Exception as exc:
                print(
                    f"Delivery report unavailable for "
                    f"{current_day}: {exc}"
                )

        current_day -= timedelta(days=1)

    if len(reports) < required_sessions:
        raise RuntimeError(
            f"Required {required_sessions} previous NSE delivery "
            f"sessions; obtained only {len(reports)}. "
            "Do not bypass the delivery filter."
        )

    return reports


def apply_delivery_filter(
    candidates,
    asof_date,
    symbol_col="TckrSymb",
    series_col="SctySrs",
    minimum_average=60.0,
):
    """
    Returns:
      qualified: candidates with 5-session average delivery >= threshold
      audit: per-symbol delivery statistics for review

    Missing/incomplete official data does not pass the filter.
    """
    if symbol_col not in candidates.columns:
        raise KeyError(
            f"Symbol column '{symbol_col}' missing. "
            f"Available columns: {list(candidates.columns)}"
        )

    reports = get_previous_delivery_sessions(asof_date, 5)

    daily_frames = []

    for report in reports:
        report = report.copy()

        report["SYMBOL"] = report["SYMBOL"].astype(str).str.strip().str.upper()
        report["SERIES"] = report["SERIES"].astype(str).str.strip().str.upper()

        report["DELIV_PER"] = pd.to_numeric(
            report["DELIV_PER"].astype(str).str.strip(),
            errors="coerce",
        )

        daily_frames.append(
            report[["SYMBOL", "SERIES", "REPORT_DATE", "DELIV_PER"]]
        )

    delivery = pd.concat(daily_frames, ignore_index=True)

    delivery = delivery.dropna(subset=["DELIV_PER"])
    delivery = delivery[
        delivery["DELIV_PER"].between(0, 100, inclusive="both")
    ]

    delivery_stats = (
        delivery.groupby(["SYMBOL", "SERIES"], as_index=False)
        .agg(
            DeliverySessions=("DELIV_PER", "count"),
            AvgDelivery5D=("DELIV_PER", "mean"),
            LatestDeliveryPct=("DELIV_PER", "last"),
        )
    )

    work = candidates.copy()
    work["_SYMBOL_KEY"] = (
        work[symbol_col].astype(str).str.strip().str.upper()
    )

    if series_col in work.columns:
        work["_SERIES_KEY"] = (
            work[series_col].astype(str).str.strip().str.upper()
        )
        work = work.merge(
            delivery_stats,
            left_on=["_SYMBOL_KEY", "_SERIES_KEY"],
            right_on=["SYMBOL", "SERIES"],
            how="left",
        )
    else:
        # If series is absent, require one unambiguous symbol match.
        unique_symbols = delivery_stats.groupby("SYMBOL").size()
        delivery_stats = delivery_stats[
            delivery_stats["SYMBOL"].map(unique_symbols).eq(1)
        ]
        work = work.merge(
            delivery_stats,
            left_on="_SYMBOL_KEY",
            right_on="SYMBOL",
            how="left",
        )

    work["DeliveryStatus"] = "WAIT_FOR_DATA"
    valid = (
        work["DeliverySessions"].eq(5)
        & work["AvgDelivery5D"].notna()
    )
    work.loc[valid, "DeliveryStatus"] = "FILTERED_OUT"
    work.loc[
        valid & work["AvgDelivery5D"].ge(minimum_average),
        "DeliveryStatus",
    ] = "PASS_60_PERCENT"

    audit = work.copy()
    qualified = work[work["DeliveryStatus"] == "PASS_60_PERCENT"].copy()

    qualified = qualified.drop(
        columns=["_SYMBOL_KEY", "_SERIES_KEY", "SYMBOL", "SERIES"],
        errors="ignore",
    )
    audit = audit.drop(
        columns=["_SYMBOL_KEY", "_SERIES_KEY"],
        errors="ignore",
    )

    return qualified, audit
