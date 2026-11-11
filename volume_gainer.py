import os
import io
import zipfile
import time
from functools import wraps

# Lightweight runtime telemetry. Emits machine-readable stage timings to Actions logs.
def _perf_timed(stage_name):
    def decorate(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            started = time.perf_counter()
            outcome = "ok"
            try:
                return func(*args, **kwargs)
            except Exception:
                outcome = "error"
                raise
            finally:
                elapsed = time.perf_counter() - started
                print(f"[PERF] stage={stage_name} elapsed_seconds={elapsed:.3f} outcome={outcome}")
        return wrapped
    return decorate

import requests
import pandas as pd
from delivery_filter import apply_delivery_filter, get_delivery_sessions
from nse_trading_calendar import CalendarCoverageError, calendar_coverage_warnings, is_trading_session, official_session_reason
from delivery_streak_tracker import update_delivery_scan_streak
from delivery_consistency import build_delivery_consistency_report
from delivery_quantity_analysis import build_delivery_quantity_report
from potential_accumulation_analysis import build_potential_accumulation_report
from vcp_observation_analysis import build_vcp_observation_report
from breakout_retest_observation import build_breakout_retest_observation
from track2_full_mainboard import build_track2_full_mainboard_report
from hybrid_watchlists import (
    write_early_hybrid_watchlists,
    write_breakout_ready_watchlist,
    write_confirmed_entry_watchlist,
)
from liquidity_filter import apply_liquidity_filter, MINIMUM_AVG_DAILY_TRADED_VALUE_INR
from fundamental_filter import apply_fundamental_filter, create_fundamental_templates
from fundamental_data_provider import collect_missing_fundamentals
from fii_dii_activity import attach_market_context, write_market_activity
from datetime import datetime, timedelta, timezone
from signal_log import append_signal_log
from signal_outcome_tracker import update_signal_outcomes
from signal_shadow_run import build_mainboard_signal_shadow
from v8_layers_14_41 import (
    monitor_positions,
    run_eod_layers,
    validate_next_day,
    write_layer_status_summary,
)
import sector_data
from main_board_filter import apply_official_main_board_filter
from bottom_detection import write_bottom_detection_report
from sector_data import refresh_sector_inputs
from news_catalyst import (
    collect_catalyst_news,
    send_marathi_telegram,
    write_catalyst_top20_report,
)

# Time the major network/data stages that were previously hidden inside the
# total scanner runtime. These wrappers preserve inputs, outputs, and rules.
get_delivery_sessions = _perf_timed("delivery_reports_fetch")(get_delivery_sessions)
apply_delivery_filter = _perf_timed("delivery_filter_calculation")(apply_delivery_filter)
build_delivery_consistency_report = _perf_timed("delivery_consistency_report")(build_delivery_consistency_report)
update_delivery_scan_streak = _perf_timed("delivery_streak_tracker")(update_delivery_scan_streak)
apply_liquidity_filter = _perf_timed("liquidity_filter_calculation")(apply_liquidity_filter)
collect_missing_fundamentals = _perf_timed("fundamental_data_collection")(collect_missing_fundamentals)
collect_catalyst_news = _perf_timed("news_catalyst_collection")(collect_catalyst_news)
refresh_sector_inputs = _perf_timed("sector_inputs_refresh")(refresh_sector_inputs)
build_potential_accumulation_report = _perf_timed("potential_accumulation_analysis")(build_potential_accumulation_report)
build_vcp_observation_report = _perf_timed("vcp_observation_analysis")(build_vcp_observation_report)

# ============================================================
# NSE V8 MODULE A
# EOD VOLUME + 5D PRIMARY SHORTLIST + RVOL + PRICE/VOLUME + CLV
# + TREND + BREAKOUT/PULLBACK + SUPPORT/RESISTANCE + RELATIVE STRENGTH
# ============================================================

NSE_BASE_URL = "https://nsearchives.nseindia.com/content/cm/"
HISTORY_DAYS = 200  # retain enough EOD sessions for verified 100D/200D resistance
DATA_CACHE_DIR = os.path.join("data", "bhavcopy")
BHAVCOPY_404_CACHE_DAYS = 2
NIFTY_HISTORY_CACHE = os.path.join(DATA_CACHE_DIR, "nifty50_index_history.csv")
NIFTY_HISTORY_MIN_BARS = 50
NIFTY_HISTORY_LOOKBACK_DAYS = 140
YAHOO_NIFTY_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

session = requests.Session()
session.headers.update(HEADERS)

# Official NSE ETF symbols are refreshed at runtime. If NSE's ETF list is
# unavailable, the scanner still excludes mutual-fund-unit ISINs (INF...) and
# AMC scheme rows from the CM bhavcopy so ETF units cannot enter stock ranking.
OFFICIAL_ETF_SYMBOLS: set[str] = set()


def refresh_official_etf_symbols() -> set[str]:
    """Load NSE's official ETF symbol list; safe fallback is handled locally."""
    global OFFICIAL_ETF_SYMBOLS
    try:
        symbols = sector_data._download_official_etf_symbols(session)
        OFFICIAL_ETF_SYMBOLS = {
            str(symbol).strip().upper()
            for symbol in (symbols or set())
            if str(symbol).strip()
        }
        print(f"[UNIVERSE] Official NSE ETF exclusion list: {len(OFFICIAL_ETF_SYMBOLS)} symbols")
    except Exception as exc:
        OFFICIAL_ETF_SYMBOLS = set()
        print(f"[UNIVERSE] Official ETF list unavailable; using ISIN/name fallback: {exc}")
    return OFFICIAL_ETF_SYMBOLS


# ============================================================
# BHAVCOPY DATE INTEGRITY
# ============================================================

def validate_bhavcopy_date(df, expected_date, source="Bhavcopy"):
    """Fail closed unless the file's own business date matches its cache/request date."""
    if df is None or df.empty:
        raise ValueError(f"{source}: empty Bhavcopy")
    date_columns = ("BizDt", "TradDt", "TRADDT", "BUSINESS_DATE", "DATE")
    date_col = next((c for c in date_columns if c in df.columns), None)
    if date_col is None:
        raise ValueError(
            f"{source}: no recognized internal date column; "
            f"available columns={list(df.columns)}"
        )
    parsed = pd.to_datetime(df[date_col], errors="coerce", dayfirst=False).dt.date
    valid_dates = set(parsed.dropna().tolist())
    expected = expected_date.date() if isinstance(expected_date, datetime) else expected_date
    if not valid_dates:
        raise ValueError(f"{source}: internal date column {date_col} has no valid dates")
    if valid_dates != {expected}:
        raise ValueError(
            f"{source}: requested/cache date {expected} does not match "
            f"internal date(s) {sorted(str(d) for d in valid_dates)}"
        )
    try:
        if not is_trading_session(expected):
            raise ValueError(
                f"{source}: {expected} is not an official NSE equity trading session "
                f"({official_session_reason(expected)})"
            )
    except CalendarCoverageError as exc:
        raise ValueError(f"{source}: {exc}") from exc
    return df


# ============================================================
# NSE BHAVCOPY DOWNLOAD
# ============================================================

def download_bhavcopy(date_obj):

    date_str = date_obj.strftime("%Y%m%d")
    cache_path = os.path.join(
        DATA_CACHE_DIR,
        f"bhavcopy_{date_str}.csv"
    )

    os.makedirs(DATA_CACHE_DIR, exist_ok=True)
    not_found_path = os.path.join(
        DATA_CACHE_DIR,
        f"bhavcopy_{date_str}.not_found"
    )

    cache_cutoff = (
        datetime.now().date()
        - timedelta(days=BHAVCOPY_404_CACHE_DAYS)
    )

    if (
        os.path.exists(not_found_path)
        and date_obj.date() <= cache_cutoff
    ):

        print(
            f"Bhavcopy 404 cache hit: "
            f"{date_obj.strftime('%Y-%m-%d')} "
            "(no NSE file; skipping request)"
        )

        return None

    if os.path.exists(cache_path):

        try:

            cached = pd.read_csv(cache_path)
            validate_bhavcopy_date(cached, date_obj.date(), source=f"Cache {cache_path}")

            if len(cached) > 0:
                print(
                    f"Bhavcopy cache hit: "
                    f"{date_obj.strftime('%Y-%m-%d')}"
                )
                return cached

        except Exception as e:

            print(
                f"Bhavcopy cache read error for "
                f"{date_str}: {e}"
            )

    url = (
        f"{NSE_BASE_URL}"
        f"BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
    )

    print("\n" + "-" * 60)
    print(
        f"Downloading NSE Bhavcopy: "
        f"{date_obj.strftime('%Y-%m-%d')}"
    )
    print(f"URL: {url}")

    try:

        response = session.get(
            url,
            timeout=30
        )

        print(
            f"HTTP status: "
            f"{response.status_code}"
        )

        print(
            f"Response size: "
            f"{len(response.content)} bytes"
        )

        if response.status_code == 404:

            if date_obj.date() <= cache_cutoff:

                with open(
                    not_found_path,
                    "w",
                    encoding="utf-8"
                ) as marker:
                    marker.write("HTTP 404")

                print(
                    f"Cached NSE 404 for "
                    f"{date_obj.strftime('%Y-%m-%d')}; "
                    "future runs will skip this old date."
                )

            else:

                print(
                    "Recent date returned HTTP 404; "
                    "leaving it uncached in case NSE is delayed."
                )

            return None

        if response.status_code != 200:
            return None

        with zipfile.ZipFile(
            io.BytesIO(response.content)
        ) as z:

            csv_files = [
                name
                for name in z.namelist()
                if name.lower().endswith(".csv")
            ]

            if not csv_files:
                print(
                    "CSV file not found inside ZIP."
                )
                return None

            csv_name = csv_files[0]

            print(
                f"Extracting CSV: "
                f"{csv_name}"
            )

            with z.open(csv_name) as f:
                df = pd.read_csv(f)

        if len(df) > 0:
            # Never persist a response under a date unless the CSV confirms it.
            validate_bhavcopy_date(df, date_obj.date(), source=f"Downloaded {url}")
            df.to_csv(cache_path, index=False)

        print(
            f"Rows downloaded: {len(df)}"
        )

        print(
            f"Columns: {list(df.columns)}"
        )

        return df

    except Exception as e:

        print(
            f"Download error: {e}"
        )

        return None


# ============================================================
# CLEAN EQUITY DATA
# ============================================================

@_perf_timed("prepare_equity_data")
def prepare_equity_data(df, etf_symbols=None):

    required = [
        "TckrSymb",
        "OpnPric",
        "HghPric",
        "LwPric",
        "ClsPric",
        "PrvsClsgPric",
        "TtlTradgVol",
    ]

    for col in required:

        if col not in df.columns:

            raise ValueError(
                f"Required column missing: {col}"
            )

    data = df.copy()

    numeric_cols = [
        "OpnPric",
        "HghPric",
        "LwPric",
        "ClsPric",
        "PrvsClsgPric",
        "TtlTradgVol",
    ]

    for col in numeric_cols:

        data[col] = pd.to_numeric(
            data[col],
            errors="coerce"
        )

    data = data[
        data["TckrSymb"].notna()
        & data["ClsPric"].notna()
        & data["TtlTradgVol"].notna()
    ].copy()

    data = data[
        (data["ClsPric"] > 0)
        & (data["TtlTradgVol"] >= 0)
    ].copy()

    if "SctySrs" in data.columns:
        # The source file is a securities bhavcopy, not a pure common-stock list.
        # Always apply the configured listed-equity series allowlist; never fall
        # back to all instruments when the allowlist returns zero rows.
        allowed_series = {"EQ", "BE", "SM", "ST", "SZ"}
        data["SctySrs"] = data["SctySrs"].astype(str).str.strip().str.upper()
        before_series_filter = len(data)
        data = data[data["SctySrs"].isin(allowed_series)].copy()
        print(
            f"[UNIVERSE] Listed-equity series filter: {len(data)}/{before_series_filter} rows retained."
        )

    # CM bhavcopy can mark ETF units as STK/EQ. Exclude them before ranking:
    # (1) official NSE ETF symbols, (2) Indian mutual-fund ISIN prefix INF,
    # and (3) AMC scheme names such as "MIRAEAMC - BANKPSU". The latter two
    # are conservative fallbacks if NSE's ETF CSV returns HTTP 403.
    official_etfs = OFFICIAL_ETF_SYMBOLS if etf_symbols is None else {
        str(symbol).strip().upper() for symbol in (etf_symbols or set())
    }
    symbol_text = data["TckrSymb"].astype(str).str.strip().str.upper()
    etf_mask = symbol_text.isin(official_etfs)

    if "ISIN" in data.columns:
        isin_text = data["ISIN"].fillna("").astype(str).str.strip().str.upper()
        etf_mask = etf_mask | isin_text.str.startswith("INF")

    if "FinInstrmNm" in data.columns:
        instrument_name = data["FinInstrmNm"].fillna("").astype(str)
        etf_mask = etf_mask | instrument_name.str.contains(
            r"\bAMC\s*-\s*", case=False, regex=True, na=False
        )

    excluded_etfs = sorted(set(symbol_text[etf_mask].tolist()))
    if excluded_etfs:
        data = data.loc[~etf_mask].copy()
        sample = excluded_etfs[:10]
        suffix = " ..." if len(excluded_etfs) > len(sample) else ""
        print(
            f"[UNIVERSE] Excluded {len(excluded_etfs)} ETF/mutual-fund symbols "
            f"before stock ranking (sample: {sample}{suffix})"
        )
    else:
        print("[UNIVERSE] No ETF-like instruments found by official list/ISIN/name checks.")

    data = data.drop_duplicates(
        subset=["TckrSymb"],
        keep="first"
    )

    previous_close = data["PrvsClsgPric"].where(data["PrvsClsgPric"] != 0)
    data["PriceChangePct"] = ((data["ClsPric"] - previous_close) / previous_close) * 100

    return data


# ============================================================
# FIND LATEST EOD
# ============================================================

@_perf_timed("latest_eod_download_and_validation")
def get_latest_eod():

    print(
        "\nSTEP 1: Searching for latest "
        "NSE EOD Bhavcopy..."
    )

    today = datetime.now().date()

    for i in range(10):

        check_date = today - timedelta(days=i)

        try:
            if not is_trading_session(check_date):
                print(f"[NSE CALENDAR] Skip {check_date}: {official_session_reason(check_date)}")
                continue
        except CalendarCoverageError as exc:
            raise RuntimeError(f"WAIT_FOR_DATA: {exc}") from exc

        print(
            f"Trying date: {check_date}"
        )

        df = download_bhavcopy(
            datetime.combine(
                check_date,
                datetime.min.time()
            )
        )

        if df is not None and len(df) > 0:
            try:
                validate_bhavcopy_date(df, check_date, source="Latest EOD")
            except ValueError as exc:
                print(f"[BHAVCOPY] Rejecting mismatched EOD response: {exc}")
                continue

            print(
                f"Latest available EOD date: "
                f"{check_date}"
            )
            return check_date, df

    raise RuntimeError(
        "Could not find latest NSE EOD Bhavcopy."
    )


# ============================================================
# HISTORICAL DATA
# ============================================================

@_perf_timed("bhavcopy_history_cache_load_and_gap_fill")
def collect_historical_days(
    latest_date,
    days=HISTORY_DAYS,
    max_calendar_days=320,  # approximately 200 NSE sessions plus holidays
):
    """Load the existing Bhavcopy history first; download only genuinely missing dates.

    GitHub Actions restores data/bhavcopy before the scanner starts. Reading the
    dated cache inventory directly avoids walking the calendar and making slow
    NSE requests for dates whose Bhavcopy is already stored.
    """
    print(f"\nSTEP 3: Loading up to {days} prior trading sessions from Bhavcopy cache...")

    os.makedirs(DATA_CACHE_DIR, exist_ok=True)
    cached_files = []
    for filename in os.listdir(DATA_CACHE_DIR):
        if not (filename.startswith("bhavcopy_") and filename.endswith(".csv")):
            continue
        date_text = filename[len("bhavcopy_"):-len(".csv")]
        try:
            cache_date = datetime.strptime(date_text, "%Y%m%d").date()
        except ValueError:
            continue
        if cache_date < latest_date:
            try:
                if is_trading_session(cache_date):
                    cached_files.append((cache_date, os.path.join(DATA_CACHE_DIR, filename)))
                else:
                    print(f"[BHAVCOPY CACHE] Ignoring non-session cache date {cache_date}: {official_session_reason(cache_date)}")
            except CalendarCoverageError as exc:
                raise RuntimeError(f"WAIT_FOR_DATA: {exc}") from exc

    cached_files.sort(key=lambda item: item[0], reverse=True)
    historical_by_date = {}
    # Only dates whose cache file passes content/date validation count as cached.
    # Corrupt or misdated files remain eligible for a fresh download below.
    cached_dates = set()

    # Fast path: consume already-restored CSVs without calling download_bhavcopy.
    for cache_date, cache_path in cached_files:
        if len(historical_by_date) >= days:
            break
        try:
            raw = pd.read_csv(cache_path)
            validate_bhavcopy_date(raw, cache_date, source=f"Historical cache {cache_path}")
            if raw.empty:
                continue
            clean = prepare_equity_data(raw)
            if not clean.empty:
                clean["Date"] = pd.Timestamp(cache_date)
                historical_by_date[cache_date] = clean
                cached_dates.add(cache_date)
        except Exception as exc:
            print(f"[BHAVCOPY CACHE] Invalid cached file {os.path.basename(cache_path)}: {exc}")

    print(
        f"[BHAVCOPY CACHE] Reused {len(historical_by_date)}/{days} required sessions "
        f"from {len(cached_files)} dated cache files."
    )

    # Only if the restored cache is incomplete, request missing official NSE sessions.
    current_date = latest_date - timedelta(days=1)
    attempted_days = 0
    while len(historical_by_date) < days and attempted_days < max_calendar_days:
        attempted_days += 1
        try:
            session_is_open = is_trading_session(current_date)
        except CalendarCoverageError as exc:
            raise RuntimeError(f"WAIT_FOR_DATA: {exc}") from exc
        if session_is_open and current_date not in cached_dates:
            print(
                f"[BHAVCOPY CACHE] Missing session candidate {current_date} | "
                f"have {len(historical_by_date)}/{days}; fetching once."
            )
            raw = download_bhavcopy(datetime.combine(current_date, datetime.min.time()))
            if raw is not None and not raw.empty:
                try:
                    validate_bhavcopy_date(raw, current_date, source="Downloaded historical Bhavcopy")
                    clean = prepare_equity_data(raw)
                    if not clean.empty:
                        clean["Date"] = pd.Timestamp(current_date)
                        historical_by_date[current_date] = clean
                        cached_dates.add(current_date)
                        print(f"Accepted trading day: {current_date}")
                except Exception as exc:
                    print(f"Historical data error for {current_date}: {exc}")
        current_date -= timedelta(days=1)

    historical = [
        historical_by_date[date]
        for date in sorted(historical_by_date)
    ][-days:]

    if len(historical) < days:
        raise RuntimeError(
            f"WAIT_FOR_DATA: only {len(historical)}/{days} historical EOD sessions "
            f"available after cache reuse and {max_calendar_days} calendar-day fallback."
        )

    print(f"[BHAVCOPY CACHE] Historical sessions ready: {len(historical)}/{days}.")
    return historical


# ============================================================
# NIFTY 50 HISTORY CACHE
# ============================================================

def fetch_nifty_index_history(
    start_date,
    end_date
):

    start_ts = int(
        datetime.combine(
            start_date,
            datetime.min.time(),
            tzinfo=timezone.utc
        ).timestamp()
    )

    end_ts = int(
        datetime.combine(
            end_date + timedelta(days=1),
            datetime.min.time(),
            tzinfo=timezone.utc
        ).timestamp()
    )

    response = session.get(
        YAHOO_NIFTY_CHART_URL,
        params={
            "period1": start_ts,
            "period2": end_ts,
            "interval": "1d",
        },
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()
    chart = payload.get("chart", {})
    chart_error = chart.get("error")

    if chart_error:
        raise RuntimeError(
            f"Nifty index history API error: {chart_error}"
        )

    results = chart.get("result") or []

    if not results:
        raise RuntimeError(
            "Nifty index history response was empty."
        )

    data = results[0]
    timestamps = data.get("timestamp") or []
    quote_sets = (
        data.get("indicators", {})
        .get("quote", [])
    )

    if not quote_sets:
        raise RuntimeError(
            "Nifty index close data was missing."
        )

    closes = quote_sets[0].get("close") or []
    rows = []

    for timestamp, close in zip(timestamps, closes):

        if close is None:
            continue

        row_date = datetime.fromtimestamp(
            int(timestamp),
            tz=timezone.utc
        ).date()

        if start_date <= row_date <= end_date:
            rows.append({
                "Date": row_date.isoformat(),
                "NiftyClose": float(close),
            })

    history = pd.DataFrame(rows)

    if history.empty:
        raise RuntimeError(
            "Nifty index history contained no daily closes."
        )

    history["Date"] = pd.to_datetime(
        history["Date"],
        errors="coerce"
    )

    history["NiftyClose"] = pd.to_numeric(
        history["NiftyClose"],
        errors="coerce"
    )

    history = history.dropna(
        subset=["Date", "NiftyClose"]
    )

    history = (
        history
        .drop_duplicates(subset=["Date"], keep="last")
        .sort_values("Date")
        .reset_index(drop=True)
    )

    return history


@_perf_timed("nifty_index_history_cache_and_refresh")
def load_nifty_index_history(latest_date):
    """Load Nifty history without letting an unavailable context feed abort NSE EOD scanning.

    A valid >=50-bar cache may be used when the latest index close is not yet
    published for the current EOD date. The returned frame is then explicitly
    marked stale by diagnostics and market-regime consumers must return
    WAIT_FOR_DATA unless it is aligned to the requested date.
    """
    print("\nSTEP 12: Loading Nifty 50 history and checking cache...")
    os.makedirs(DATA_CACHE_DIR, exist_ok=True)

    cached = pd.DataFrame(columns=["Date", "NiftyClose"])
    if os.path.exists(NIFTY_HISTORY_CACHE):
        try:
            cached = pd.read_csv(NIFTY_HISTORY_CACHE)
            if {"Date", "NiftyClose"}.issubset(cached.columns):
                cached["Date"] = pd.to_datetime(cached["Date"], errors="coerce")
                cached["NiftyClose"] = pd.to_numeric(cached["NiftyClose"], errors="coerce")
                cached = (cached.dropna(subset=["Date", "NiftyClose"])
                          .drop_duplicates(subset=["Date"], keep="last")
                          .sort_values("Date").reset_index(drop=True))
            else:
                cached = pd.DataFrame(columns=["Date", "NiftyClose"])
        except Exception as exc:
            print(f"[NIFTY][CACHE_READ_ERROR] {type(exc).__name__}: {exc}")
            cached = pd.DataFrame(columns=["Date", "NiftyClose"])

    target = pd.Timestamp(latest_date).normalize()
    cached_asof = cached[cached["Date"] <= target] if not cached.empty else cached

    if len(cached_asof) >= NIFTY_HISTORY_MIN_BARS and not cached_asof.empty and cached_asof["Date"].max() == target:
        print(f"[NIFTY][CACHE_HIT] rows={len(cached_asof)} asof={target.date()}")
        return cached_asof.tail(260).reset_index(drop=True)

    fetch_start = (target - pd.Timedelta(days=NIFTY_HISTORY_LOOKBACK_DAYS)).date()
    if len(cached_asof) >= NIFTY_HISTORY_MIN_BARS:
        last_date = cached_asof["Date"].max().date()
        fetch_start = max(fetch_start, (pd.Timestamp(last_date) - pd.Timedelta(days=5)).date())

    print(f"[NIFTY][REFRESH] fetching {fetch_start} to {target.date()}")
    try:
        downloaded = fetch_nifty_index_history(fetch_start, target.date())
        if downloaded is None or downloaded.empty:
            raise RuntimeError("index provider returned no usable closes")
    except Exception as exc:
        if len(cached_asof) >= NIFTY_HISTORY_MIN_BARS:
            last_date = cached_asof["Date"].max().date()
            print(
                f"[NIFTY][STALE_CACHE_FALLBACK] refresh failed "
                f"({type(exc).__name__}: {exc}); using {len(cached_asof)} cached closes "
                f"through {last_date}; market-context fields must be WAIT_FOR_DATA if not aligned."
            )
            return cached_asof.tail(260).reset_index(drop=True)
        raise RuntimeError(
            f"Nifty index history unavailable and cache has only {len(cached_asof)} "
            f"valid closes; at least {NIFTY_HISTORY_MIN_BARS} required. "
            f"Cause: {type(exc).__name__}: {exc}"
        ) from exc

    combined = pd.concat([cached, downloaded], ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"], errors="coerce")
    combined["NiftyClose"] = pd.to_numeric(combined["NiftyClose"], errors="coerce")
    combined = (combined.dropna(subset=["Date", "NiftyClose"])
                .drop_duplicates(subset=["Date"], keep="last")
                .sort_values("Date").tail(260).reset_index(drop=True))

    # Only persist provider response when it actually contains the requested
    # NSE EOD date. Never overwrite a usable cache with a stale/partial result.
    aligned = combined[combined["Date"] <= target]
    if not aligned.empty and aligned["Date"].max() == target and len(aligned) >= NIFTY_HISTORY_MIN_BARS:
        combined.to_csv(NIFTY_HISTORY_CACHE, index=False, date_format="%Y-%m-%d")
        print(f"[NIFTY][CACHE_UPDATED] rows={len(combined)} through={target.date()}")
        return combined

    if len(cached_asof) >= NIFTY_HISTORY_MIN_BARS:
        last_date = cached_asof["Date"].max().date()
        print(
            f"[NIFTY][STALE_CACHE_FALLBACK] provider response lacks exact "
            f"EOD date {target.date()}; preserving cache through {last_date}."
        )
        return cached_asof.tail(260).reset_index(drop=True)

    latest_download_date = aligned["Date"].max().date() if not aligned.empty else "NONE"
    raise RuntimeError(
        f"Nifty history has {len(aligned)} usable closes through {latest_download_date}; "
        f"requested EOD date {target.date()} and need {NIFTY_HISTORY_MIN_BARS}. "
        "No sufficient cache fallback exists."
    )


# ============================================================
# 20D AVERAGE VOLUME
# ============================================================

@_perf_timed("prior_20_session_average_volume")
def calculate_average_volume(historical):
    """Calculate average volume from exactly 20 distinct prior EOD sessions.

    The current EOD session is excluded. A symbol needs one valid non-negative
    volume value in each of the 20 sessions; duplicates and missing rows wait.
    """
    print("\nSTEP 3: Preparing prior-20-session average-volume baseline (RVOL is calculated only after Delivery A/B)...")
    recent = historical[-20:]
    empty = pd.DataFrame(columns=["TckrSymb", "AvgVolume20D", "AvgVolumeSessions"])
    if len(recent) < 20:
        print(f"[RVOL] WAIT_FOR_DATA: only {len(recent)}/20 prior sessions available")
        return empty

    date_flags = ["Date" in frame.columns for frame in recent]
    if any(date_flags):
        if not all(date_flags):
            print("[RVOL] WAIT_FOR_DATA: mixed Date availability in prior-session frames")
            return empty
        session_dates = []
        for frame in recent:
            parsed_dates = pd.to_datetime(frame["Date"], errors="coerce").dropna().dt.date.unique()
            if len(parsed_dates) != 1:
                print("[RVOL] WAIT_FOR_DATA: a prior-session frame has invalid/multiple dates")
                return empty
            session_dates.append(parsed_dates[0])
        if len(set(session_dates)) != 20:
            print("[RVOL] WAIT_FOR_DATA: prior-session frames do not contain 20 distinct dates")
            return empty

    frames = []
    for frame in recent:
        if not {"TckrSymb", "TtlTradgVol"}.issubset(frame.columns):
            frames.append(pd.DataFrame(columns=["TckrSymb", "TtlTradgVol"]))
            continue
        temp = frame[["TckrSymb", "TtlTradgVol"]].copy()
        temp["TckrSymb"] = temp["TckrSymb"].astype(str).str.strip().str.upper()
        duplicate_symbols = set(
            temp.loc[temp["TckrSymb"].duplicated(keep=False), "TckrSymb"].dropna()
        )
        if duplicate_symbols:
            temp = temp[~temp["TckrSymb"].isin(duplicate_symbols)]
        temp["TtlTradgVol"] = pd.to_numeric(temp["TtlTradgVol"], errors="coerce")
        temp = temp.dropna(subset=["TckrSymb", "TtlTradgVol"])
        temp = temp[(temp["TtlTradgVol"] >= 0) & temp["TckrSymb"].ne("")]
        frames.append(temp)

    all_volume = pd.concat(frames, ignore_index=True)
    if all_volume.empty:
        return empty
    summary = all_volume.groupby("TckrSymb")["TtlTradgVol"].agg(
        AvgVolume20D="mean", AvgVolumeSessions="count"
    ).reset_index()
    summary.loc[summary["AvgVolumeSessions"] != 20, "AvgVolume20D"] = float("nan")
    print(
        f"[RVOL] Baselines: {len(summary)} symbols; "
        f"complete 20-session baselines: {(summary['AvgVolumeSessions'] == 20).sum()}"
    )
    return summary

# ============================================================
# RVOL
# ============================================================

@_perf_timed("rvol_calculation")
def calculate_rvol(current, avg_volume):
    print("\nSTEP 5: Calculating RVOL for the de-duplicated Delivery A/B union only...")
    baseline_columns = ["TckrSymb", "AvgVolume20D", "AvgVolumeSessions"]
    if avg_volume is None or avg_volume.empty:
        baseline = pd.DataFrame(columns=baseline_columns)
    else:
        baseline = avg_volume.reindex(columns=baseline_columns).copy()
    # Always use the verified baseline from the prior-20-session calculator.
    # Do not retain stale or partial AvgVolume columns already on current.
    result = current.drop(
        columns=["AvgVolume20D", "AvgVolumeSessions", "RVOL", "RVOLStatus"],
        errors="ignore",
    ).merge(baseline, on="TckrSymb", how="left")
    result["AvgVolumeSessions"] = pd.to_numeric(
        result["AvgVolumeSessions"], errors="coerce"
    ).fillna(0).astype(int)
    current_volume = pd.to_numeric(
        result.get("TtlTradgVol", pd.Series(index=result.index, dtype=float)),
        errors="coerce",
    )
    average_volume = pd.to_numeric(result["AvgVolume20D"], errors="coerce")
    result["RVOL"] = current_volume / average_volume
    result["DailyVolumePct20D"] = result["RVOL"] * 100
    valid_current_volume = current_volume.notna() & current_volume.ge(0)
    result["RVOLStatus"] = (
        (result["AvgVolumeSessions"] == 20)
        & average_volume.notna()
        & average_volume.gt(0)
        & valid_current_volume
        & result["RVOL"].notna()
        & result["RVOL"].map(lambda value: pd.notna(value) and float("-inf") < float(value) < float("inf"))
    ).map({True: "PASS", False: "WAIT_FOR_DATA"})
    print(f"[RVOL] Calculated: {(result['RVOLStatus'] == 'PASS').sum()}; WAIT_FOR_DATA: {(result['RVOLStatus'] == 'WAIT_FOR_DATA').sum()}")
    return result


# ============================================================
# 5D VOLUME
# ============================================================

@_perf_timed("five_day_volume_metrics")
def calculate_5d_volume(
    result,
    historical
):

    print(
        "\nSTEP 5: 5D Volume Analysis / descriptive pattern metrics..."
    )

    recent = historical[-5:]

    volume_map = {}

    for df in recent:

        for _, row in df.iterrows():

            symbol = row["TckrSymb"]

            volume_map.setdefault(
                symbol,
                []
            ).append(
                row["TtlTradgVol"]
            )

    low_days = []
    patterns = []

    avg_map = dict(
        zip(
            result["TckrSymb"],
            result["AvgVolume20D"]
        )
    )

    for symbol in result["TckrSymb"]:

        vols = volume_map.get(
            symbol,
            []
        )

        avg = avg_map.get(
            symbol
        )

        if (
            avg is None
            or pd.isna(avg)
            or avg <= 0
        ):

            low_days.append(0)
            patterns.append(
                "Insufficient"
            )

            continue

        lows = sum(
            1
            for v in vols
            if v < avg
        )

        low_days.append(lows)

        if len(vols) < 5:

            patterns.append(
                "Insufficient"
            )

        else:

            first_two = (
                sum(vols[:2]) / 2
            )

            last_two = (
                sum(vols[-2:]) / 2
            )

            current = vols[-1]

            if (
                first_two > 0
                and last_two
                < first_two * 0.80
                and current
                > avg * 1.20
            ):

                patterns.append(
                    "Contraction -> Expansion"
                )

            elif (
                last_two
                < first_two * 0.80
            ):

                patterns.append(
                    "Contraction"
                )

            elif (
                last_two
                > first_two * 1.20
            ):

                patterns.append(
                    "Expansion"
                )

            else:

                patterns.append(
                    "Mixed"
                )

    result["LowVolumeDays5D"] = low_days

    result["LowVolumePct5D"] = (
        result["LowVolumeDays5D"]
        / 5
    ) * 100

    result["VolumePattern5D"] = patterns

    result["LowVolume60Pass"] = (
        result["LowVolumeDays5D"] >= 3
    )

    return result


def prepare_primary_shortlist(result, eod_date):
    """Legacy volume-history diagnostic helper; not the production eligibility path.

    Production eligibility is Delivery Category A OR B over the 30-day report
    window. RVOL is classified after Delivery and does not reject <=1.5 rows.
    This helper only labels history completeness for its callers.
    RVOL is classification only; it is not an eligibility filter. Delivery A/B uses
    all valid distinct reports in the 30-calendar-day window (minimum five).
    A 3-of-5 low-volume rule is NOT used as a filter. Five-session volume-pattern
    and prior-20-session baseline data are still validated for reliable analysis.
    Incomplete history remains WAIT_FOR_DATA.
    """
    if result is None or result.empty:
        print("[PRIMARY SHORTLIST] No rows available after 5-day volume analysis.")
        return result.copy() if isinstance(result, pd.DataFrame) else pd.DataFrame()

    frame = result.copy()
    avg_sessions = pd.to_numeric(
        frame.get("AvgVolumeSessions", pd.Series(index=frame.index, dtype=float)),
        errors="coerce",
    )
    pattern = frame.get(
        "VolumePattern5D", pd.Series("Insufficient", index=frame.index)
    ).astype(str)
    enough_5d = pattern.ne("Insufficient")
    enough_20d = avg_sessions.eq(20)
    complete = enough_5d & enough_20d

    # Keep legacy audit columns for compatibility, but do not use low-volume
    # day counts as a filter or as a required setup condition.
    frame["LowVolume60Pass"] = pd.NA
    frame["LowVolumeRuleStatus"] = "NOT_USED_DELIVERY_PERCENTAGE_IS_THE_REQUIRED_VOLUME_SELECTION_GATE"
    frame["PrimaryShortlistStatus"] = [
        "PASS" if is_complete else "WAIT_FOR_DATA" for is_complete in complete
    ]
    frame["PrimaryShortlistReason"] = [
        "PASS_RVOL_DELIVERY_CATEGORY_A_AND_COMPLETE_5D_AND_PRIOR_20D_HISTORY"
        if is_complete else "WAIT_INSUFFICIENT_5D_OR_PRIOR_20D_VOLUME_HISTORY"
        for is_complete in complete
    ]

    audit_cols = [
        col for col in [
            "TckrSymb", "AvgVolumeSessions", "LowVolumeDays5D", "LowVolumePct5D",
            "VolumePattern5D", "LowVolume60Pass", "LowVolumeRuleStatus",
            "PrimaryShortlistStatus", "PrimaryShortlistReason",
        ] if col in frame.columns
    ]
    audit = frame[audit_cols].copy()
    audit.insert(0, "EODDate", str(eod_date))
    primary = frame.loc[complete].copy()

    os.makedirs(os.path.join("data", "reports"), exist_ok=True)
    audit_path = os.path.join(
        "data", "reports",
        f"v8_primary_shortlist_5d_volume_{pd.Timestamp(eod_date).strftime('%Y%m%d')}.csv",
    )
    audit.to_csv(audit_path, index=False)
    print(
        f"[PRIMARY SHORTLIST] Eligible with complete history={len(primary)}; "
        f"WAIT_FOR_DATA={int((~complete).sum())}. "
        "Production flow applies Delivery A OR B first; RVOL is classification only and does not reject low-RVOL candidates. "
        f"Audit: {audit_path}"
    )
    return primary


def classify_rvol_for_delivery_candidates(result, eod_date, minimum_rvol=1.5):
    """Classify every Delivery-qualified stock by RVOL without rejecting low-RVOL rows.

    Delivery is the eligibility gate. RVOL > threshold is the high-volume
    observation group; RVOL <= threshold is retained as a separate group.
    Missing/invalid RVOL remains WAIT_FOR_DATA but is also retained for audit
    and downstream non-RVOL checks.
    """
    if result is None or result.empty:
        return result.copy() if isinstance(result, pd.DataFrame) else pd.DataFrame()

    frame = result.copy()
    frame["RVOL"] = pd.to_numeric(
        frame.get("RVOL", pd.Series(index=frame.index, dtype=float)),
        errors="coerce",
    )
    if "RVOLStatus" not in frame.columns:
        frame["RVOLStatus"] = "WAIT_FOR_DATA"
    frame["RVOLThreshold"] = float(minimum_rvol)

    def _classify(row):
        value = row.get("RVOL")
        if str(row.get("RVOLStatus", "")).upper() != "PASS" or pd.isna(value):
            return "WAIT_FOR_DATA"
        return "HIGH_RVOL_GT_1_5" if float(value) > float(minimum_rvol) else "LOW_RVOL_LE_1_5"

    frame["RVOLBand"] = frame.apply(_classify, axis=1)
    frame["RVOLThresholdStatus"] = frame["RVOLBand"].map({
        "HIGH_RVOL_GT_1_5": "PASS_RVOL_GT_1_5",
        "LOW_RVOL_LE_1_5": "INFO_RVOL_LE_1_5",
        "WAIT_FOR_DATA": "WAIT_FOR_DATA",
    })
    frame = frame.sort_values(
        "RVOL", ascending=False, na_position="last", kind="mergesort"
    ).reset_index(drop=True)
    high_mask = frame["RVOLBand"].eq("HIGH_RVOL_GT_1_5")
    frame["RVOLRank"] = pd.NA
    frame.loc[high_mask, "RVOLRank"] = range(1, int(high_mask.sum()) + 1)
    frame["RVOLRank"] = pd.to_numeric(frame["RVOLRank"], errors="coerce").astype("Int64")
    print(
        f"[RVOL CLASSIFICATION] Delivery-qualified={len(frame)}; "
        f"high(> {minimum_rvol})={int(high_mask.sum())}; "
        f"low(<= {minimum_rvol})={int(frame['RVOLBand'].eq('LOW_RVOL_LE_1_5').sum())}; "
        f"wait={int(frame['RVOLBand'].eq('WAIT_FOR_DATA').sum())}. "
        "No Delivery-qualified stock is rejected by RVOL."
    )
    return frame


def select_rvol_above_threshold(result, eod_date, minimum_rvol=1.5):
    """Legacy diagnostic-only helper that exports the HIGH-RVOL subset.

    Production eligibility is the Delivery A/B union followed by Liquidity;
    RVOL is classification only and this helper is not called as a production gate.
    Missing 20-session baselines stay WAIT_FOR_DATA in the production cohort.
    """
    if result is None or result.empty:
        print("[RVOL HIGH-BAND AUDIT] No candidates available.")
        return result.copy() if isinstance(result, pd.DataFrame) else pd.DataFrame()
    frame = result.copy()
    frame["RVOL"] = pd.to_numeric(frame.get("RVOL", pd.Series(index=frame.index, dtype=float)), errors="coerce")
    if "RVOLStatus" not in frame.columns:
        frame["RVOLStatus"] = "WAIT_FOR_DATA"
    frame["RVOLThreshold"] = float(minimum_rvol)
    frame["RVOLThresholdStatus"] = frame.apply(
        lambda row: "PASS_RVOL_GT_1_5" if str(row.get("RVOLStatus", "")).upper() == "PASS"
        and pd.notna(row.get("RVOL")) and float(row.get("RVOL")) > float(minimum_rvol)
        else ("WAIT_FOR_DATA" if str(row.get("RVOLStatus", "")).upper() != "PASS" or pd.isna(row.get("RVOL")) else "REJECT_RVOL_LE_1_5"),
        axis=1,
    )
    audit_dir = os.path.join("outputs")
    os.makedirs(audit_dir, exist_ok=True)
    audit_path = os.path.join(audit_dir, "v8_rvol_gt_1_5_audit.csv")
    frame.sort_values("RVOL", ascending=False, na_position="last", kind="mergesort").to_csv(audit_path, index=False)
    selected = frame[frame["RVOLThresholdStatus"] == "PASS_RVOL_GT_1_5"].copy()
    selected = selected.sort_values("RVOL", ascending=False, na_position="last", kind="mergesort")
    selected["RVOLRank"] = range(1, len(selected) + 1)
    selected.to_csv(os.path.join(audit_dir, "v8_rvol_gt_1_5_candidates.csv"), index=False)
    print(f"[RVOL HIGH-BAND AUDIT] Rows={len(selected)}; diagnostic subset only, not a production eligibility gate. Audit: {audit_path}")
    return selected


# ============================================================
# PRICE + VOLUME
# ============================================================

@_perf_timed("price_volume_relationship")
def calculate_price_volume_relationship(
    result
):

    print(
        "\nSTEP 7: Price + Volume Relationship..."
    )

    labels = []

    for _, row in result.iterrows():

        price = row["PriceChangePct"]
        rvol = row["RVOL"]

        if (
            price > 0.10
            and rvol >= 1.5
        ):

            label = "Strong Bullish"

        elif (
            price > 0.10
            and rvol < 1.5
        ):

            label = "Weak Bullish"

        elif (
            price < -0.10
            and rvol >= 1.5
        ):

            label = "Selling / Distribution"

        elif (
            price < -0.10
            and rvol < 1.5
        ):

            label = "Normal Pullback"

        else:

            label = (
                "Possible Accumulation/Event"
            )

        labels.append(label)

    result[
        "PriceVolumeRelationship"
    ] = labels

    return result


# ============================================================
# CLV
# ============================================================

@_perf_timed("clv_calculation")
def calculate_clv(result):

    print(
        "\nSTEP 8: Calculating "
        "CLV / Candle Quality..."
    )

    candle_range = (
        result["HghPric"]
        - result["LwPric"]
    )

    result["CLV"] = (
        (
            result["ClsPric"]
            - result["LwPric"]
        )
        / candle_range
    )

    result.loc[
        candle_range <= 0,
        "CLV"
    ] = 0.5

    result["CLV"] = (
        result["CLV"]
        .clip(
            lower=0,
            upper=1
        )
    )

    def clv_label(value):

        if value > 0.75:
            return "Strong"

        elif value >= 0.50:
            return "Good"

        elif value >= 0.25:
            return "Weak"

        return "Very Weak"

    result["CLVQuality"] = (
        result["CLV"].apply(
            clv_label
        )
    )

    print(
        "CLV calculated successfully."
    )

    return result


# ============================================================
# EXPERIMENTAL ACCUMULATION SCORE — NOT APPROVED, NOT BACKTESTED; NON-GATING
# ============================================================

def calculate_accumulation_score(result):
    if result is None or result.empty:
        return result

    scores = []
    for _, row in result.iterrows():
        score = 0.0
        clv = pd.to_numeric(pd.Series([row.get("CLV")]), errors="coerce").iloc[0]
        if pd.notna(clv):
            score += float(clv) * 40.0

        low_days = pd.to_numeric(pd.Series([row.get("LowVolumeDays5D")]), errors="coerce").iloc[0]
        if pd.notna(low_days):
            score += min(float(low_days) / 5.0, 1.0) * 30.0

        price_change = pd.to_numeric(pd.Series([row.get("PriceChangePct")]), errors="coerce").iloc[0]
        if pd.notna(price_change):
            abs_change = abs(float(price_change))
            if abs_change <= 1.0:
                score += 20.0
            elif abs_change <= 3.0:
                score += 10.0

        rvol = pd.to_numeric(pd.Series([row.get("RVOL")]), errors="coerce").iloc[0]
        if pd.notna(rvol) and float(rvol) <= 1.5:
            score += 10.0

        scores.append(round(score, 2))

    result = result.copy()
    result["AccumulationScore"] = scores  # legacy compatibility alias; experimental only
    result["AccumulationStatus"] = result["AccumulationScore"].apply(
        lambda s: "HIGH_ACCUMULATION" if s >= 70 else "MODERATE_ACCUMULATION" if s >= 40 else "LOW_ACCUMULATION"
    )
    result["ExperimentalAccumulationScore"] = result["AccumulationScore"]
    result["ExperimentalAccumulationStatus"] = result["AccumulationStatus"].map(
        lambda value: f"EXPERIMENTAL_NOT_APPROVED_NOT_BACKTESTED_{value}"
    )
    print("[EXPERIMENTAL ACCUMULATION — NOT APPROVED, NOT BACKTESTED] " + str(result["ExperimentalAccumulationStatus"].value_counts().to_dict()))
    return result


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    series,
    period=14
):

    delta = series.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    rs = avg_gain / avg_loss

    rsi = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    return rsi


def classify_rsi_observation(current_rsi, previous_rsi):
    """Return descriptive RSI zone/direction labels only; never an eligibility gate."""
    current = pd.to_numeric(pd.Series([current_rsi]), errors="coerce").iloc[0]
    previous = pd.to_numeric(pd.Series([previous_rsi]), errors="coerce").iloc[0]
    if pd.isna(current):
        return {
            "RSIDirection": "WAIT_FOR_DATA",
            "RSIZone": "WAIT_FOR_DATA",
            "RSIBehaviour": "WAIT_FOR_DATA",
            "RSIRetestStatus": "NOT_EVALUATED",
            "RSIDivergenceStatus": "NOT_EVALUATED",
        }
    if current <= 30:
        zone = "OVERSOLD"
    elif current >= 70:
        zone = "OVERBOUGHT"
    else:
        zone = "NEUTRAL"
    if pd.isna(previous):
        direction = "WAIT_FOR_DATA"
    elif current - previous > 0.5:
        direction = "RISING"
    elif current - previous < -0.5:
        direction = "FALLING"
    else:
        direction = "FLAT"
    if zone == "OVERSOLD":
        behaviour = "OVERSOLD_RECOVERY" if direction == "RISING" else "OVERSOLD_PRESSURE" if direction == "FALLING" else "OVERSOLD"
    elif zone == "OVERBOUGHT":
        behaviour = "OVERBOUGHT_COOLING" if direction == "FALLING" else "OVERBOUGHT_MOMENTUM" if direction == "RISING" else "OVERBOUGHT"
    else:
        behaviour = f"RSI_{direction}" if direction in {"RISING", "FALLING"} else "NEUTRAL"
    return {
        "RSIDirection": direction,
        "RSIZone": zone,
        "RSIBehaviour": behaviour,
        # Retest/divergence are explicitly not asserted until their dedicated,
        # validated detectors are implemented; they remain informational only.
        "RSIRetestStatus": "NOT_EVALUATED",
        "RSIDivergenceStatus": "NOT_EVALUATED",
    }


# ============================================================
# ADX
# ============================================================

def calculate_adx(
    df,
    period=14
):

    high = df["HghPric"]
    low = df["LwPric"]
    close = df["ClsPric"]

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (
        high - prev_close
    ).abs()

    tr3 = (
        low - prev_close
    ).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    up_move = (
        high - prev_high
    )

    down_move = (
        prev_low - low
    )

    plus_dm = pd.Series(
        0.0,
        index=df.index
    )

    minus_dm = pd.Series(
        0.0,
        index=df.index
    )

    plus_condition = (
        (up_move > down_move)
        & (up_move > 0)
    )

    minus_condition = (
        (down_move > up_move)
        & (down_move > 0)
    )

    plus_dm.loc[
        plus_condition
    ] = up_move.loc[
        plus_condition
    ]

    minus_dm.loc[
        minus_condition
    ] = down_move.loc[
        minus_condition
    ]

    atr = tr.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    plus_dm_avg = plus_dm.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    minus_dm_avg = minus_dm.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    plus_di = (
        100
        * plus_dm_avg
        / atr
    )

    minus_di = (
        100
        * minus_dm_avg
        / atr
    )

    denominator = (
        plus_di + minus_di
    )

    dx = (
        100
        * (
            plus_di - minus_di
        ).abs()
        / denominator
    )

    adx = dx.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    return adx


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    df,
    period=14
):

    high = df["HghPric"]
    low = df["LwPric"]
    close = df["ClsPric"]

    prev_close = close.shift(1)

    tr1 = high - low

    tr2 = (
        high - prev_close
    ).abs()

    tr3 = (
        low - prev_close
    ).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = tr.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    return atr


# ============================================================
# TREND
# ============================================================

def prepare_history_by_symbol(
    historical,
    columns=None,
):

    if columns is None:
        columns = [
            "TckrSymb",
            "Date",
            "OpnPric",
            "HghPric",
            "LwPric",
            "ClsPric",
            "TtlTradgVol",
        ]

    frames = [
        frame.loc[:, columns]
        for frame in historical
        if all(column in frame.columns for column in columns)
    ]

    if not frames:
        return pd.DataFrame(columns=columns), {}

    all_history = pd.concat(
        frames,
        ignore_index=True,
        
    )

    all_history["Date"] = pd.to_datetime(
        all_history["Date"],
        errors="coerce",
    )

    all_history = all_history.dropna(
        subset=["TckrSymb", "Date"]
    ).sort_values(
        ["TckrSymb", "Date"],
        kind="mergesort",
    )

    history_by_symbol = {
        symbol: frame.reset_index(drop=True)
        for symbol, frame in all_history.groupby(
            "TckrSymb",
            sort=False,
        )
    }

    return all_history, history_by_symbol

def _classify_ema44_trend(close_value, ema44_value):
    """Classify stock trend solely by latest close versus EMA44."""
    close = pd.to_numeric(pd.Series([close_value]), errors="coerce").iloc[0]
    ema44 = pd.to_numeric(pd.Series([ema44_value]), errors="coerce").iloc[0]
    if pd.isna(close) or pd.isna(ema44) or ema44 <= 0:
        return "WAIT_FOR_DATA"
    if close > ema44:
        return "Bullish (Close > EMA44)"
    if close < ema44:
        return "Bearish (Close < EMA44)"
    return "NEUTRAL (Close = EMA44)"

@_perf_timed("trend_ema_rsi_adx")
def calculate_trend(result, historical):
    """Calculate EMA20/EMA44 and descriptive EMA44 states for screened candidates only.

    EMA44 proximity is informational: NOT_NEAR_EMA44 never rejects a candidate.
    A breakout/breakdown requires an EOD cross plus volume confirmation.
    """
    print("\nSTEP 9: Calculating EMA20 / EMA44 + RSI14 + ADX14...")
    print("Indicators run only for the current screened candidates; EMA44 proximity is not a rejection gate.")

    trend_rows = []
    _, history_by_symbol = prepare_history_by_symbol(historical)
    market_dates = set()
    for raw in historical or []:
        if raw is None or raw.empty or "Date" not in raw.columns:
            continue
        for value in pd.to_datetime(raw["Date"], errors="coerce").dropna():
            market_dates.add(value.date())
    asof_date = max(market_dates) if market_dates else None

    for _, candidate in result.iterrows():
        symbol = str(candidate.get("TckrSymb", "")).strip().upper()
        hist = history_by_symbol.get(symbol)
        missing = {
            "TckrSymb": symbol,
            "EMA20": float("nan"), "EMA44": float("nan"),
            "EMA44DistancePct": float("nan"),
            "EMA44Trend": "WAIT_FOR_DATA",
            "EMA44Position": "WAIT_FOR_DATA",
            "EMA44ProximityStatus": "WAIT_FOR_DATA",
            "EMA44SignalStatus": "WAIT_FOR_DATA",
            "PriceChange5D": float("nan"),
            "RSI14": float("nan"), "RSI14Previous": float("nan"),
            "RSIDirection": "WAIT_FOR_DATA", "RSIZone": "WAIT_FOR_DATA",
            "RSIBehaviour": "WAIT_FOR_DATA", "RSIRetestStatus": "NOT_EVALUATED",
            "RSIDivergenceStatus": "NOT_EVALUATED", "ADX14": float("nan"),
            "TrendClassification": "WAIT_FOR_DATA",
            "TrendDataStatus": "WAIT_FOR_DATA",
        }
        if hist is None or hist.empty or asof_date is None:
            trend_rows.append(missing)
            continue

        hist = hist.copy()
        hist["Date"] = pd.to_datetime(hist["Date"], errors="coerce")
        hist = hist.dropna(subset=["Date"])
        hist = hist[hist["Date"].dt.date.isin(market_dates)].sort_values("Date", kind="mergesort")
        if hist["Date"].dt.date.duplicated().any():
            trend_rows.append(missing)
            continue
        for column in ("ClsPric", "HghPric", "LwPric", "OpnPric", "TtlTradgVol"):
            if column in hist.columns:
                hist[column] = pd.to_numeric(hist[column], errors="coerce")
        symbol_dates = sorted({value.date() for value in hist["Date"]})
        if not symbol_dates or symbol_dates[-1] != asof_date:
            trend_rows.append(missing)
            continue
        expected_symbol_dates = [
            day for day in sorted(market_dates)
            if symbol_dates[0] <= day <= asof_date
        ]
        if (
            len(expected_symbol_dates) < 50
            or symbol_dates != expected_symbol_dates
            or len(hist) < 50
            or hist["ClsPric"].isna().any()
            or not {"HghPric", "LwPric"}.issubset(hist.columns)
            or hist[["HghPric", "LwPric"]].isna().any().any()
        ):
            trend_rows.append(missing)
            continue

        close = hist["ClsPric"]
        hist["EMA20"] = close.ewm(span=20, adjust=False).mean()
        hist["EMA44"] = close.ewm(span=44, adjust=False).mean()
        hist["RSI14"] = calculate_rsi(close, 14)
        hist["ADX14"] = calculate_adx(hist, 14)
        last = hist.iloc[-1]
        prior = hist.iloc[-2]
        current_close = float(last["ClsPric"])
        ema20 = float(last["EMA20"])
        ema44 = float(last["EMA44"])
        rsi = float(last["RSI14"]) if pd.notna(last["RSI14"]) else float("nan")
        previous_rsi = float(hist.iloc[-2]["RSI14"]) if pd.notna(hist.iloc[-2]["RSI14"]) else float("nan")
        rsi_observation = classify_rsi_observation(rsi, previous_rsi)
        adx = float(last["ADX14"]) if pd.notna(last["ADX14"]) else float("nan")
        distance = ((current_close - ema44) / ema44) * 100 if ema44 > 0 else float("nan")
        proximity = "NEAR_EMA44" if pd.notna(distance) and abs(distance) <= 3.0 else "NOT_NEAR_EMA44"
        position = "ABOVE_EMA44" if current_close > ema44 else "BELOW_EMA44" if current_close < ema44 else "AT_EMA44"

        prior_ema44 = float(hist.iloc[-2]["EMA44"])
        ema44_5_sessions_ago = float(hist.iloc[-6]["EMA44"])
        if ema44_5_sessions_ago > 0 and ((ema44 / ema44_5_sessions_ago) - 1) * 100 > 0.10:
            ema44_trend = "RISING"
        elif ema44_5_sessions_ago > 0 and ((ema44 / ema44_5_sessions_ago) - 1) * 100 < -0.10:
            ema44_trend = "FALLING"
        else:
            ema44_trend = "FLAT"

        try:
            prior_close = float(prior["ClsPric"])
            price_change_5d = ((current_close / float(hist.iloc[-6]["ClsPric"])) - 1) * 100
        except (TypeError, ValueError, ZeroDivisionError):
            prior_close, price_change_5d = float("nan"), float("nan")

        rvol = pd.to_numeric(pd.Series([candidate.get("RVOL")]), errors="coerce").iloc[0]
        avg_volume = pd.to_numeric(pd.Series([candidate.get("AvgVolume20D")]), errors="coerce").iloc[0]
        current_volume = pd.to_numeric(pd.Series([candidate.get("TtlTradgVol")]), errors="coerce").iloc[0]
        volume_confirmed = (pd.notna(rvol) and float(rvol) >= 1.2) or (
            pd.notna(current_volume) and pd.notna(avg_volume) and float(avg_volume) > 0
            and float(current_volume) >= float(avg_volume)
        )
        crossed_up = prior_close <= prior_ema44 and current_close > ema44
        crossed_down = prior_close >= prior_ema44 and current_close < ema44
        if crossed_up and volume_confirmed:
            signal = "BULLISH_BREAKOUT"
        elif crossed_down and volume_confirmed:
            signal = "BEARISH_BREAKDOWN"
        elif crossed_up:
            signal = "BULLISH_CROSS_NO_VOLUME_CONFIRMATION"
        elif crossed_down:
            signal = "BEARISH_CROSS_NO_VOLUME_CONFIRMATION"
        elif current_close > ema44:
            signal = "ABOVE_EMA44"
        elif current_close < ema44:
            signal = "BELOW_EMA44"
        else:
            signal = "AT_EMA44"

        # EMA20, RSI14 and ADX14 are supporting metrics only; EMA44 decides trend.
        trend = _classify_ema44_trend(current_close, ema44)

        trend_rows.append({
            "TckrSymb": symbol,
            "EMA20": ema20,
            "EMA44": ema44,
            "EMA44DistancePct": distance,
            "EMA44Trend": ema44_trend,
            "EMA44Position": position,
            "EMA44ProximityStatus": proximity,
            "EMA44SignalStatus": signal,
            "PriceChange5D": price_change_5d,
            "RSI14": rsi,
            "RSI14Previous": previous_rsi,
            **rsi_observation,
            "ADX14": adx,
            "TrendClassification": trend,
            "TrendDataStatus": "COMPLETE",
        })

    trend_columns = [
        "TckrSymb", "EMA20", "EMA44", "EMA44DistancePct", "EMA44Trend",
        "EMA44Position", "EMA44ProximityStatus", "EMA44SignalStatus",
        "PriceChange5D", "RSI14", "RSI14Previous", "RSIDirection", "RSIZone",
        "RSIBehaviour", "RSIRetestStatus", "RSIDivergenceStatus", "ADX14", "TrendClassification",
        "TrendDataStatus",
    ]
    # Empty screened lists are valid (for example, when the mandatory delivery
    # gate is WAIT_FOR_DATA). Keep the merge key even when there are zero rows.
    trend_df = pd.DataFrame(trend_rows, columns=trend_columns)
    result = result.merge(trend_df, on="TckrSymb", how="left")
    print(f"EMA20/EMA44 indicators calculated for {len(trend_df)} screened symbols")
    print("EMA44 proximity is descriptive only; NOT_NEAR_EMA44 does not reject any candidate.")
    return result

# ============================================================
# BREAKOUT / PULLBACK
# ============================================================

@_perf_timed("breakout_pullback")
def calculate_breakout_pullback(result, historical):
    print("\nSTEP 10: Breakout / Pullback Detection...")

    if result is None:
        return pd.DataFrame(columns=[
            "TckrSymb", "BreakoutStatus", "PullbackStatus", "SetupType",
            "BreakoutDataStatus", "PullbackDataStatus",
        ])
    if result.empty:
        empty = result.copy()
        for column in (
            "BreakoutStatus", "PullbackStatus", "SetupType",
            "BreakoutDataStatus", "PullbackDataStatus",
            "High20DDataStatus", "High50DDataStatus", "VolumeBaseline20DStatus",
        ):
            if column not in empty.columns:
                empty[column] = pd.Series(dtype="object")
        return empty

    _, history_by_symbol = prepare_history_by_symbol(historical)
    market_dates = set()
    for raw in historical or []:
        if raw is None or raw.empty or "Date" not in raw.columns:
            continue
        for value in pd.to_datetime(raw["Date"], errors="coerce").dropna():
            market_dates.add(value.date())
    asof_date = max(market_dates) if market_dates else None
    prior_market_dates = sorted(day for day in market_dates if asof_date is not None and day < asof_date)
    rows = []
    seen_candidate_symbols = set()

    def safe_float(value):
        try:
            number = float(value)
            return number if pd.notna(number) and number not in (float("inf"), float("-inf")) else float("nan")
        except (TypeError, ValueError):
            return float("nan")

    for symbol in result["TckrSymb"]:
        symbol_key = str(symbol).strip().upper()
        if symbol_key in seen_candidate_symbols:
            continue
        seen_candidate_symbols.add(symbol_key)
        candidate_rows = result[
            result["TckrSymb"].astype(str).str.strip().str.upper().eq(symbol_key)
        ]
        candidate = candidate_rows.iloc[0] if not candidate_rows.empty else pd.Series(dtype="object")
        hist = history_by_symbol.get(symbol)

        empty_row = {
            "TckrSymb": symbol,
            "RecentSwingHigh": float("nan"),
            "RecentSwingLow": float("nan"),
            "High20D": float("nan"),
            "High50D": float("nan"),
            "ATR14": float("nan"),
            "BreakoutStatus": "WAIT_FOR_DATA",
            "PullbackStatus": "WAIT_FOR_DATA",
            "SetupType": "WAIT_FOR_DATA",
            "CorrectionFromHighPct": float("nan"),
            "SetupRVOL": float("nan"),
            "High20DDataStatus": "WAIT_FOR_DATA",
            "High50DDataStatus": "WAIT_FOR_DATA",
            "VolumeBaseline20DStatus": "WAIT_FOR_DATA",
            "BreakoutDataStatus": "WAIT_FOR_DATA",
            "PullbackDataStatus": "WAIT_FOR_DATA",
        }

        # Twenty complete prior sessions plus the current session are needed
        # for the existing 20D breakout and volume-baseline rules.
        if hist is None or hist.empty or asof_date is None:
            rows.append(empty_row)
            continue

        hist = hist.copy()
        required = {"OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"}
        if not required.issubset(hist.columns) or "Date" not in hist.columns:
            rows.append(empty_row)
            continue
        hist["Date"] = pd.to_datetime(hist["Date"], errors="coerce")
        hist = hist.dropna(subset=["Date"])
        hist = hist[hist["Date"].dt.date.isin(market_dates)].sort_values("Date", kind="mergesort")
        if hist["Date"].dt.date.duplicated().any():
            rows.append(empty_row)
            continue
        for column in required:
            hist[column] = pd.to_numeric(hist[column], errors="coerce")
            hist[column] = hist[column].replace(
                [float("inf"), float("-inf")], float("nan")
            )

        # Ambiguous candidate identity must not multiply rows in the final merge.
        if result["TckrSymb"].astype(str).str.strip().str.upper().eq(
            str(symbol).strip().upper()
        ).sum() != 1:
            rows.append(empty_row)
            continue

        current_rows = hist[hist["Date"].dt.date.eq(asof_date)]
        if len(current_rows) != 1:
            rows.append(empty_row)
            continue
        current = current_rows.iloc[0]
        previous = hist[hist["Date"].dt.date.lt(asof_date)].copy()
        prior20_dates = prior_market_dates[-20:]
        prior50_dates = prior_market_dates[-50:]
        prior20 = previous[previous["Date"].dt.date.isin(prior20_dates)].sort_values("Date")
        prior50 = previous[previous["Date"].dt.date.isin(prior50_dates)].sort_values("Date")

        current_close = safe_float(current["ClsPric"])
        current_open = safe_float(current["OpnPric"])
        current_high = safe_float(current["HghPric"])
        current_low = safe_float(current["LwPric"])
        current_volume = safe_float(current["TtlTradgVol"])
        previous_close = safe_float(prior20.iloc[-1]["ClsPric"]) if len(prior20) == 20 else float("nan")

        high20_values = pd.to_numeric(prior20["HghPric"], errors="coerce")
        low20_values = pd.to_numeric(prior20["LwPric"], errors="coerce")
        volume20_values = pd.to_numeric(prior20["TtlTradgVol"], errors="coerce")
        high50_values = pd.to_numeric(prior50["HghPric"], errors="coerce")

        high20_ready = len(prior20_dates) == 20 and len(prior20) == 20 and high20_values.notna().all()
        low20_ready = len(prior20_dates) == 20 and len(prior20) == 20 and low20_values.notna().all()
        volume20_ready = (
            len(prior20_dates) == 20 and len(prior20) == 20
            and volume20_values.notna().all()
            and (volume20_values >= 0).all()
        )
        high50_ready = (
            len(prior50_dates) == 50 and len(prior50) == 50
            and high50_values.notna().all()
            and (high50_values > 0).all()
        )
        high20_ready = bool(
            high20_ready and (high20_values > 0).all()
            and (low20_values > 0).all()
            and (high20_values >= low20_values).all()
        )

        high20 = float(high20_values.max()) if high20_ready else float("nan")
        high50 = float(high50_values.max()) if high50_ready else float("nan")
        recent_swing_low = float(low20_values.min()) if low20_ready else float("nan")
        previous_avg_volume = float(volume20_values.mean()) if volume20_ready else float("nan")

        volume_baseline_ready = (
            pd.notna(previous_avg_volume) and previous_avg_volume > 0
            and pd.notna(current_volume) and current_volume >= 0
        )
        current_rvol = current_volume / previous_avg_volume if volume_baseline_ready else float("nan")

        candle_range = current_high - current_low if pd.notna(current_high) and pd.notna(current_low) else float("nan")
        clv = (
            (current_close - current_low) / candle_range
            if pd.notna(candle_range) and candle_range > 0 and pd.notna(current_close)
            else float("nan")
        )

        atr_ohlc = hist[["OpnPric", "HghPric", "LwPric", "ClsPric"]]
        atr_ready = (
            len(hist) == len(market_dates)
            and atr_ohlc.notna().all().all()
            and (atr_ohlc > 0).all().all()
            and (hist["HghPric"] >= hist["LwPric"]).all()
            and (hist["HghPric"] >= hist[["OpnPric", "ClsPric"]].max(axis=1)).all()
            and (hist["LwPric"] <= hist[["OpnPric", "ClsPric"]].min(axis=1)).all()
        )
        atr_series = calculate_atr(hist, 14) if atr_ready else pd.Series(dtype="float64")
        atr = safe_float(atr_series.iloc[-1]) if len(atr_series) else float("nan")

        current_candle_valid = (
            all(pd.notna(value) and value > 0 for value in (
                current_open, current_high, current_low, current_close
            ))
            and current_high >= current_low
            and current_high >= max(current_open, current_close)
            and current_low <= min(current_open, current_close)
            and pd.notna(current_volume) and current_volume >= 0
        )
        common_breakout_data_ready = (
            current_candle_valid and pd.notna(current_rvol)
            and pd.notna(clv) and pd.notna(current_high) and pd.notna(current_low)
        )
        breakout20_ready = bool(high20_ready and common_breakout_data_ready)
        breakout50_ready = bool(high50_ready and common_breakout_data_ready)

        if breakout20_ready and breakout50_ready:
            breakout_data_status = "COMPLETE"
        elif breakout20_ready or breakout50_ready:
            breakout_data_status = "PARTIAL_DATA"
        else:
            breakout_data_status = "WAIT_FOR_DATA"

        breakout = False
        breakout_status = "WAIT_FOR_DATA"
        if breakout20_ready or breakout50_ready:
            # Preserve the existing V8 breakout thresholds exactly.
            if breakout20_ready and current_close > high20 and current_rvol >= 2.0 and clv > 0.75:
                breakout = True
            elif breakout50_ready and current_close > high50 and current_rvol >= 1.5 and clv > 0.75:
                breakout = True

            if (
                breakout20_ready and breakout50_ready
                and current_close > high20 and current_close > high50
                and current_rvol >= 2.0 and clv > 0.75
            ):
                breakout_status = "Strong Breakout"
            elif breakout:
                breakout_status = "Breakout"
            elif breakout20_ready and current_close >= high20 * 0.98 and current_rvol >= 1.2:
                breakout_status = "Near Breakout"
            else:
                breakout_status = "No Breakout"

        ema20_value = safe_float(candidate.get("EMA20"))
        ema44_value = safe_float(candidate.get("EMA44"))
        trend_text = str(candidate.get("TrendClassification", "WAIT_FOR_DATA"))
        low_volume_days = safe_float(candidate.get("LowVolumeDays5D"))

        correction_from_high = (
            (high20 - current_close) / high20 * 100.0
            if high20_ready and high20 > 0 and pd.notna(current_close)
            else float("nan")
        )
        pullback_inputs_ready = (
            common_breakout_data_ready
            and pd.notna(current_open) and pd.notna(previous_close)
            and pd.notna(correction_from_high)
            and (pd.notna(ema20_value) or pd.notna(ema44_value))
            and pd.notna(low_volume_days)
            and trend_text not in ("WAIT_FOR_DATA", "Insufficient Data", "nan", "")
        )

        near_ema20 = (
            pd.notna(ema20_value) and ema20_value > 0
            and abs(current_close - ema20_value) / ema20_value <= 0.03
        )
        near_ema44 = (
            pd.notna(ema44_value) and ema44_value > 0
            and abs(current_close - ema44_value) / ema44_value <= 0.03
        )
        controlled_pullback = 1.0 <= correction_from_high <= 15.0 if pd.notna(correction_from_high) else False
        bullish_reversal_candle = (
            pd.notna(current_open) and pd.notna(previous_close) and pd.notna(clv)
            and current_close > current_open and current_close > previous_close and clv > 0.50
        )

        if not pullback_inputs_ready:
            pullback_status = "WAIT_FOR_DATA"
            pullback_data_status = "WAIT_FOR_DATA"
        else:
            pullback_data_status = "COMPLETE"
            pullback_structure = (
                ("Bullish" in trend_text)
                and controlled_pullback
                and (near_ema20 or near_ema44)
                and current_rvol <= 1.5
            )
            # Preserve the existing 3-of-5 low-volume and bullish-candle rule.
            if pullback_structure and int(low_volume_days) >= 3 and bullish_reversal_candle:
                pullback_status = "Strong Pullback"
            elif controlled_pullback and (near_ema20 or near_ema44):
                pullback_status = "Possible Pullback"
            else:
                pullback_status = "No Pullback"

        if breakout_status in ("Strong Breakout", "Breakout"):
            setup_type = "Breakout"
        elif pullback_status == "Strong Pullback":
            setup_type = "Pullback"
        elif breakout_status == "Near Breakout":
            setup_type = "Pre-Breakout"
        elif pullback_status == "Possible Pullback":
            setup_type = "Possible Pullback"
        elif breakout_status == "WAIT_FOR_DATA" or pullback_status == "WAIT_FOR_DATA":
            setup_type = "WAIT_FOR_DATA"
        else:
            setup_type = "No Clear Setup"

        rows.append({
            "TckrSymb": symbol,
            "RecentSwingHigh": high20,
            "RecentSwingLow": recent_swing_low,
            "High20D": high20,
            "High50D": high50,
            "ATR14": atr,
            "BreakoutStatus": breakout_status,
            "PullbackStatus": pullback_status,
            "SetupType": setup_type,
            "CorrectionFromHighPct": correction_from_high,
            "SetupRVOL": current_rvol,
            "High20DDataStatus": "COMPLETE" if high20_ready else "WAIT_FOR_DATA",
            "High50DDataStatus": "COMPLETE" if high50_ready else "WAIT_FOR_DATA",
            "VolumeBaseline20DStatus": "COMPLETE" if volume_baseline_ready else "WAIT_FOR_DATA",
            "BreakoutDataStatus": breakout_data_status,
            "PullbackDataStatus": pullback_data_status,
        })

    setup_columns = [
        "TckrSymb", "RecentSwingHigh", "RecentSwingLow", "High20D", "High50D",
        "ATR14", "BreakoutStatus", "PullbackStatus", "SetupType",
        "CorrectionFromHighPct", "SetupRVOL", "High20DDataStatus",
        "High50DDataStatus", "VolumeBaseline20DStatus",
        "BreakoutDataStatus", "PullbackDataStatus",
    ]
    setup_df = pd.DataFrame(rows, columns=setup_columns)
    return result.merge(setup_df, on="TckrSymb", how="left")




# ============================================================
# STEP 11 / SUPPORT & RESISTANCE
# ============================================================

@_perf_timed("support_resistance")
def calculate_support_resistance(result, historical):
    print("\nSTEP 11: Support / Resistance Detection...")

    sr_columns = [
        "TckrSymb", "PDH", "PDL", "PWH", "PWL", "SR20DHigh", "SR50DHigh",
        "SR100DHigh", "SR200DHigh", "SRSwingHigh", "SRSwingLow",
        "SRSupport", "SRResistance", "BreakoutLevel", "EntryZoneLow",
        "EntryZoneHigh", "SRStatus", "SRDataStatus",
        "SR20DDataStatus", "SR50DDataStatus", "SR100DDataStatus",
        "SR200DDataStatus", "PreviousDayDataStatus",
    ]
    if result is None:
        return pd.DataFrame(columns=sr_columns)
    if result.empty:
        empty = result.copy()
        for column in sr_columns:
            if column not in empty.columns:
                empty[column] = pd.Series(dtype="object")
        return empty

    all_history, history_by_symbol = prepare_history_by_symbol(historical)
    required_history_columns = {
        "TckrSymb", "Date", "OpnPric", "HghPric", "LwPric", "ClsPric"
    }
    if (
        all_history is None or all_history.empty
        or not required_history_columns.issubset(all_history.columns)
    ):
        rows = []
        for symbol in result["TckrSymb"].drop_duplicates():
            rows.append({
                "TckrSymb": symbol, "PDH": float("nan"), "PDL": float("nan"),
                "PWH": float("nan"), "PWL": float("nan"), "SR20DHigh": float("nan"),
                "SR50DHigh": float("nan"), "SR100DHigh": float("nan"),
                "SR200DHigh": float("nan"), "SRSwingHigh": float("nan"),
                "SRSwingLow": float("nan"), "SRSupport": float("nan"),
                "SRResistance": float("nan"), "BreakoutLevel": float("nan"),
                "EntryZoneLow": float("nan"), "EntryZoneHigh": float("nan"),
                "SRStatus": "WAIT_FOR_DATA", "SRDataStatus": "WAIT_FOR_DATA",
                "SR20DDataStatus": "WAIT_FOR_DATA", "SR50DDataStatus": "WAIT_FOR_DATA",
                "SR100DDataStatus": "WAIT_FOR_DATA", "SR200DDataStatus": "WAIT_FOR_DATA",
                "PreviousDayDataStatus": "WAIT_FOR_DATA",
            })
        return result.merge(pd.DataFrame(rows, columns=sr_columns), on="TckrSymb", how="left")

    all_history = all_history.copy()
    all_history["Date"] = pd.to_datetime(all_history["Date"], errors="coerce")
    for column in ("OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"):
        if column in all_history.columns:
            all_history[column] = pd.to_numeric(all_history[column], errors="coerce")
            all_history[column] = all_history[column].replace(
                [float("inf"), float("-inf")], float("nan")
            )
    all_history = all_history.dropna(subset=["Date"])
    unique_dates = sorted({value.date() for value in all_history["Date"]})
    if not unique_dates:
        return result.copy()

    latest_date = unique_dates[-1]
    prior_dates = [day for day in unique_dates if day < latest_date]
    latest_ts = pd.Timestamp(latest_date)
    current_week = (latest_ts - pd.Timedelta(days=latest_ts.weekday())).normalize()
    previous_week_start = (current_week - pd.Timedelta(days=7)).normalize()
    previous_week_end = (current_week - pd.Timedelta(days=1)).normalize()
    previous_week_data = all_history[
        (all_history["Date"] >= previous_week_start)
        & (all_history["Date"] <= previous_week_end)
    ]

    def safe_float(value):
        try:
            number = float(value)
            return number if pd.notna(number) and number not in (float("inf"), float("-inf")) else float("nan")
        except (TypeError, ValueError):
            return float("nan")

    def wait_row(symbol):
        return {
            "TckrSymb": symbol, "PDH": float("nan"), "PDL": float("nan"),
            "PWH": float("nan"), "PWL": float("nan"), "SR20DHigh": float("nan"),
            "SR50DHigh": float("nan"), "SR100DHigh": float("nan"),
            "SR200DHigh": float("nan"), "SRSwingHigh": float("nan"),
            "SRSwingLow": float("nan"), "SRSupport": float("nan"),
            "SRResistance": float("nan"), "BreakoutLevel": float("nan"),
            "EntryZoneLow": float("nan"), "EntryZoneHigh": float("nan"),
            "SRStatus": "WAIT_FOR_DATA", "SRDataStatus": "WAIT_FOR_DATA",
            "SR20DDataStatus": "WAIT_FOR_DATA", "SR50DDataStatus": "WAIT_FOR_DATA",
            "SR100DDataStatus": "WAIT_FOR_DATA", "SR200DDataStatus": "WAIT_FOR_DATA",
            "PreviousDayDataStatus": "WAIT_FOR_DATA",
        }

    rows = []
    seen_candidate_symbols = set()
    for symbol in result["TckrSymb"]:
        symbol_key = str(symbol).strip().upper()
        if symbol_key in seen_candidate_symbols:
            continue
        seen_candidate_symbols.add(symbol_key)
        stock = history_by_symbol.get(symbol)
        if (
            result["TckrSymb"].astype(str).str.strip().str.upper().eq(
                str(symbol).strip().upper()
            ).sum() != 1
        ):
            rows.append(wait_row(symbol))
            continue
        if stock is None or stock.empty:
            rows.append(wait_row(symbol))
            continue

        stock = stock.copy()
        stock["Date"] = pd.to_datetime(stock["Date"], errors="coerce")
        stock = stock.dropna(subset=["Date"])
        stock = stock[stock["Date"].dt.date.isin(unique_dates)].sort_values("Date", kind="mergesort")
        for column in ("OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"):
            if column in stock.columns:
                stock[column] = pd.to_numeric(stock[column], errors="coerce")
        if stock["Date"].dt.date.duplicated().any():
            rows.append(wait_row(symbol))
            continue

        current_rows = stock[stock["Date"].dt.date.eq(latest_date)]
        if len(current_rows) != 1:
            rows.append(wait_row(symbol))
            continue
        current = current_rows.iloc[0]
        current_close = safe_float(current.get("ClsPric"))
        current_open = safe_float(current.get("OpnPric"))
        current_high = safe_float(current.get("HghPric"))
        current_low = safe_float(current.get("LwPric"))
        current_candle_valid = (
            all(pd.notna(value) and value > 0 for value in (
                current_open, current_high, current_low, current_close
            ))
            and current_high >= max(current_open, current_close)
            and current_low <= min(current_open, current_close)
            and current_high >= current_low
        )
        if not current_candle_valid:
            rows.append(wait_row(symbol))
            continue

        previous_rows = stock[stock["Date"].dt.date.lt(latest_date)].copy()
        previous_date = prior_dates[-1] if prior_dates else None
        previous_day_rows = (
            previous_rows[previous_rows["Date"].dt.date.eq(previous_date)]
            if previous_date is not None else previous_rows.iloc[0:0]
        )
        previous_day_ready = (
            len(previous_day_rows) == 1
            and pd.notna(safe_float(previous_day_rows.iloc[0].get("HghPric")))
            and pd.notna(safe_float(previous_day_rows.iloc[0].get("LwPric")))
            and safe_float(previous_day_rows.iloc[0].get("HghPric")) > 0
            and safe_float(previous_day_rows.iloc[0].get("LwPric")) > 0
            and safe_float(previous_day_rows.iloc[0].get("HghPric"))
                >= safe_float(previous_day_rows.iloc[0].get("LwPric"))
        )
        if previous_day_ready:
            pdh = safe_float(previous_day_rows.iloc[0]["HghPric"])
            pdl = safe_float(previous_day_rows.iloc[0]["LwPric"])
        else:
            pdh = pdl = float("nan")

        stock_previous_week = previous_week_data[
            previous_week_data["TckrSymb"].astype(str).str.strip().str.upper().eq(str(symbol).strip().upper())
        ]
        if (
            not stock_previous_week.empty
            and stock_previous_week["Date"].dt.date.duplicated().sum() == 0
            and stock_previous_week[["HghPric", "LwPric"]].notna().all().all()
            and (stock_previous_week[["HghPric", "LwPric"]] > 0).all().all()
            and (stock_previous_week["HghPric"] >= stock_previous_week["LwPric"]).all()
        ):
            pwh = safe_float(stock_previous_week["HghPric"].max())
            pwl = safe_float(stock_previous_week["LwPric"].min())
        else:
            pwh = pwl = float("nan")

        def exact_window(period):
            dates = prior_dates[-period:]
            part = previous_rows[previous_rows["Date"].dt.date.isin(dates)].sort_values("Date")
            complete = (
                len(dates) == period and len(part) == period
                and not part["Date"].dt.date.duplicated().any()
                and part[["HghPric", "LwPric"]].notna().all().all()
                and (part[["HghPric", "LwPric"]] > 0).all().all()
                and (part["HghPric"] >= part["LwPric"]).all()
            )
            return part, complete

        prior20, ready20 = exact_window(20)
        prior50, ready50 = exact_window(50)
        prior100, ready100 = exact_window(100)
        prior200, ready200 = exact_window(200)

        high20 = safe_float(prior20["HghPric"].max()) if ready20 else float("nan")
        low20 = safe_float(prior20["LwPric"].min()) if ready20 else float("nan")
        high50 = safe_float(prior50["HghPric"].max()) if ready50 else float("nan")
        low50 = safe_float(prior50["LwPric"].min()) if ready50 else float("nan")
        high100 = safe_float(prior100["HghPric"].max()) if ready100 else float("nan")
        high200 = safe_float(prior200["HghPric"].max()) if ready200 else float("nan")
        swing_high = high20
        swing_low = low20

        row_match = result[result["TckrSymb"] == symbol]
        ema20 = safe_float(row_match["EMA20"].iloc[0]) if len(row_match) and "EMA20" in row_match.columns else float("nan")
        ema44 = safe_float(row_match["EMA44"].iloc[0]) if len(row_match) and "EMA44" in row_match.columns else float("nan")

        support_candidates = [pdl, pwl, low20, low50, swing_low]
        if pd.notna(ema20) and ema20 > 0:
            support_candidates.append(ema20)
        if pd.notna(ema44) and ema44 > 0:
            support_candidates.append(ema44)
        support_candidates = [
            value for value in support_candidates
            if pd.notna(value) and value > 0 and value <= current_close
        ]
        support = max(support_candidates) if support_candidates else float("nan")

        resistance_candidates = [pdh, pwh, high20, high50, swing_high]
        resistance_candidates = [
            value for value in resistance_candidates
            if pd.notna(value) and value > 0 and value >= current_close
        ]
        resistance = min(resistance_candidates) if resistance_candidates else float("nan")
        if pd.isna(resistance):
            fallback = [
                value for value in [pdh, pwh, high20, high50, swing_high]
                if pd.notna(value) and value > 0
            ]
            if fallback:
                resistance = max(fallback)

        breakout_level = resistance
        if pd.notna(resistance):
            if current_close <= resistance:
                entry_zone_low = resistance * 0.995
                entry_zone_high = resistance * 1.005
            else:
                entry_zone_low = resistance
                entry_zone_high = resistance * 1.01
        else:
            entry_zone_low = support if pd.notna(support) else float("nan")
            entry_zone_high = support if pd.notna(support) else float("nan")

        # Preserve the existing 2% resistance / 3% support proximity rules.
        if pd.isna(support) and pd.isna(resistance):
            sr_status = "WAIT_FOR_DATA"
        elif pd.notna(resistance) and current_close > resistance:
            sr_status = "Above Resistance"
        elif (
            pd.notna(resistance) and resistance > 0
            and (resistance - current_close) / resistance <= 0.02
        ):
            sr_status = "Near Resistance"
        elif (
            pd.notna(support) and support > 0
            and (current_close - support) / current_close <= 0.03
        ):
            sr_status = "Near Support"
        else:
            sr_status = "Between Support/Resistance"

        window_statuses = [ready20, ready50, ready100, ready200]
        any_level = any([
            previous_day_ready, pd.notna(pwh), ready20, ready50, ready100, ready200,
            pd.notna(ema20), pd.notna(ema44),
        ])
        sr_data_status = (
            "COMPLETE" if all(window_statuses) and previous_day_ready
            else "PARTIAL_DATA" if any_level
            else "WAIT_FOR_DATA"
        )

        rows.append({
            "TckrSymb": symbol,
            "PDH": pdh, "PDL": pdl, "PWH": pwh, "PWL": pwl,
            "SR20DHigh": high20, "SR50DHigh": high50,
            "SR100DHigh": high100, "SR200DHigh": high200,
            "SRSwingHigh": swing_high, "SRSwingLow": swing_low,
            "SRSupport": support, "SRResistance": resistance,
            "BreakoutLevel": breakout_level,
            "EntryZoneLow": entry_zone_low, "EntryZoneHigh": entry_zone_high,
            "SRStatus": sr_status, "SRDataStatus": sr_data_status,
            "SR20DDataStatus": "COMPLETE" if ready20 else "WAIT_FOR_DATA",
            "SR50DDataStatus": "COMPLETE" if ready50 else "WAIT_FOR_DATA",
            "SR100DDataStatus": "COMPLETE" if ready100 else "WAIT_FOR_DATA",
            "SR200DDataStatus": "COMPLETE" if ready200 else "WAIT_FOR_DATA",
            "PreviousDayDataStatus": "COMPLETE" if previous_day_ready else "WAIT_FOR_DATA",
        })

    sr_df = pd.DataFrame(rows, columns=sr_columns)
    result = result.merge(sr_df, on="TckrSymb", how="left")
    print("Support / Resistance calculation completed.")
    return result

# ============================================================
# RELATIVE STRENGTH VS NIFTY
# ============================================================

@_perf_timed("relative_strength_vs_nifty")
def calculate_relative_strength_nifty(
    result,
    historical,
    nifty_history,
    latest_date
):

    print(
        "\nSTEP 13: Calculating Relative Strength vs Nifty..."
    )

    all_history = pd.concat(
        historical,
        ignore_index=True
    )

    all_history["Date"] = pd.to_datetime(
        all_history["Date"],
        errors="coerce"
    )

    all_history["ClsPric"] = pd.to_numeric(
        all_history["ClsPric"],
        errors="coerce"
    )

    history_by_symbol = {
        symbol: frame.sort_values("Date")
        for symbol, frame in all_history.groupby("TckrSymb")
    }

    nifty = nifty_history.copy()

    nifty["Date"] = pd.to_datetime(
        nifty["Date"],
        errors="coerce"
    )

    nifty["NiftyClose"] = pd.to_numeric(
        nifty["NiftyClose"],
        errors="coerce"
    )

    nifty = nifty.dropna(
        subset=["Date", "NiftyClose"]
    )

    nifty = (
        nifty[
            nifty["Date"]
            <= pd.Timestamp(latest_date).normalize()
        ]
        .drop_duplicates(
            subset=["Date"],
            keep="last"
        )
        .sort_values("Date")
        .reset_index(drop=True)
    )

    nifty_return_20d = float("nan")
    nifty_aligned = (
        len(nifty) >= 21
        and pd.Timestamp(nifty.iloc[-1]["Date"]).normalize()
        == pd.Timestamp(latest_date).normalize()
    )
    if nifty_aligned:
        nifty_base_close = pd.to_numeric(
            pd.Series([nifty["NiftyClose"].iloc[-21]]), errors="coerce"
        ).iloc[0]
        nifty_last_close = pd.to_numeric(
            pd.Series([nifty["NiftyClose"].iloc[-1]]), errors="coerce"
        ).iloc[0]
        if pd.notna(nifty_base_close) and nifty_base_close > 0 and pd.notna(nifty_last_close):
            nifty_return_20d = ((float(nifty_last_close) / float(nifty_base_close)) - 1) * 100

    if pd.isna(nifty_return_20d):
        print(
            "[NIFTY][RELATIVE_STRENGTH_WAIT_FOR_DATA] "
            f"Need >=21 valid closes ending exactly on {pd.Timestamp(latest_date).date()}; "
            "Nifty 20D return and per-stock relative strength will remain WAIT_FOR_DATA."
        )

    stock_returns = []
    nifty_returns = []
    relative_strengths = []
    classifications = []

    def classify_relative_strength(value):

        if pd.isna(value):
            return "Insufficient Data"

        if value >= 5:
            return "Strong Outperformance"

        if value >= 2:
            return "Outperformance"

        if value > -2:
            return "Market Aligned"

        if value > -5:
            return "Underperformance"

        return "Strong Underperformance"

    for _, row in result.iterrows():

        symbol = row["TckrSymb"]
        current_close = pd.to_numeric(
            pd.Series([row.get("ClsPric")]),
            errors="coerce"
        ).iloc[0]

        stock_return_20d = float("nan")
        relative_strength = float("nan")

        symbol_history = history_by_symbol.get(symbol)

        if (
            symbol_history is not None
            and len(symbol_history) >= 20
            and pd.notna(current_close)
            and current_close > 0
        ):

            base_close = pd.to_numeric(
                symbol_history["ClsPric"].iloc[-20],
                errors="coerce"
            )

            if pd.notna(base_close) and base_close > 0:

                stock_return_20d = (
                    (float(current_close) / float(base_close)) - 1
                ) * 100

                relative_strength = (
                    stock_return_20d
                    - nifty_return_20d
                )

        stock_returns.append(stock_return_20d)
        nifty_returns.append(nifty_return_20d)
        relative_strengths.append(relative_strength)
        classifications.append(
            classify_relative_strength(relative_strength)
        )

    result = result.copy()

    result["StockReturn20D"] = stock_returns
    result["NiftyReturn20D"] = nifty_returns
    result["RelativeStrengthNifty"] = relative_strengths
    result["RSNiftyClassification"] = classifications

    valid_count = int(
        result["RelativeStrengthNifty"].notna().sum()
    )

    print(
        f"Relative Strength calculated for "
        f"{valid_count}/{len(result)} symbols."
    )

    return result


# ============================================================
# V8 CORE CANDIDATE SELECTION — AUDITABLE, NO FORCED FILL
# ============================================================

def write_technical_parameter_audit(candidates, eod_date):
    """Write a compact per-symbol, per-rule technical audit and count summary."""
    detail_columns = [
        "EODDate", "TckrSymb", "CheckOrder", "Parameter", "ObservedValue",
        "RequiredRule", "Status", "Reason", "OverallTechnicalStatus",
        "RSI14", "EMA20", "EMA44", "TrendClassification", "SetupType",
    ]
    detail_rows = []

    def is_missing(value):
        try:
            return bool(pd.isna(value))
        except (TypeError, ValueError):
            return value is None

    def display(value):
        return "WAIT_FOR_DATA" if is_missing(value) else str(value)

    if candidates is not None and not candidates.empty:
        for _, row in candidates.iterrows():
            symbol = str(row.get("TckrSymb", "")).strip().upper()
            if not symbol:
                continue
            check_order = 0
            overall = display(row.get("CoreTechnicalScreenStatus", row.get("CandidateScreenStatus", "WAIT_FOR_DATA")))
            trend = display(row.get("TrendClassification", "WAIT_FOR_DATA"))
            setup = display(row.get("SetupType", "WAIT_FOR_DATA"))
            delivery = display(row.get("DeliveryFilterStatus", "WAIT_FOR_DATA"))
            rvol_status = display(row.get("RVOLStatus", "WAIT_FOR_DATA")).upper()
            rvol = pd.to_numeric(pd.Series([row.get("RVOL")]), errors="coerce").iloc[0]
            clv = pd.to_numeric(pd.Series([row.get("CLV")]), errors="coerce").iloc[0]
            price_change = pd.to_numeric(pd.Series([row.get("PriceChangePct")]), errors="coerce").iloc[0]
            relative_strength = pd.to_numeric(pd.Series([row.get("RelativeStrengthNifty")]), errors="coerce").iloc[0]
            support = pd.to_numeric(pd.Series([row.get("SRSupport")]), errors="coerce").iloc[0]
            resistance = pd.to_numeric(pd.Series([row.get("SRResistance")]), errors="coerce").iloc[0]
            breakout = display(row.get("BreakoutStatus", "WAIT_FOR_DATA"))
            pullback = display(row.get("PullbackStatus", "WAIT_FOR_DATA"))
            price_volume = display(row.get("PriceVolumeRelationship", "WAIT_FOR_DATA"))

            def add(parameter, observed, rule, status, reason):
                nonlocal check_order
                check_order += 1
                detail_rows.append({
                    "EODDate": str(eod_date),
                    "TckrSymb": symbol,
                    "CheckOrder": check_order,
                    "Parameter": parameter,
                    "ObservedValue": observed,
                    "RequiredRule": rule,
                    "Status": status,
                    "Reason": reason,
                    "OverallTechnicalStatus": overall,
                    "RSI14": row.get("RSI14", pd.NA),
                    "EMA20": row.get("EMA20", pd.NA),
                    "EMA44": row.get("EMA44", pd.NA),
                    "TrendClassification": trend,
                    "SetupType": setup,
                })

            delivery_ok = delivery.upper() in {"PASS_GE_60_PERCENT", "PASS_AVG_GE_60_PERCENT"}
            add(
                "Delivery gate",
                delivery,
                "Delivery category A/B must already have PASS status; current pipeline normally requires category B.",
                "PASS" if delivery_ok else ("WAIT_FOR_DATA" if "WAIT" in delivery.upper() else "FAIL"),
                "Delivery passed." if delivery_ok else ("Delivery data/status missing." if "WAIT" in delivery.upper() else "Delivery status is not eligible."),
            )

            rvol_ok = rvol_status == "PASS" and pd.notna(rvol) and float(rvol) > 0
            add(
                "RVOL data check",
                f"status={rvol_status}; RVOL={display(rvol)}",
                "RVOLStatus=PASS and RVOL>0; the earlier universe gate enforces RVOL>1.5.",
                "PASS" if rvol_ok else ("WAIT_FOR_DATA" if rvol_status == "WAIT_FOR_DATA" or pd.isna(rvol) else "FAIL"),
                "RVOL passed upstream." if rvol_ok else "RVOL baseline/status is missing or invalid.",
            )

            setup_ok = setup in {"Breakout", "Pullback"}
            add(
                "Confirmed setup",
                f"SetupType={setup}; BreakoutStatus={breakout}; PullbackStatus={pullback}",
                "SetupType must be exactly Breakout or Pullback; near/possible setups are informational only.",
                "PASS" if setup_ok else ("WAIT_FOR_DATA" if "WAIT" in setup.upper() or "INSUFFICIENT" in setup.upper() else "FAIL"),
                "Confirmed setup selected." if setup_ok else "No confirmed Breakout/Pullback setup; see both raw setup statuses.",
            )

            trend_ok = "Bullish" in trend
            add(
                "Trend",
                trend,
                'Close > EMA44 = BULLISH; Close < EMA44 = BEARISH; Close = EMA44 = NEUTRAL; missing EMA44 = WAIT_FOR_DATA. EMA20/RSI14/ADX14 do not override this classification.',
                "PASS" if trend_ok else ("WAIT_FOR_DATA" if "WAIT" in trend.upper() or "INSUFFICIENT" in trend.upper() else "FAIL"),
                "Latest close is above EMA44." if trend_ok else "Latest close is not above EMA44.",
            )

            if setup == "Breakout":
                clv_threshold = 0.75
                clv_rule = "Breakout CLV must be >0.75."
            elif setup == "Pullback":
                clv_threshold = 0.50
                clv_rule = "Pullback CLV must be >0.50."
            else:
                clv_threshold = None
                clv_rule = "Only evaluated after a confirmed Breakout or Pullback setup; inspect setup statuses and CLV value."
            if clv_threshold is None:
                clv_status, clv_reason = "NOT_EVALUATED", "No confirmed setup selected; candle threshold is conditional."
            elif pd.isna(clv):
                clv_status, clv_reason = "WAIT_FOR_DATA", "CLV is missing."
            elif float(clv) > clv_threshold:
                clv_status, clv_reason = "PASS", "CLV is above the setup-specific threshold."
            else:
                clv_status, clv_reason = "FAIL", "CLV does not exceed the setup-specific threshold."
            add("Candle quality (CLV)", display(clv), clv_rule, clv_status, clv_reason)

            if "Selling / Distribution" in price_volume:
                pv_status, pv_reason = "FAIL", "Price/volume classification is Selling / Distribution."
            elif "WAIT" in price_volume.upper() or "INSUFFICIENT" in price_volume.upper():
                pv_status, pv_reason = "WAIT_FOR_DATA", "Price/volume classification is missing."
            else:
                pv_status, pv_reason = "PASS", "No Selling / Distribution classification."
            add("Price-volume", price_volume, "Must not be Selling / Distribution.", pv_status, pv_reason)

            if pd.isna(relative_strength):
                rs_status, rs_reason = "WAIT_FOR_DATA", "Relative strength is missing."
            elif float(relative_strength) < 0:
                rs_status, rs_reason = "INFO", "Negative relative strength adds a warning/score penalty; it is not a standalone reject."
            else:
                rs_status, rs_reason = "PASS", "Relative strength is non-negative."
            add(
                "Relative strength vs Nifty",
                display(relative_strength),
                "Must be available; negative values are a warning, not a hard rejection.",
                rs_status,
                rs_reason,
            )

            if pd.isna(support) or pd.isna(resistance):
                sr_status, sr_reason = "WAIT_FOR_DATA", "Support or resistance value is missing."
            elif float(support) <= 0 or float(resistance) <= 0:
                sr_status, sr_reason = "FAIL", "Support and resistance must be positive."
            else:
                sr_status, sr_reason = "PASS", "Support and resistance values are available."
            add(
                "Support / resistance",
                f"support={display(support)}; resistance={display(resistance)}",
                "Both support and resistance must be positive and available.",
                sr_status,
                sr_reason,
            )

            if setup == "Breakout":
                breakout_ok = breakout in {"Breakout", "Strong Breakout"}
                positive_close_ok = pd.notna(price_change) and float(price_change) > 0
                status = "PASS" if breakout_ok and positive_close_ok else ("WAIT_FOR_DATA" if pd.isna(price_change) or "INSUFFICIENT" in breakout.upper() else "FAIL")
                reason = "Confirmed breakout and positive close change." if status == "PASS" else "Breakout status must be confirmed and close change must be positive."
                add(
                    "Breakout confirmation",
                    f"BreakoutStatus={breakout}; PriceChangePct={display(price_change)}",
                    "BreakoutStatus=Breakout/Strong Breakout and PriceChangePct>0.",
                    status,
                    reason,
                )
            else:
                status = "NOT_EVALUATED"
                reason = "Breakout-specific check does not apply to this SetupType."
                add("Breakout confirmation", f"BreakoutStatus={breakout}; PriceChangePct={display(price_change)}", "Only evaluated for SetupType=Breakout.", status, reason)

            if setup == "Pullback" or setup == "Possible Pullback":
                pullback_ok = pullback in {"Pullback", "Strong Pullback"}
                status = "PASS" if pullback_ok else ("WAIT_FOR_DATA" if "INSUFFICIENT" in pullback.upper() or "WAIT" in pullback.upper() else "FAIL")
                reason = "Confirmed pullback status." if status == "PASS" else "Possible/no pullback is not confirmed; reversal, volume contraction, EMA proximity and trend conditions must align."
                rule = "PullbackStatus=Pullback/Strong Pullback; current implementation requires controlled 1–15% correction, within 3% of EMA20/EMA44, RVOL<=1.5, >=3/5 low-volume days and bullish reversal candle with CLV>0.50."
                add("Pullback confirmation", f"PullbackStatus={pullback}; LowVolumeDays5D={display(row.get('LowVolumeDays5D'))}", rule, status, reason)
            else:
                add(
                    "Pullback confirmation",
                    f"PullbackStatus={pullback}; LowVolumeDays5D={display(row.get('LowVolumeDays5D'))}",
                    "Only evaluated for Pullback/Possible Pullback setup.",
                    "NOT_EVALUATED",
                    "Pullback-specific check does not apply to this SetupType.",
                )

    details = pd.DataFrame(detail_rows, columns=detail_columns)
    status_order = ["PASS", "FAIL", "WAIT_FOR_DATA", "INFO", "NOT_EVALUATED"]
    summary_rows = []
    if not details.empty:
        for (check_order, parameter), group in details.groupby(["CheckOrder", "Parameter"], sort=True):
            counts = group["Status"].value_counts()
            summary_rows.append({
                "EODDate": str(eod_date),
                "CheckOrder": int(check_order),
                "Parameter": parameter,
                "PassCount": int(counts.get("PASS", 0)),
                "FailCount": int(counts.get("FAIL", 0)),
                "WaitForDataCount": int(counts.get("WAIT_FOR_DATA", 0)),
                "InfoCount": int(counts.get("INFO", 0)),
                "NotEvaluatedCount": int(counts.get("NOT_EVALUATED", 0)),
                "TotalSymbols": int(len(group)),
            })
    summary = pd.DataFrame(summary_rows, columns=[
        "EODDate", "CheckOrder", "Parameter", "PassCount", "FailCount",
        "WaitForDataCount", "InfoCount", "NotEvaluatedCount", "TotalSymbols",
    ])

    os.makedirs("outputs", exist_ok=True)
    os.makedirs(os.path.join("data", "reports"), exist_ok=True)
    details.to_csv("outputs/v8_technical_parameter_audit.csv", index=False)
    summary.to_csv("outputs/v8_technical_parameter_summary.csv", index=False)
    date_suffix = pd.Timestamp(eod_date).strftime("%Y%m%d")
    details.to_csv(os.path.join("data", "reports", f"v8_technical_parameter_audit_{date_suffix}.csv"), index=False)
    summary.to_csv(os.path.join("data", "reports", f"v8_technical_parameter_summary_{date_suffix}.csv"), index=False)
    return details, summary


def select_top20_analysis_candidates(result, eod_date):
    """Annotate liquidity-qualified candidates after the core EOD screens.

    Delivery eligibility is the complete 30-calendar-day Category A OR B union:
    A = average Delivery >=60.00%; B = every valid report day >=60.00%, with at
    least five valid distinct reports. The strict five-session watchlist is separate.
    RVOL is classification only and does not reject low-RVOL candidates. There is
    no Top-N cap; the complete liquidity-qualified cohort proceeds into this analysis.
    Negative relative strength is retained
    as a scoring/ranking warning, not a standalone hard rejection.
    Final sector/news/3+1, risk/reward and chase gates remain in run_eod_layers().
    """
    if result is None or result.empty:
        print("[CANDIDATE SCREEN] No rows available; no candidates selected.")
        empty = result.copy() if isinstance(result, pd.DataFrame) else pd.DataFrame()
        write_technical_parameter_audit(empty, eod_date)
        return empty

    frame = result.copy()
    audit_rows = []
    required_columns = [
        "DeliveryFilterStatus", "RVOLStatus", "RVOL", "SetupType",
        "TrendClassification", "CLV", "PriceVolumeRelationship",
        "RelativeStrengthNifty", "LowVolumeDays5D", "BreakoutStatus",
        "PullbackStatus", "SRSupport", "SRResistance", "PriceChangePct",
    ]

    for col in required_columns:
        if col not in frame.columns:
            frame[col] = pd.NA

    for _, row in frame.iterrows():
        reasons = []
        warnings = []
        symbol = str(row.get("TckrSymb", "")).strip().upper()
        delivery = str(row.get("DeliveryFilterStatus", "WAIT_FOR_DATA")).strip().upper()
        rvol_status = str(row.get("RVOLStatus", "WAIT_FOR_DATA")).strip().upper()
        setup = str(row.get("SetupType", "")).strip()
        trend = str(row.get("TrendClassification", "")).strip()
        pv = str(row.get("PriceVolumeRelationship", "")).strip()
        breakout = str(row.get("BreakoutStatus", "")).strip()
        pullback = str(row.get("PullbackStatus", "")).strip()
        rvol = pd.to_numeric(pd.Series([row.get("RVOL")]), errors="coerce").iloc[0]
        clv = pd.to_numeric(pd.Series([row.get("CLV")]), errors="coerce").iloc[0]
        rs = pd.to_numeric(pd.Series([row.get("RelativeStrengthNifty")]), errors="coerce").iloc[0]
        low_days = pd.to_numeric(pd.Series([row.get("LowVolumeDays5D")]), errors="coerce").iloc[0]
        change = pd.to_numeric(pd.Series([row.get("PriceChangePct")]), errors="coerce").iloc[0]
        support = pd.to_numeric(pd.Series([row.get("SRSupport")]), errors="coerce").iloc[0]
        resistance = pd.to_numeric(pd.Series([row.get("SRResistance")]), errors="coerce").iloc[0]

        # Defensive audit check: the mandatory delivery gate must already have passed.
        if delivery not in {"PASS_GE_60_PERCENT", "PASS_AVG_GE_60_PERCENT"}:
            reasons.append("DELIVERY_CATEGORY_A_AVERAGE_NOT_GE_60_OR_DATA_MISSING")
        if rvol_status != "PASS" or pd.isna(rvol) or rvol <= 0:
            reasons.append("RVOL_20_SESSION_BASELINE_NOT_VALID")
        if setup not in {"Breakout", "Pullback"}:
            reasons.append("NO_CONFIRMED_BREAKOUT_OR_PULLBACK_SETUP")
        if "Bullish" not in trend:
            reasons.append("TREND_NOT_BULLISH")
        if setup == "Breakout" and (pd.isna(clv) or clv <= 0.75):
            reasons.append("BREAKOUT_CANDLE_NOT_STRONG_CLV_NOT_GT_0_75")
        elif setup == "Pullback" and (pd.isna(clv) or clv <= 0.50):
            reasons.append("PULLBACK_CANDLE_CLV_NOT_GT_0_50")
        if pv == "Selling / Distribution":
            reasons.append("PRICE_VOLUME_SHOWS_SELLING_DISTRIBUTION")
        if pd.isna(rs):
            reasons.append("RELATIVE_STRENGTH_WAIT_FOR_DATA")
        elif rs < 0:
            warnings.append("UNDERPERFORMS_NIFTY_SCORE_PENALTY")
        if pd.isna(support) or support <= 0 or pd.isna(resistance) or resistance <= 0:
            reasons.append("SUPPORT_RESISTANCE_WAIT_FOR_DATA")

        if setup == "Breakout":
            if breakout not in {"Breakout", "Strong Breakout"}:
                reasons.append("BREAKOUT_NOT_CONFIRMED")
            if pd.isna(change) or change <= 0:
                reasons.append("BREAKOUT_WITHOUT_POSITIVE_CLOSE_CHANGE")
        elif setup == "Pullback":
            if pullback not in {"Pullback", "Strong Pullback"}:
                reasons.append("PULLBACK_NOT_CONFIRMED")

        selected = len(reasons) == 0
        audit_rows.append({
            "EODDate": str(eod_date),
            "TckrSymb": symbol,
            "DeliveryFilterStatus": delivery,
            "RVOLStatus": rvol_status,
            "RVOL": rvol,
            "LowVolumeDays5D": low_days,
            "PriceChangePct": change,
            "CLV": clv,
            "TrendClassification": trend,
            "SetupType": setup,
            "PriceVolumeRelationship": pv,
            "RelativeStrengthNifty": rs,
            "SRSupport": support,
            "SRResistance": resistance,
            "CandidateScreenStatus": "PASS" if selected else "REJECT",
            "CandidateScreenReasons": "PASS_CORE_TECHNICAL_SCREEN" if selected else ";".join(reasons),
            "CandidateScreenWarnings": ";".join(warnings) if warnings else "NONE",
        })

    audit = pd.DataFrame(audit_rows)
    # Keep the full liquidity-qualified cohort flowing through sector/news/3+1 evidence collection.
    # The technical screen is recorded as a hard final eligibility gate, not an early data-collection gate.
    audit["TckrSymb"] = audit["TckrSymb"].astype(str).str.strip().str.upper()
    frame["TckrSymb"] = frame["TckrSymb"].astype(str).str.strip().str.upper()
    audit_map = audit.set_index("TckrSymb")[[
        "CandidateScreenStatus", "CandidateScreenReasons", "CandidateScreenWarnings"
    ]]
    frame = frame.merge(audit_map, left_on="TckrSymb", right_index=True, how="left")
    frame["CoreTechnicalScreenStatus"] = frame["CandidateScreenStatus"]
    frame["CoreTechnicalScreenReasons"] = frame["CandidateScreenReasons"]
    frame["CoreTechnicalScreenWarnings"] = frame["CandidateScreenWarnings"]
    frame["RVOL"] = pd.to_numeric(frame["RVOL"], errors="coerce")
    frame["CLV"] = pd.to_numeric(frame["CLV"], errors="coerce")
    frame["RelativeStrengthNifty"] = pd.to_numeric(frame["RelativeStrengthNifty"], errors="coerce")
    frame = frame.sort_values(
        ["RVOL", "CLV", "RelativeStrengthNifty"],
        ascending=[False, False, False], na_position="last", kind="mergesort",
    ).copy()
    frame["CandidateRank"] = range(1, len(frame) + 1)
    write_technical_parameter_audit(frame, eod_date)

    ranks = dict(zip(frame["TckrSymb"].astype(str).str.upper(), frame["CandidateRank"]))
    audit["CandidateRank"] = audit["TckrSymb"].map(ranks)
    audit.loc[audit["CandidateScreenStatus"].eq("PASS") & audit["CandidateRank"].isna(), "CandidateScreenStatus"] = "PASS"
    audit_path = os.path.join("data", "reports", f"v8_candidate_selection_audit_{pd.Timestamp(eod_date).strftime('%Y%m%d')}.csv")
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    audit.to_csv(audit_path, index=False)
    os.makedirs("outputs", exist_ok=True)
    # This cohort contains all liquidity-qualified A/B candidates, not only HIGH RVOL.
    # Keep the old filename as a compatibility alias; new consumers should use
    # the accurately named artifact below.
    frame.to_csv(os.path.join("outputs", "v8_liquidity_qualified_pre_news_candidates.csv"), index=False)
    frame.to_csv(os.path.join("outputs", "v8_pre_news_rvol_gt_1_5_candidates.csv"), index=False)

    counts = audit["CandidateScreenStatus"].value_counts().to_dict()
    passed = int(audit["CandidateScreenStatus"].eq("PASS").sum())
    print("[CANDIDATE SCREEN] Audit: " + audit_path)
    print(f"[CANDIDATE SCREEN] Core technical pass among liquidity-qualified Delivery A/B candidates: {passed}/{len(frame)}")
    print(f"[CANDIDATE SCREEN] Continuing all liquidity-qualified Delivery A/B candidates into news/sector/EOD evidence analysis: {len(frame)} (RVOL classification only; no Top-N cap)")
    print(f"[CANDIDATE SCREEN] Status counts: {counts}")
    return frame


# ============================================================
# DISPLAY ALL LIQUIDITY-QUALIFIED DELIVERY A/B CANDIDATES
# ============================================================

def display_top20(result):
    """Legacy function name retained for compatibility; displays the full cohort without a Top-N cap."""

    print(
        "\n"
        + "=" * 110
    )

    print(
        "V8 LIQUIDITY-QUALIFIED DELIVERY A/B CANDIDATES (RVOL CLASSIFICATION ONLY; NO TOP-N CAP)"
    )

    print(
        "=" * 110
    )

    display = result.sort_values(by="RVOL", ascending=False, na_position="last")

    for i, (_, row) in enumerate(
        display.iterrows(),
        start=1
    ):

        def fmt(
            value,
            digits=2
        ):

            if pd.isna(value):
                return "NA"

            return (
                f"{value:.{digits}f}"
            )

        print(
            f"\n{i}. "
            f"{row['TckrSymb']:<15}"
            f" Price="
            f"{fmt(row['PriceChangePct'])}%"
            f" | RVOL="
            f"{fmt(row['RVOL'])}x"
            f" | Low5D="
            f"{int(row['LowVolumeDays5D'])}/5"
            f" | P+V="
            f"{row['PriceVolumeRelationship']:<30}"
            f" | CLV="
            f"{fmt(row['CLV'])} "
            f"{row['CLVQuality']:<10}"
        )

        print(
            f"   EMA20="
            f"{fmt(row['EMA20'])}"
            f" | EMA44="
            f"{fmt(row['EMA44'])}"
            f" | EMA44 Distance="
            f"{fmt(row.get('EMA44DistancePct'))}%"
            f" | EMA44 Proximity="
            f"{row.get('EMA44ProximityStatus', 'WAIT_FOR_DATA')}"
            f" | EMA44 Signal="
            f"{row.get('EMA44SignalStatus', 'WAIT_FOR_DATA')}"
            f" | RSI="
            f"{fmt(row['RSI14'],1)}"
            f" | ADX="
            f"{fmt(row['ADX14'],1)}"
            f" | Trend="
            f"{row['TrendClassification']}"
        )

        print(
            f"   20DHigh="
            f"{fmt(row['High20D'])}"
            f" | 50DHigh="
            f"{fmt(row['High50D'])}"
            f" | SwingHigh="
            f"{fmt(row['RecentSwingHigh'])}"
            f" | SwingLow="
            f"{fmt(row['RecentSwingLow'])}"
        )

        print(
            f"   Breakout="
            f"{row['BreakoutStatus']}"
            f" | Pullback="
            f"{row['PullbackStatus']}"
            f" | Setup="
            f"{row['SetupType']}"
        )

        print(
            f"   PDH="
            f"{fmt(row['PDH'])}"
            f" | PDL="
            f"{fmt(row['PDL'])}"
            f" | PWH="
            f"{fmt(row['PWH'])}"
            f" | PWL="
            f"{fmt(row['PWL'])}"
        )

        print(
            f"   Support="
            f"{fmt(row['SRSupport'])}"
            f" | Resistance="
            f"{fmt(row['SRResistance'])}"
            f" | BreakoutLevel="
            f"{fmt(row['BreakoutLevel'])}"
        )

        print(
            f"   EntryZone="
            f"{fmt(row['EntryZoneLow'])}"
            f" - "
            f"{fmt(row['EntryZoneHigh'])}"
            f" | S/R="
            f"{row['SRStatus']}"
        )

        print(
            f"   StockReturn20D="
            f"{fmt(row['StockReturn20D'])}%"
            f" | NiftyReturn20D="
            f"{fmt(row['NiftyReturn20D'])}%"
            f" | RelativeStrengthNifty="
            f"{fmt(row['RelativeStrengthNifty'])}%"
            f" | RSNiftyClassification="
            f"{row['RSNiftyClassification']}"
        )

        if "EODWatchlistStatus" in row.index:
            print(
                f"   V8Score={fmt(row.get('V8Score'), 0)}/100"
                f" | Sector={row.get('Sector', 'Unknown')}"
                f" | News={row.get('NewsEvidenceStatus', 'WAIT_FOR_DATA')}"
                f" | R:R={fmt(row.get('RiskReward'))}"
                f" | Chase={row.get('ChaseStatus', 'WAIT_FOR_DATA')}"
                f" | EOD={row.get('EODWatchlistStatus', 'WAIT_FOR_DATA')}"
            )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(
    result,
    eod_date
):

    if not TELEGRAM_BOT_TOKEN:

        print(
            "Telegram bot token "
            "not configured."
        )

        return

    if not TELEGRAM_CHAT_ID:

        print(
            "Telegram chat ID "
            "not configured."
        )

        return

    if "EODWatchlistStatus" in result:
        top = (
            result[result["EODWatchlistStatus"] == "WATCH"]
            .sort_values("V8Score", ascending=False)
            .head(10)
        )
    else:
        top = result.head(0)

    lines = []

    lines.append(
        "NSE V8 MODULE A - EOD UPDATE"
    )

    lines.append(
        f"Date: {eod_date}"
    )

    lines.append(
        "Analysis only. No automatic order is placed."
    )

    lines.append("")

    if top.empty:
        status_counts = result["EODWatchlistStatus"].value_counts().to_dict()
        lines.append("No symbol passed the complete EOD watchlist gate.")
        lines.append(f"Status counts: {status_counts}")
        lines.append("Missing external evidence keeps candidates out of WATCH.")

    for _, row in top.iterrows():

        def fmt(
            value,
            digits=2
        ):

            if pd.isna(value):
                return "NA"

            return (
                f"{value:.{digits}f}"
            )

        lines.append(
            f"{row['TckrSymb']} | "
            f"RVOL {fmt(row['RVOL'])}x | "
            f"Setup {row['SetupType']}"
        )

        lines.append(
            f"Trend: "
            f"{row['TrendClassification']}"
        )

        lines.append(
            f"Support: "
            f"{fmt(row['SRSupport'])} | "
            f"Resistance: "
            f"{fmt(row['SRResistance'])}"
        )

        lines.append(
            f"Breakout Level: "
            f"{fmt(row['BreakoutLevel'])}"
        )

        lines.append(
            f"Entry Zone: "
            f"{fmt(row['EntryZoneLow'])}"
            f"-"
            f"{fmt(row['EntryZoneHigh'])}"
        )

        lines.append(
            f"S/R Status: "
            f"{row['SRStatus']}"
        )

        lines.append(
            f"20D RS vs Nifty: "
            f"Stock {fmt(row['StockReturn20D'])}% | "
            f"Nifty {fmt(row['NiftyReturn20D'])}% | "
            f"RS {fmt(row['RelativeStrengthNifty'])}% | "
            f"{row['RSNiftyClassification']}"
        )

        lines.append(
            f"V8 Score: {row.get('V8Score', 'NA')}/100"
            f" | Sector: {row.get('Sector', 'Unknown')}"
            f" | News: {row.get('NewsEvidenceStatus', 'WAIT_FOR_DATA')}"
            f" | R:R: {row.get('RiskReward', 'NA')}"
        )

        lines.append("")

    message = "\n".join(
        lines
    )

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/"
        "sendMessage"
    )

    try:

        response = requests.post(
            url,
            data={
                "chat_id":
                    TELEGRAM_CHAT_ID,
                "text":
                    message,
            },
            timeout=20,
        )

        print(
            f"Telegram HTTP status: "
            f"{response.status_code}"
        )

        if response.status_code != 200:

            print(
                f"Telegram response: "
                f"{response.text[:500]}"
            )

    except Exception as e:

        print(
            f"Telegram error: {e}"
        )


# ============================================================
# MAIN
# ============================================================

@_perf_timed("total_scanner_runtime")
def main():

    print(
        "\n"
        + "=" * 70
    )

    print(
        "NSE V8 MODULE A"
    )

    print(
        "NSE MAINBOARD + DUAL DELIVERY A/B + RVOL CLASSIFICATION + LIQUIDITY + FUNDAMENTALS + 5D "
        "+ PRICE/VOLUME + CLV "
        "+ TREND "
        "+ BREAKOUT/PULLBACK "
        "+ SUPPORT/RESISTANCE + RELATIVE STRENGTH"
    )

    print(
        "=" * 70
    )

    print(
        "\nPython script started successfully."
    )

    # Fail-closed calendar coverage is enforced at use time; warn early so the
    # official NSE holiday list can be refreshed before the year rolls over.
    for calendar_warning in calendar_coverage_warnings():
        print(calendar_warning)

    # Exclude ETF units consistently from current EOD and historical volume data.
    refresh_official_etf_symbols()

    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    eod_date, raw_current = (
        get_latest_eod()
    )

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    print(
        "\nSTEP 2: Preparing current "
        "EOD data..."
    )

    current = prepare_equity_data(
        raw_current
    )

    print(
        f"Current valid symbols before Main Board classification: "
        f"{len(current)}"
    )

    # Full stage audits are retained so the final report can explain every gate.
    delivery_audit = pd.DataFrame()
    liquidity_audit = pd.DataFrame()
    fundamental_audit = pd.DataFrame()

    # --------------------------------------------------------
    # STEP 1B: OFFICIAL MAIN BOARD ONLY (SME EXCLUDED)
    # --------------------------------------------------------
    # Classification comes from NSE's official Equity-segment and SME CSVs.
    # Unknown symbols are excluded; no name/price/series heuristic is used.
    try:
        current, board_audit = apply_official_main_board_filter(current, session=session)
        os.makedirs("outputs", exist_ok=True)
        board_audit.to_csv("outputs/v8_main_board_universe_audit.csv", index=False)
    except Exception as exc:
        print(f"[MAIN_BOARD] WAIT_FOR_DATA: official board classification could not be verified: {exc}")
        current = current.iloc[0:0].copy()
        os.makedirs("outputs", exist_ok=True)
        pd.DataFrame(columns=["TckrSymb", "BoardClassification", "MainBoardStatus", "ClassificationSource"]).to_csv(
            "outputs/v8_main_board_universe_audit.csv", index=False
        )

    print(f"Current verified Main Board symbols: {len(current)}")
    # Immutable Track 2 input: official Mainboard cohort before Delivery A/B.
    # Track 2 writes isolated research artifacts and never mutates Track 1.
    track2_mainboard_candidates = current.copy(deep=True)

    # --------------------------------------------------------
    # STEP 3: LOAD HISTORY AND PREPARE THE PRIOR-20-SESSION VOLUME BASELINE.
    # Do not calculate RVOL for the Mainboard universe here. RVOL calculation
    # is deliberately deferred until the complete Delivery A OR B union exists.
    historical = collect_historical_days(eod_date, HISTORY_DAYS)
    avg_volume = calculate_average_volume(historical)

    # --------------------------------------------------------
    # STEP 4: DELIVERY A/B ELIGIBILITY — BUILD THE COMPLETE A OR B UNION FIRST.
    # --------------------------------------------------------
    print("\\nSTEP 4: Classifying 30-calendar-day Delivery Categories A and B before RVOL...")
    delivery_data_available = True
    delivery_sessions = []
    accumulation_report = pd.DataFrame()
    vcp_report = pd.DataFrame()
    if current.empty:
        delivery_audit = current.copy()
        for col in ["DeliverySessions", "DeliveryDailyPassCount", "DeliveryMin5D", "AvgDelivery5D", "LatestDeliveryPct", "DeliveryStatus", "DeliveryFilterStatus", "DeliveryCategoryAStatus", "DeliveryCategoryBStatus"]:
            if col not in delivery_audit.columns:
                delivery_audit[col] = pd.Series(dtype="object")
    else:
        try:
            # Fetch the full 30-calendar-day Delivery window once. A/B and
            # 5D/10D/20D consistency reuse these same in-memory reports.
            delivery_sessions = get_delivery_sessions(
                eod_date, required_sessions=5, max_calendar_days=30,
                session=session, collect_all=True,
            )

            _, delivery_audit = apply_delivery_filter(
                current, eod_date, symbol_col="TckrSymb", series_col="SctySrs",
                minimum_average=60.0, sessions=delivery_sessions,
            )
            delivery_data_available = not delivery_audit.empty

            # Consistency is observational and must reuse the shared Delivery fetch.
            try:
                delivery_audit, _ = build_delivery_consistency_report(
                    delivery_audit, eod_date, sessions=delivery_sessions, threshold=60.0
                )
            except Exception as consistency_exc:
                consistency_columns = [
                    "Delivery5DSessions", "Delivery5DDailyPassCount", "Delivery5DAverage",
                    "Delivery5DCategoryAStatus", "Delivery5DCategoryBStatus",
                    "Delivery10DSessions", "Delivery10DDailyPassCount", "Delivery10DAverage",
                    "Delivery10DCategoryAStatus", "Delivery10DCategoryBStatus",
                    "Delivery20DSessions", "Delivery20DDailyPassCount", "Delivery20DAverage",
                    "Delivery20DCategoryAStatus", "Delivery20DCategoryBStatus",
                    "Delivery20DCurrentStreak", "Delivery20DTag",
                    "DeliveryConsistencyAsOfDate", "DeliveryConsistencyWindowStart",
                    "DeliveryConsistencyWindowEnd",
                ]
                for column in consistency_columns:
                    delivery_audit[column] = "WAIT_FOR_DATA"
                os.makedirs("outputs", exist_ok=True)
                delivery_audit[["TckrSymb"] + consistency_columns].to_csv(
                    f"outputs/v8_delivery_consistency_{pd.Timestamp(eod_date).strftime('%Y%m%d')}.csv",
                    index=False,
                )
                print(
                    "[DELIVERY CONSISTENCY] WAIT_FOR_DATA; existing 5D Delivery A/B "
                    f"pipeline continues unchanged: {type(consistency_exc).__name__}: {consistency_exc}"
                )
            # Delivery Quantity + price-response evidence is observational only.
            # It must never change Delivery A/B membership or stop the liquidity path.
            try:
                delivery_audit, _ = build_delivery_quantity_report(
                    delivery_audit, eod_date, sessions=delivery_sessions
                )
                print(
                    "[DELIVERY QUANTITY] Observation report saved; "
                    "quantity/price fields do not act as eligibility gates."
                )
            except Exception as quantity_exc:
                delivery_audit["DeliveryQuantityStatus"] = "WAIT_FOR_DATA"
                delivery_audit["DeliveryQuantityReason"] = (
                    f"OBSERVATION_UNAVAILABLE:{type(quantity_exc).__name__}"
                )
                print(
                    "[DELIVERY QUANTITY] WAIT_FOR_DATA; A/B pipeline continues unchanged: "
                    f"{type(quantity_exc).__name__}: {quantity_exc}"
                )

            if delivery_data_available and "DeliverySessions" in delivery_audit.columns:
                session_counts = pd.to_numeric(delivery_audit["DeliverySessions"], errors="coerce")
                delivery_data_available = bool(session_counts.ge(5).any())
            os.makedirs("outputs", exist_ok=True)
            delivery_audit["DeliveryFilterStatus"] = delivery_audit.apply(
                lambda row: "PASS_A_OR_B"
                if (
                    str(row.get("DeliveryCategoryAStatus", "")).upper() == "PASS_AVG_GE_60_PERCENT"
                    or str(row.get("DeliveryCategoryBStatus", "")).upper() == "PASS_EACH_DAY_GE_60_PERCENT"
                )
                else ("WAIT_FOR_DATA" if str(row.get("DeliveryCategoryAStatus", "")).upper().startswith("WAIT_FOR_DATA")
                      or str(row.get("DeliveryCategoryBStatus", "")).upper().startswith("WAIT_FOR_DATA")
                      else "FILTERED_OUT_A_AND_B"),
                axis=1,
            )
            delivery_audit.to_csv("outputs/v8_delivery_dual_category_audit.csv", index=False)

            # Delivery is the eligibility gate. Keep the full A OR B union.
            # RVOL only classifies the Delivery-qualified universe; it must not
            # remove stocks at or below 1.5 or stocks whose RVOL is unavailable.
            category_a_all = delivery_audit[
                delivery_audit["DeliveryCategoryAStatus"].eq("PASS_AVG_GE_60_PERCENT")
            ].copy()
            category_b_all = delivery_audit[
                delivery_audit["DeliveryCategoryBStatus"].eq("PASS_EACH_DAY_GE_60_PERCENT")
            ].copy()
            category_a_all["DeliveryCategory"] = "A"
            category_b_all["DeliveryCategory"] = "B"
            category_a_all.to_csv("outputs/v8_delivery_category_a_all.csv", index=False)
            category_b_all.to_csv("outputs/v8_delivery_category_b_all.csv", index=False)

            # Build the unique A/B union before classifying RVOL. Preserve A/B
            # membership and never use the RVOL threshold as an eligibility gate.
            combined = pd.concat([category_a_all, category_b_all], ignore_index=True, sort=False)
            if not combined.empty:
                membership = combined.groupby("TckrSymb")["DeliveryCategory"].agg(
                    lambda values: "A_AND_B" if set(values) >= {"A", "B"} else str(values.iloc[0])
                )
                delivery_candidates = combined.drop_duplicates("TckrSymb", keep="first").copy()
                delivery_candidates["DeliveryCategory"] = delivery_candidates["TckrSymb"].map(membership)
                delivery_candidates["DeliveryCategoryAStatus"] = delivery_candidates["DeliveryCategoryAStatus"].fillna("WAIT_FOR_DATA")
                delivery_candidates["DeliveryCategoryBStatus"] = delivery_candidates["DeliveryCategoryBStatus"].fillna("WAIT_FOR_DATA")
                delivery_candidates["DeliveryFilterStatus"] = "PASS_GE_60_PERCENT"
                delivery_candidates["DeliveryStatus"] = "PASS"

                # STEP 5: Calculate RVOL only after A/B union + de-duplication.
                # Every A/B-qualified stock is passed to calculate_rvol; HIGH,
                # LOW and WAIT_FOR_DATA rows are all retained for Liquidity.
                current = calculate_rvol(delivery_candidates, avg_volume)
                current = classify_rvol_for_delivery_candidates(
                    current, eod_date, minimum_rvol=1.5
                )
                current.to_csv("outputs/v8_delivery_qualified_all_rvol_classified.csv", index=False)

                # Early-stage accumulation observations run on the full unique
                # Delivery A/B union before Liquidity and later technical gates.
                # This report is independent and never changes candidate membership.
                try:
                    accumulation_report = build_potential_accumulation_report(
                        current, historical, delivery_sessions, eod_date
                    )
                    print(
                        "[ACCUMULATION] Independent observations saved for "
                        f"{len(accumulation_report)} Delivery A/B candidates; no gating applied."
                    )
                except Exception as accumulation_exc:
                    # Preserve every unique Delivery A/B candidate in the
                    # early watchlist even if the optional evidence engine
                    # fails. The fallback is explicitly WAIT_FOR_DATA.
                    accumulation_report = current.drop_duplicates(
                        "TckrSymb", keep="first"
                    ).copy()
                    accumulation_report["AsOfDate"] = pd.Timestamp(eod_date).date().isoformat()
                    accumulation_report["DeliveryEvidenceStatus"] = "WAIT_FOR_DATA"
                    accumulation_report["EvidenceStatus"] = "WAIT_FOR_DATA"
                    accumulation_report["DeliveryQuantityStatus"] = "WAIT_FOR_DATA"
                    print(
                        "[ACCUMULATION] WAIT_FOR_DATA; preserved "
                        f"{len(accumulation_report)} Delivery A/B candidates for early watchlist; "
                        f"Delivery/Liquidity pipeline continues: {type(accumulation_exc).__name__}: {accumulation_exc}"
                    )
                # VCP measurements are descriptive only; no VCP status is
                # used to filter or rank the Delivery A/B candidate union.
                try:
                    vcp_report = build_vcp_observation_report(
                        current, historical, eod_date
                    )
                    print(
                        "[VCP] Three-block range/volume observations saved for "
                        f"{len(vcp_report)} candidates; no gating applied."
                    )
                except Exception as vcp_exc:
                    print(
                        "[VCP] WAIT_FOR_DATA; Delivery/Liquidity pipeline continues: "
                        f"{type(vcp_exc).__name__}: {vcp_exc}"
                    )
                current[current["RVOLBand"].eq("HIGH_RVOL_GT_1_5")].to_csv(
                    "outputs/v8_rvol_gt_1_5_candidates.csv", index=False
                )
                current[current["RVOLBand"].eq("LOW_RVOL_LE_1_5")].to_csv(
                    "outputs/v8_rvol_le_1_5_delivery_candidates.csv", index=False
                )
                current[current["RVOLBand"].eq("WAIT_FOR_DATA")].to_csv(
                    "outputs/v8_delivery_candidates_rvol_wait.csv", index=False
                )
            else:
                current = combined
                current["RVOLBand"] = pd.Series(dtype="object")
                current["RVOLThresholdStatus"] = pd.Series(dtype="object")

            print(
                f"[DELIVERY A] 30D average >=60%: {len(category_a_all)}; "
                f"[DELIVERY B] every valid session >=60%: {len(category_b_all)}."
            )
            print(
                f"[DELIVERY] Unique A/B-qualified stocks retained for liquidity={len(current)}; "
                "RVOL is classification only, not a rejection gate."
            )
        except Exception as exc:
            delivery_data_available = False
            print(f"[DELIVERY] WAIT_FOR_DATA: delivery categories could not be verified: {exc}")
            current = current.iloc[0:0].copy()
            delivery_audit = current.copy()
            for col in ["DeliverySessions", "DeliveryDailyPassCount", "DeliveryMin5D", "AvgDelivery5D", "LatestDeliveryPct", "DeliveryStatus", "DeliveryFilterStatus", "DeliveryCategoryAStatus", "DeliveryCategoryBStatus"]:
                if col not in current.columns:
                    current[col] = pd.Series(dtype="object")

    # Track 2 always observes the immutable full Mainboard cohort, even if
    # Track 1's current frame is empty or the shared Delivery fetch failed.
    # Missing Delivery evidence is passed as an empty session list and reported
    # as WAIT_FOR_DATA by the observer; it cannot gate or mutate Track 1.
    try:
        track2_report, track2_manifest = build_track2_full_mainboard_report(
            track2_mainboard_candidates,
            historical,
            delivery_sessions,
            eod_date,
        )
        print(
            "[TRACK 2] Full Mainboard research report saved; "
            f"cohort_rows={len(track2_report)}, "
            f"eligible_unique={track2_manifest.get('eligible_unique_mainboard_symbols', 0)}; "
            "non-gating and isolated from Track 1."
        )
    except Exception as track2_exc:
        print(
            "[TRACK 2] WAIT_FOR_DATA; Track 1 continues unchanged: "
            f"{type(track2_exc).__name__}: {track2_exc}"
        )

    # Persist A/B delivery scan streaks independently of downstream fundamental,
    # technical, news, or sector gates. A duplicate EOD date is idempotent.
    market_session_dates = []
    for history_frame in historical:
        if "Date" in history_frame.columns:
            market_session_dates.extend(
                pd.to_datetime(history_frame["Date"], errors="coerce").dropna().tolist()
            )
    try:
        delivery_audit = update_delivery_scan_streak(
            delivery_audit,
            eod_date,
            market_session_dates,
            data_available=delivery_data_available,
        )
        os.makedirs("outputs", exist_ok=True)
        delivery_audit.to_csv("outputs/v8_delivery_dual_category_audit.csv", index=False)
    except Exception as tracker_exc:
        print(f"[DELIVERY TRACKER] WAIT_FOR_DATA: streak report could not be updated: {tracker_exc}")

    # Four hybrid watchlists are independent reports. The first two are
    # generated before Liquidity and never remove Delivery A/B candidates.
    try:
        early_watchlists = write_early_hybrid_watchlists(
            accumulation_report, vcp_report
        )
        print(
            "[HYBRID WATCHLISTS] Early Accumulation and Base/VCP reports saved; "
            f"accumulation_rows={len(early_watchlists[0])}, base_rows={len(early_watchlists[1])}."
        )
    except Exception as watchlist_exc:
        print(f"[HYBRID WATCHLISTS] Early outputs WAIT_FOR_DATA: {watchlist_exc}")

    # --------------------------------------------------------
    # --------------------------------------------------------
    # STEP 5: LIQUIDITY FIRST — FUNDAMENTALS ARE COLLECTED AFTER PASS
    # --------------------------------------------------------
    print("\nSTEP 5: All Delivery A/B-passed stocks (all RVOL bands) proceed to liquidity.")
    # The previous fundamental hard gate could empty the candidate list before
    # liquidity was measured. Keep Delivery-passed candidates intact here.
    fundamental_audit = pd.DataFrame()
    observation_report = pd.DataFrame()

    # STEP 6: EXISTING LIQUIDITY FILTER — ₹1.5 CRORE
    # --------------------------------------------------------
    print("\nSTEP 6: Applying 20-session liquidity tiers; minimum average daily traded value ₹1.5 crore...")
    liquidity_audit_columns = ["LiquiditySessions", "AvgDailyTradedValue20D", "MinimumAvgDailyTradedValueINR", "LiquidityStatus", "LiquidityFilterStatus", "LiquidityTier"]
    if current.empty:
        for col in liquidity_audit_columns:
            current[col] = pd.Series(dtype="object")
        liquidity_audit = current.copy()
    else:
        try:
            current, liquidity_audit = apply_liquidity_filter(
                current, historical, symbol_col="TckrSymb", value_col="TtlTrfVal",
                minimum_average_daily_value=MINIMUM_AVG_DAILY_TRADED_VALUE_INR, required_sessions=20,
            )
        except Exception as exc:
            print(f"[LIQUIDITY] WAIT_FOR_DATA: liquidity gate could not be verified: {exc}")
            current = current.iloc[0:0].copy()
            for col in liquidity_audit_columns:
                current[col] = pd.Series(dtype="object")
            liquidity_audit = current.copy()
    os.makedirs("outputs", exist_ok=True)
    liquidity_audit.to_csv("outputs/v8_liquidity_first_audit.csv", index=False)
    print(f"[LIQUIDITY] Audit saved: outputs/v8_liquidity_first_audit.csv; qualified={len(current)}")

    # --------------------------------------------------------
    # STEP 7: FUNDAMENTALS FOR LIQUIDITY-QUALIFIED STOCKS ONLY
    # --------------------------------------------------------
    print(f"\nSTEP 7: Collecting NSE/Yahoo fundamentals for {len(current)} liquidity-qualified stocks; score is informational, never a rejection gate...")
    create_fundamental_templates()
    liquidity_pass_candidates = current.copy()
    try:
        if liquidity_pass_candidates.empty:
            fundamental_audit = liquidity_pass_candidates.copy()
            for report_name in ["v8_fundamental_report.csv", "v8_fundamental_complete_data.csv",
                                "v8_fundamental_partial_data.csv", "v8_fundamental_missing_data.csv",
                                "v8_liquidity_fundamental_candidates.csv"]:
                fundamental_audit.to_csv(os.path.join("outputs", report_name), index=False)
        else:
            try:
                collect_missing_fundamentals(liquidity_pass_candidates, asof_date=eod_date)
            except Exception as provider_exc:
                os.makedirs("outputs", exist_ok=True)
                pd.DataFrame([{
                    "ProviderStatus": "PROVIDER_STAGE_ERROR",
                    "ProviderReason": f"{type(provider_exc).__name__}: {provider_exc}",
                }]).to_csv("outputs/v8_fundamental_provider_diagnostics.csv", index=False)
                print(f"[FUNDAMENTAL PROVIDER] Stage error; retain liquidity-passed stocks: {provider_exc}")
            fundamental_audit, _ = apply_fundamental_filter(liquidity_pass_candidates, eod_date)
            # Run NSE XBRL verification as an audit sidecar, never as an eligibility gate.
            try:
                from fundamental_metric_verification import run_audit as run_fundamental_metric_audit
                evidence_symbols = set(fundamental_audit["TckrSymb"].dropna().astype(str).str.upper())
                run_fundamental_metric_audit(symbols=evidence_symbols)
            except Exception as metric_audit_exc:
                print(f"[NSE XBRL AUDIT] WAIT_FOR_DATA; liquidity-passed stocks are retained: {metric_audit_exc}")
            os.makedirs("outputs", exist_ok=True)
            fundamental_audit.to_csv("outputs/v8_fundamental_report.csv", index=False)
            fundamental_audit[fundamental_audit.get("FundamentalStatus", pd.Series("", index=fundamental_audit.index)).astype(str).eq("COMPLETE")].to_csv("outputs/v8_fundamental_complete_data.csv", index=False)
            fundamental_audit[fundamental_audit.get("FundamentalStatus", pd.Series("", index=fundamental_audit.index)).astype(str).eq("PARTIAL_DATA")].to_csv("outputs/v8_fundamental_partial_data.csv", index=False)
            fundamental_audit[fundamental_audit.get("FundamentalStatus", pd.Series("", index=fundamental_audit.index)).astype(str).eq("MISSING_DATA")].to_csv("outputs/v8_fundamental_missing_data.csv", index=False)
            fundamental_audit.to_csv("outputs/v8_liquidity_fundamental_candidates.csv", index=False)
        current = fundamental_audit.copy()
        observation_report = current.copy()
        if "Fundamental65PlusStatus" in current.columns:
            print(f"[FUNDAMENTAL SCORE] 65+/below/incomplete={current['Fundamental65PlusStatus'].value_counts().to_dict()}; no score-based rejection.")
    except Exception as fund_exc:
        print(f"[FUNDAMENTAL] Collection/score error; keeping all liquidity-qualified candidates: {fund_exc}")
        fundamental_audit = liquidity_pass_candidates.copy()
        if not fundamental_audit.empty:
            fundamental_audit["FundamentalStatus"] = "MISSING_DATA"
            fundamental_audit["FundamentalReason"] = f"FUNDAMENTAL_COLLECTION_ERROR:{type(fund_exc).__name__}:{fund_exc}"
            fundamental_audit["Fundamental65PlusStatus"] = "WAIT_FOR_DATA"
            fundamental_audit["FundamentalScore"] = pd.NA
            fundamental_audit.to_csv("outputs/v8_fundamental_report.csv", index=False)
            fundamental_audit.to_csv("outputs/v8_liquidity_fundamental_candidates.csv", index=False)
        current = fundamental_audit.copy()
        observation_report = current.copy()
    print(f"[FUNDAMENTAL] liquidity-qualified rows retained={len(current)}; fundamentals are enrichment only.")


    # Calculate technical features for every stock that passed Delivery and Liquidity.
    # Fundamental score/status is enrichment only and never removes a candidate.
    result = current.copy()
    result = calculate_5d_volume(result, historical)
    result = prepare_primary_shortlist(result, eod_date)
    # RVOL/AvgVolume20D were calculated once on the Delivery A/B union above.
    # Preserve those verified fields; do not recalculate for a later cohort.

    # Keep the current session out of rolling-volume baselines, but include it
    # for indicators and price-structure calculations that describe today's EOD.
    current_history = current.copy()
    current_history["Date"] = pd.Timestamp(eod_date)
    analysis_history = historical + [current_history]

    # RVOL threshold and both Delivery categories have already been applied.
    # All remaining existing technical modules continue without a Top-50 cap.

    # --------------------------------------------------------
    # STEP 7: PRICE + VOLUME — all candidates that passed non-fundamental gates
    # --------------------------------------------------------
    result = calculate_price_volume_relationship(result)

    # --------------------------------------------------------
    # STEP 8
    # --------------------------------------------------------

    result = calculate_clv(
        result
    )

    # Accumulation score (descriptive, non-gating)
    result = calculate_accumulation_score(result)

    # Consolidation detection (descriptive, non-gating)
    result = calculate_consolidation_score(result, analysis_history)

    # --------------------------------------------------------
    # STEP 9
    # --------------------------------------------------------

    result = calculate_trend(
        result,
        analysis_history
    )

    # --------------------------------------------------------
    # STEP 10
    # --------------------------------------------------------

    result = (
        calculate_breakout_pullback(
            result,
            analysis_history
        )
    )

    # Descriptive retest observation only; never changes selection or entry gates.
    try:
        retest_observation = build_breakout_retest_observation(result, analysis_history)
        if len(retest_observation) == len(result):
            for column in retest_observation.columns:
                if column != "TckrSymb":
                    result[column] = retest_observation[column].to_numpy()
    except Exception as retest_exc:
        result["RetestObservationStatus"] = "WAIT_FOR_DATA"
        result["ExactLevelTouchObserved"] = "WAIT_FOR_DATA"
        print("[BREAKOUT_RETEST] WAIT_FOR_DATA; existing pipeline continues: " + str(retest_exc))

    # LowVolumeDays5D may remain as descriptive data only. It is not a selection
    # condition; the mandatory rule is Delivery >=60% on EACH of five sessions.
    if "LowVolumeDays5D" in result.columns:
        result["LowVolumeRuleStatus"] = "NOT_USED_DELIVERY_PERCENTAGE_IS_THE_REQUIRED_VOLUME_SELECTION_GATE"

    # --------------------------------------------------------
    # STEP 11
    # SUPPORT / RESISTANCE
    # --------------------------------------------------------

    result = (
        calculate_support_resistance(
            result,
            analysis_history
        )
    )

    # Independent bottom diagnostics: separate report only; never filters or
    # re-ranks the existing V8 candidate pipeline.
    bottom_report = write_bottom_detection_report(
        result,
        analysis_history,
        eod_date,
    )

    # --------------------------------------------------------
    # STEP 12
    # RELATIVE STRENGTH VS NIFTY
    # --------------------------------------------------------

    nifty_history = load_nifty_index_history(
        eod_date
    )

    result = calculate_relative_strength_nifty(
        result,
        historical,
        nifty_history,
        eod_date
    )

    # Core technical screen: only eligible Breakout/Pullback candidates proceed
    # to the costly news/sector/3+1 layers. The remaining universe is preserved
    # in the selection audit, not mislabeled as a final watchlist.
    result = select_top20_analysis_candidates(result, eod_date)
    observation_report = result.copy()  # Every liquidity-qualified row plus its core technical result.
    os.makedirs("outputs", exist_ok=True)
    result.to_csv("outputs/v8_technical_report.csv", index=False)
    observation_report.to_csv("outputs/v8_liquidity_technical_fundamental_report.csv", index=False)

    # Check every liquidity-qualified candidate against official NSE RSS feeds and secondary coverage.
    news_session_dates = [
        pd.to_datetime(frame["Date"], errors="coerce").dropna().iloc[0]
        for frame in historical[-4:]
        if "Date" in frame.columns and not frame.empty
        and not pd.to_datetime(frame["Date"], errors="coerce").dropna().empty
    ]
    news_session_dates.append(pd.Timestamp(eod_date))
    auto_news, news_feed_status = collect_catalyst_news(
        observation_report,
        eod_date,
        session_dates=news_session_dates,
    )

    # --------------------------------------------------------
    # STEPS 13–41: EOD scoring, next-day validation, positions
    # --------------------------------------------------------

    # --------------------------------------------------------
    # SECTOR DATA INTEGRATION
    # Ensure sector_data.py runs before Layers 14–24 read the CSVs.
    # Missing feeds remain WAIT_FOR_DATA; never fabricate confirmations.
    # --------------------------------------------------------
    print("\\nSTEP 13A: Refreshing official NSE sector mapping/history...")
    try:
        sector_refresh = refresh_sector_inputs(
            eod_date,
            candidate_symbols=result["TckrSymb"].astype(str).tolist() if "TckrSymb" in result.columns else [],
        )
        print(
            "[SECTOR] Refresh result: "
            f"mapping_rows={sector_refresh.get('mapping_rows', 0)}, "
            f"history_rows={sector_refresh.get('history_rows', 0)}, "
            f"exact_date_sectors={sector_refresh.get('sectors_with_asof', 0)}, "
            f"constituent_feeds={sector_refresh.get('constituent_feeds', 0)}"
        )
    except Exception as exc:
        print(f"[SECTOR] Refresh failed; sector layer must not pass: {exc}")

    # NSE FII/FPI and DII flows are market-wide context, not per-stock activity.
    # Keep the report even when the feed is unavailable; never use it to create
    # a stock-level confirmation or to alter the candidate score.
    market_flow = write_market_activity(eod_date)
    result = attach_market_context(result, market_flow)

    result = run_eod_layers(
        result,
        historical,
        current,
        nifty_history,
        eod_date,
    )

    # Observation-only append: does not mutate result or affect any scanner output.
    signal_rows_written = append_signal_log(result, eod_date)
    print(f"[SIGNAL LOG] Appended {signal_rows_written} new date/symbol rows (existing rows preserved).")
    # Forward outcomes are a separate observation-only sidecar. They use only
    # validated official-session Bhavcopy records strictly after each signal.
    try:
        outcome_summary = update_signal_outcomes(
            "outputs/signal_log.csv",
            analysis_history,
            outcome_store_path="outputs/signal_outcomes.csv",
        )
        print("[SIGNAL OUTCOMES] " + str(outcome_summary))
    except Exception as outcome_exc:
        print(f"[SIGNAL OUTCOMES] WARNING: observation update skipped; scanner continues: {outcome_exc}")

    # Full Mainboard shadow cohort + immutable point-in-time snapshots. This
    # sidecar is strictly observational and cannot feed back into Track 1.
    try:
        strategy_sha = os.getenv("GITHUB_SHA", "")
        if len(strategy_sha) != 40:
            raise ValueError("GITHUB_SHA is unavailable; immutable snapshot strategy version cannot be verified")
        shadow_manifest = build_mainboard_signal_shadow(
            track2_mainboard_candidates,
            reports={
                "delivery": delivery_audit,
                "liquidity": liquidity_audit,
                "fundamental": fundamental_audit,
                "technical": result,
                "final_eod": result,
            },
            eod_date=eod_date,
            strategy_version=strategy_sha,
            workflow_run_id=os.getenv("GITHUB_RUN_ID", ""),
            workflow_run_attempt=os.getenv("GITHUB_RUN_ATTEMPT", ""),
        )
        print("[SIGNAL SHADOW] " + str(shadow_manifest))
    except Exception as shadow_exc:
        print(f"[SIGNAL SHADOW] WARNING: observation snapshot skipped; scanner continues: {shadow_exc}")

    # Later-stage watchlists are independent copies; no output feeds back into
    # result or changes the existing EOD selection gates.
    try:
        write_breakout_ready_watchlist(result)
        write_confirmed_entry_watchlist(result)
        print("[HYBRID WATCHLISTS] Breakout Ready and Confirmed Entry reports saved.")
    except Exception as watchlist_exc:
        print(f"[HYBRID WATCHLISTS] Later outputs WAIT_FOR_DATA: {watchlist_exc}")

    write_catalyst_top20_report(
        result,
        eod_date,
        auto_news,
    )

    next_day_report = validate_next_day(
        result,
        eod_date,
    )

    position_report = monitor_positions(
        result,
        analysis_history,
        eod_date,
    )

    layer_summary = write_layer_status_summary(
        result,
        next_day_report,
        position_report,
    )

    # Consolidated, stage-labelled audit: every gate's PASS/REJECT/WAIT remains inspectable.
    stage_frames = []
    def _append_stage(frame, stage, status_col, reason_col=None, pass_values=None, reject_values=None):
        if frame is None or frame.empty or status_col not in frame.columns:
            return
        temp = frame.copy()
        temp["SelectionStage"] = stage
        temp["SelectionStatus"] = temp[status_col].fillna("WAIT_FOR_DATA").astype(str)
        if reason_col and reason_col in temp.columns:
            temp["SelectionReason"] = temp[reason_col].fillna("").astype(str)
        else:
            temp["SelectionReason"] = temp["SelectionStatus"]
        stage_frames.append(temp)
    _append_stage(delivery_audit, "DELIVERY_30D_AB", "DeliveryFilterStatus")
    _append_stage(liquidity_audit, "LIQUIDITY_20D", "LiquidityFilterStatus")
    _append_stage(fundamental_audit, "FUNDAMENTAL", "FundamentalStatus", "FundamentalReason")
    _append_stage(result, "PORTFOLIO_RISK", "RiskControlStatus", "RiskControlReason")
    _append_stage(result, "FINAL_EOD", "EODWatchlistStatus", "EODWatchlistReason")
    if stage_frames:
        selection_audit = pd.concat(stage_frames, ignore_index=True, sort=False)
    else:
        selection_audit = pd.DataFrame(columns=["TckrSymb", "SelectionStage", "SelectionStatus", "SelectionReason"])
    selection_audit.to_csv("outputs/v8_selection_status_report.csv", index=False)
    selection_audit[selection_audit["SelectionStatus"].astype(str).str.startswith(("PASS", "WATCH"))].to_csv("outputs/v8_passed_stocks.csv", index=False)
    selection_audit[selection_audit["SelectionStatus"].astype(str).str.contains("REJECT|FILTERED_OUT|SKIP|FAIL", case=False, regex=True)].to_csv("outputs/v8_rejected_stocks.csv", index=False)
    selection_audit[selection_audit["SelectionStatus"].astype(str).str.contains("WAIT_FOR_DATA", case=False)].to_csv("outputs/v8_wait_for_data_stocks.csv", index=False)

    print(
        "\nV8 reports saved under outputs/:"
    )

    print(
        f"EOD watchlist rows: {len(result)}"
    )

    print(
        f"Next-day validator rows: {len(next_day_report)}"
    )

    print(
        f"Open-position monitor rows: {len(position_report)}"
    )

    print(
        f"Layers 14–41 waiting for data: "
        f"{int((layer_summary['Result'] == 'WAIT_FOR_DATA').sum())}"
    )

    # --------------------------------------------------------
    # DISPLAY
    # --------------------------------------------------------

    display_top20(
        result
    )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    telegram_enabled = os.getenv(
        "SEND_TELEGRAM",
        "true"
    ).strip().lower() in {"1", "true", "yes", "on"}

    if telegram_enabled:
        manual_news_path = os.path.join("data", "inputs", "news_evidence.csv")
        manual_news = (
            pd.read_csv(manual_news_path)
            if os.path.exists(manual_news_path)
            else pd.DataFrame()
        )
        digest_news = pd.concat(
            [frame for frame in [auto_news, manual_news] if not frame.empty],
            ignore_index=True,
        ) if not auto_news.empty or not manual_news.empty else pd.DataFrame()
        send_marathi_telegram(
            result,
            eod_date,
            digest_news,
            news_feed_status,
            TELEGRAM_BOT_TOKEN,
            TELEGRAM_CHAT_ID,
            observation_report=observation_report,
        )
    else:
        print("Telegram notification skipped (SEND_TELEGRAM is disabled).")

    # --------------------------------------------------------
    # COMPLETION
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 70
    )

    print(
        "MODULE A CURRENT STAGE COMPLETED"
    )

    print(
        "=" * 70
    )

    print(
        f"\nEOD Date: {eod_date}"
    )

    print(
        f"\nFinal symbols: "
        f"{len(result)}"
    )

    print(
        "\nLayer code paths 1–41 evaluated; per-layer data/result status is in outputs/*.csv."
    )

    print(
        "WAIT_FOR_DATA and FAIL are not passing layers; review required before any trade."
    )

    print(
        "\nPython exit code: 0"
    )


# ============================================================
# EXPERIMENTAL CONSOLIDATION SCORE — NOT APPROVED, NOT BACKTESTED; NON-GATING
# ============================================================

def calculate_consolidation_score(result, historical):
    if result is None or result.empty:
        return result

    _, history_by_symbol = prepare_history_by_symbol(historical)
    scores = []
    statuses = []

    for _, row in result.iterrows():
        symbol = str(row.get("TckrSymb", "")).strip().upper()
        hist = history_by_symbol.get(symbol)
        score = 0.0
        status = "NO_CONSOLIDATION"

        if hist is not None and not hist.empty and len(hist) >= 10:
            closes = pd.to_numeric(hist["ClsPric"], errors="coerce").dropna()
            if len(closes) >= 10:
                recent = closes.tail(10)
                high = float(recent.max())
                low = float(recent.min())
                if high > 0:
                    range_pct = (high - low) / high * 100.0
                    if range_pct <= 5.0:
                        score = 90.0
                        status = "TIGHT_CONSOLIDATION"
                    elif range_pct <= 10.0:
                        score = 70.0
                        status = "MODERATE_CONSOLIDATION"
                    elif range_pct <= 15.0:
                        score = 50.0
                        status = "LOOSE_CONSOLIDATION"
                    else:
                        score = 10.0
                        status = "NO_CONSOLIDATION"

                    vols = pd.to_numeric(hist["TtlTradgVol"], errors="coerce").dropna()
                    if len(vols) >= 10:
                        recent_vols = vols.tail(5)
                        older_vols = vols.tail(10).head(5)
                        if older_vols.mean() > 0:
                            vol_ratio = recent_vols.mean() / older_vols.mean()
                            if vol_ratio < 0.8:
                                score = min(score + 10.0, 100.0)
                                status = status + "_VOL_CONTRACTING"

        scores.append(round(score, 2))
        statuses.append(status)

    result = result.copy()
    result["ConsolidationScore"] = scores  # legacy compatibility alias; experimental only
    result["ConsolidationStatus"] = statuses
    result["ExperimentalConsolidationScore"] = result["ConsolidationScore"]
    result["ExperimentalConsolidationStatus"] = result["ConsolidationStatus"].map(
        lambda value: f"EXPERIMENTAL_NOT_APPROVED_NOT_BACKTESTED_{value}"
    )
    print("[EXPERIMENTAL CONSOLIDATION — NOT APPROVED, NOT BACKTESTED] " + str(result["ExperimentalConsolidationStatus"].value_counts().to_dict()))
    return result


# ============================================================
# ENTRY POINT
# ============================================================
# Keep this guard last: any helper defined below it would raise NameError on
# the first live scan even though every unit test still passes.
if __name__ == "__main__":
    main()
