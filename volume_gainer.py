import os
import io
import zipfile
import requests
import pandas as pd
from delivery_filter import apply_delivery_filter
from liquidity_filter import apply_liquidity_filter, MINIMUM_AVG_DAILY_TRADED_VALUE_INR
from fundamental_filter import apply_fundamental_filter, create_fundamental_templates
from fundamental_data_provider import collect_missing_fundamentals
from fundamental_shortlist import build_fundamental_shortlist
from datetime import datetime, timedelta, timezone
from v8_layers_14_41 import (
    monitor_positions,
    run_eod_layers,
    validate_next_day,
    write_layer_status_summary,
)
import sector_data
from main_board_filter import apply_official_main_board_filter
from sector_data import refresh_sector_inputs
from news_catalyst import (
    collect_catalyst_news,
    send_marathi_telegram,
    write_catalyst_top20_report,
)

# ============================================================
# NSE V8 MODULE A
# EOD VOLUME + 5D PRIMARY SHORTLIST + RVOL + PRICE/VOLUME + CLV
# + TREND + BREAKOUT/PULLBACK + SUPPORT/RESISTANCE + RELATIVE STRENGTH
# ============================================================

NSE_BASE_URL = "https://nsearchives.nseindia.com/content/cm/"
HISTORY_DAYS = 50
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
        print(
            f"[UNIVERSE] Excluded {len(excluded_etfs)} ETF/mutual-fund symbols "
            f"before stock ranking: {excluded_etfs}"
        )
    else:
        print("[UNIVERSE] No ETF-like instruments found by official list/ISIN/name checks.")

    data = data.drop_duplicates(
        subset=["TckrSymb"],
        keep="first"
    )

    data["PriceChangePct"] = (
        (
            data["ClsPric"]
            - data["PrvsClsgPric"]
        )
        / data["PrvsClsgPric"]
    ) * 100

    return data


# ============================================================
# FIND LATEST EOD
# ============================================================

def get_latest_eod():

    print(
        "\nSTEP 1: Searching for latest "
        "NSE EOD Bhavcopy..."
    )

    today = datetime.now().date()

    for i in range(10):

        check_date = today - timedelta(days=i)

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

def collect_historical_days(
    latest_date,
    days=HISTORY_DAYS,
    max_calendar_days=120,
):

    print(
        "\nSTEP 3: Collecting historical "
        f"{days} trading days..."
    )

    print("\n" + "=" * 60)

    print(
        f"COLLECTING PREVIOUS "
        f"{days} TRADING DAYS"
    )

    print("=" * 60)

    historical = []

    current_date = (
        latest_date
        - timedelta(days=1)
    )

    attempted_days = 0
    while len(historical) < days and attempted_days < max_calendar_days:

        attempted_days += 1
        print(
            f"\nChecking {current_date} | "
            f"Found {len(historical)}/{days}"
        )

        df = download_bhavcopy(
            datetime.combine(
                current_date,
                datetime.min.time()
            )
        )

        if df is not None and len(df) > 0:

            try:

                clean = prepare_equity_data(
                    df
                )

                if len(clean) > 0:

                    clean["Date"] = pd.Timestamp(
                        current_date
                    )

                    historical.append(
                        clean
                    )

                    print(
                        f"Accepted trading day: "
                        f"{current_date}"
                    )

            except Exception as e:

                print(
                    f"Historical data error: {e}"
                )

        current_date -= timedelta(days=1)

    if len(historical) < days:
        raise RuntimeError(
            f"WAIT_FOR_DATA: only {len(historical)}/{days} historical EOD sessions "
            f"collected within {max_calendar_days} calendar days."
        )

    historical.reverse()

    print("\n" + "=" * 60)

    print(
        f"Historical trading days collected: "
        f"{len(historical)}"
    )

    print("=" * 60)

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


def load_nifty_index_history(latest_date):

    print(
        "\nSTEP 12: Loading Nifty 50 history "
        "and checking cache..."
    )

    os.makedirs(DATA_CACHE_DIR, exist_ok=True)

    cached = pd.DataFrame(
        columns=["Date", "NiftyClose"]
    )

    if os.path.exists(NIFTY_HISTORY_CACHE):

        try:

            cached = pd.read_csv(
                NIFTY_HISTORY_CACHE
            )

            if (
                "Date" in cached.columns
                and "NiftyClose" in cached.columns
            ):

                cached["Date"] = pd.to_datetime(
                    cached["Date"],
                    errors="coerce"
                )

                cached["NiftyClose"] = pd.to_numeric(
                    cached["NiftyClose"],
                    errors="coerce"
                )

                cached = cached.dropna(
                    subset=["Date", "NiftyClose"]
                )

                cached = (
                    cached
                    .drop_duplicates(
                        subset=["Date"],
                        keep="last"
                    )
                    .sort_values("Date")
                    .reset_index(drop=True)
                )

            else:

                cached = pd.DataFrame(
                    columns=["Date", "NiftyClose"]
                )

        except Exception as e:

            print(
                f"Nifty history cache read error: {e}"
            )

            cached = pd.DataFrame(
                columns=["Date", "NiftyClose"]
            )

    target_date = pd.Timestamp(
        latest_date
    ).normalize()

    cached_asof = cached[
        cached["Date"] <= target_date
    ]

    cache_is_current = (
        len(cached_asof) >= NIFTY_HISTORY_MIN_BARS
        and not cached_asof.empty
        and cached_asof["Date"].max() == target_date
    )

    if cache_is_current:

        print(
            f"Nifty history cache hit: "
            f"{NIFTY_HISTORY_CACHE} "
            f"({len(cached_asof)} closes through {target_date.date()})"
        )

        return cached

    fetch_start = (
        pd.Timestamp(latest_date)
        - pd.Timedelta(days=NIFTY_HISTORY_LOOKBACK_DAYS)
    ).date()

    if not cached.empty and len(cached_asof) >= NIFTY_HISTORY_MIN_BARS:

        last_cached_date = (
            cached["Date"].max().date()
        )

        if last_cached_date < latest_date:
            overlap_start = (
                pd.Timestamp(last_cached_date)
                - pd.Timedelta(days=5)
            ).date()

            fetch_start = max(
                fetch_start,
                overlap_start
            )

    print(
        f"Downloading Nifty 50 daily history "
        f"from {fetch_start} to {latest_date}..."
    )

    downloaded = fetch_nifty_index_history(
        fetch_start,
        latest_date
    )

    combined = pd.concat(
        [cached, downloaded],
        ignore_index=True
    )

    combined["Date"] = pd.to_datetime(
        combined["Date"],
        errors="coerce"
    )

    combined["NiftyClose"] = pd.to_numeric(
        combined["NiftyClose"],
        errors="coerce"
    )

    combined = combined.dropna(
        subset=["Date", "NiftyClose"]
    )

    combined = (
        combined
        .drop_duplicates(
            subset=["Date"],
            keep="last"
        )
        .sort_values("Date")
        .tail(260)
        .reset_index(drop=True)
    )

    combined.to_csv(
        NIFTY_HISTORY_CACHE,
        index=False,
        date_format="%Y-%m-%d"
    )

    aligned = combined[
        combined["Date"] <= target_date
    ]

    if (
        aligned.empty
        or aligned["Date"].max() != target_date
    ):

        raise RuntimeError(
            "Nifty history does not contain the latest NSE EOD date "
            f"{target_date.date()}."
        )

    if len(aligned) < NIFTY_HISTORY_MIN_BARS:

        raise RuntimeError(
            f"At least {NIFTY_HISTORY_MIN_BARS} Nifty closes are required "
            "to calculate the 20D return and market regime; "
            f"found {len(aligned)}."
        )

    print(
        f"Nifty history cached: "
        f"{NIFTY_HISTORY_CACHE} "
        f"({len(combined)} rows)"
    )

    return combined


# ============================================================
# 20D AVERAGE VOLUME
# ============================================================

def calculate_average_volume(
    historical
):
    """Calculate the baseline from exactly the previous 20 complete EOD sessions.

    The current EOD session is not included. A symbol needs a valid volume value
    in all 20 sessions; otherwise its baseline is marked WAIT_FOR_DATA later.
    """
    print("\nSTEP 4: Calculating prior-20-session average volume...")
    recent = historical[-20:]
    if len(recent) < 20:
        print(f"[RVOL] WAIT_FOR_DATA: only {len(recent)}/20 prior sessions available")
        return pd.DataFrame(columns=["TckrSymb", "AvgVolume20D", "AvgVolumeSessions"])

    frames = []
    for df in recent:
        if not {"TckrSymb", "TtlTradgVol"}.issubset(df.columns):
            continue
        temp = df[["TckrSymb", "TtlTradgVol"]].copy()
        temp["TtlTradgVol"] = pd.to_numeric(temp["TtlTradgVol"], errors="coerce")
        temp = temp.dropna(subset=["TckrSymb", "TtlTradgVol"])
        temp = temp[temp["TtlTradgVol"] >= 0]
        frames.append(temp.drop_duplicates("TckrSymb", keep="last"))

    if not frames:
        return pd.DataFrame(columns=["TckrSymb", "AvgVolume20D", "AvgVolumeSessions"])

    all_volume = pd.concat(frames, ignore_index=True)
    summary = all_volume.groupby("TckrSymb")["TtlTradgVol"].agg(
        AvgVolume20D="mean", AvgVolumeSessions="count"
    ).reset_index()
    # Keep incomplete rows for an explicit WAIT_FOR_DATA state; never infer PASS.
    summary.loc[summary["AvgVolumeSessions"] != 20, "AvgVolume20D"] = float("nan")
    print(f"[RVOL] Baselines: {len(summary)} symbols; complete 20-session baselines: {(summary['AvgVolumeSessions'] == 20).sum()}")
    return summary


# ============================================================
# RVOL
# ============================================================

def calculate_rvol(
    current,
    avg_volume
):
    print("\nSTEP 6: Calculating RVOL for primary-shortlisted stocks...")
    # The primary shortlist stage may already have attached the 20-session
    # baseline before the 5-day filter. Avoid duplicate AvgVolume columns.
    if {"AvgVolume20D", "AvgVolumeSessions"}.issubset(current.columns):
        result = current.copy()
    else:
        result = current.merge(avg_volume, on="TckrSymb", how="left")
    if "AvgVolumeSessions" not in result.columns:
        result["AvgVolumeSessions"] = 0
    result["AvgVolumeSessions"] = pd.to_numeric(result["AvgVolumeSessions"], errors="coerce").fillna(0).astype(int)
    result["RVOL"] = result["TtlTradgVol"] / result["AvgVolume20D"]
    result["DailyVolumePct20D"] = result["RVOL"] * 100
    result["RVOLStatus"] = result.apply(
        lambda row: "PASS" if row["AvgVolumeSessions"] == 20 and pd.notna(row["AvgVolume20D"]) and row["AvgVolume20D"] > 0 and pd.notna(row["RVOL"]) else "WAIT_FOR_DATA",
        axis=1,
    )
    print(f"[RVOL] Calculated: {(result['RVOLStatus'] == 'PASS').sum()}; WAIT_FOR_DATA: {(result['RVOLStatus'] == 'WAIT_FOR_DATA').sum()}")
    return result


# ============================================================
# 5D VOLUME
# ============================================================

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
    """Keep candidates with complete volume history; delivery is the requested gate.

    Delivery Category A (five-session average >=60%) has already been applied after
    RVOL >1.5. Category B (each of five daily values >=60%) is reported separately.
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
        "Dual Delivery Categories are applied after RVOL > 1.5; Category A average >=60% is the downstream gate. "
        f"Audit: {audit_path}"
    )
    return primary


def select_rvol_above_threshold(result, eod_date, minimum_rvol=1.5):
    """Keep every valid Main Board candidate with RVOL strictly greater than 1.5.

    There is deliberately no Top-20/Top-50 cap here. Missing 20-session baselines
    stay WAIT_FOR_DATA and never qualify.
    """
    if result is None or result.empty:
        print("[RVOL > 1.5] No candidates available.")
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
    print(f"[RVOL > 1.5] Candidates={len(selected)}; no Top-50 cap. Audit: {audit_path}")
    return selected


# ============================================================
# PRICE + VOLUME
# ============================================================

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

def calculate_trend(result, historical):
    """Calculate EMA20/EMA44 and descriptive EMA44 states for screened candidates only.

    EMA44 proximity is informational: NOT_NEAR_EMA44 never rejects a candidate.
    A breakout/breakdown requires an EOD cross plus volume confirmation.
    """
    print("\nSTEP 9: Calculating EMA20 / EMA44 + RSI14 + ADX14...")
    print("Indicators run only for the current screened candidates; EMA44 proximity is not a rejection gate.")

    trend_rows = []
    _, history_by_symbol = prepare_history_by_symbol(historical)

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
            "RSI14": float("nan"), "ADX14": float("nan"),
            "TrendClassification": "Insufficient Data",
        }
        if hist is None or hist.empty:
            trend_rows.append(missing)
            continue

        hist = hist.copy().sort_values("Date", kind="mergesort").reset_index(drop=True)
        for column in ("ClsPric", "HghPric", "LwPric", "OpnPric", "TtlTradgVol"):
            if column in hist.columns:
                hist[column] = pd.to_numeric(hist[column], errors="coerce")
        hist = hist.dropna(subset=["ClsPric"]).reset_index(drop=True)
        if len(hist) < 50:
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

        if current_close > ema20 and ema20 > ema44 and pd.notna(rsi) and rsi >= 50 and pd.notna(adx) and adx >= 20:
            trend = "Strong Bullish Trend"
        elif current_close > ema20 and ema20 > ema44:
            trend = "Bullish Trend"
        elif current_close < ema20 and ema20 < ema44 and pd.notna(rsi) and rsi < 50 and pd.notna(adx) and adx >= 20:
            trend = "Strong Bearish Trend"
        elif current_close < ema20 and ema20 < ema44:
            trend = "Bearish Trend"
        elif current_close > ema44 and ema20 > ema44:
            trend = "Mixed / Improving"
        elif current_close < ema44 and ema20 < ema44:
            trend = "Mixed / Weak"
        else:
            trend = "Sideways / Mixed"

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
            "ADX14": adx,
            "TrendClassification": trend,
        })

    trend_columns = [
        "TckrSymb", "EMA20", "EMA44", "EMA44DistancePct", "EMA44Trend",
        "EMA44Position", "EMA44ProximityStatus", "EMA44SignalStatus",
        "PriceChange5D", "RSI14", "ADX14", "TrendClassification",
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

def calculate_breakout_pullback(
    result,
    historical
):

    print(
        "\nSTEP 10: Breakout / "
        "Pullback Detection..."
    )

    rows = []

    _, history_by_symbol = prepare_history_by_symbol(
        historical
    )

    for symbol in result["TckrSymb"]:

        hist = history_by_symbol.get(symbol)

        if hist is None or hist.empty:

            rows.append({
                "TckrSymb": symbol,
                "RecentSwingHigh":
                    float("nan"),
                "RecentSwingLow":
                    float("nan"),
                "High20D":
                    float("nan"),
                "High50D":
                    float("nan"),
                "ATR14":
                    float("nan"),
                "BreakoutStatus":
                    "Insufficient Data",
                "PullbackStatus":
                    "Insufficient Data",
                "SetupType":
                    "Insufficient Data",
            })

            continue

        hist = hist.copy()

        if len(hist) < 20:

            rows.append({
                "TckrSymb": symbol,
                "RecentSwingHigh":
                    float("nan"),
                "RecentSwingLow":
                    float("nan"),
                "High20D":
                    float("nan"),
                "High50D":
                    float("nan"),
                "ATR14":
                    float("nan"),
                "BreakoutStatus":
                    "Insufficient Data",
                "PullbackStatus":
                    "Insufficient Data",
                "SetupType":
                    "Insufficient Data",
            })

            continue

        hist["ATR14"] = calculate_atr(
            hist,
            14
        )

        current_close = float(
            hist["ClsPric"].iloc[-1]
        )

        current_open = float(
            hist["OpnPric"].iloc[-1]
        ) if "OpnPric" in hist.columns and pd.notna(hist["OpnPric"].iloc[-1]) else float("nan")

        previous_close = float(
            hist["ClsPric"].iloc[-2]
        ) if len(hist) >= 2 and pd.notna(hist["ClsPric"].iloc[-2]) else float("nan")

        current_high = float(
            hist["HghPric"].iloc[-1]
        )

        current_low = float(
            hist["LwPric"].iloc[-1]
        )

        current_volume = float(
            hist["TtlTradgVol"].iloc[-1]
        )

        previous = hist.iloc[:-1].copy()

        high20 = float(
            previous["HghPric"]
            .tail(20)
            .max()
        )

        high50 = float(
            previous["HghPric"]
            .tail(50)
            .max()
        )

        recent_swing_high = high20

        recent_swing_low = float(
            previous["LwPric"]
            .tail(20)
            .min()
        )

        atr = float(
            hist["ATR14"].iloc[-1]
        )

        previous_avg_volume = float(
            previous["TtlTradgVol"]
            .tail(20)
            .mean()
        )

        if previous_avg_volume > 0:

            current_rvol = (
                current_volume
                / previous_avg_volume
            )

        else:

            current_rvol = 0.0

        candle_range = (
            current_high
            - current_low
        )

        if candle_range > 0:

            clv = (
                current_close
                - current_low
            ) / candle_range

        else:

            clv = 0.5

        # ----------------------------
        # BREAKOUT
        # ----------------------------
        # Master V8 rule: a confirmed breakout requires a strong closing candle
        # (CLV strictly greater than 0.75), not merely a close in the upper half.
        breakout = False

        if (
            current_close > high20
            and current_rvol >= 2.0
            and clv > 0.75
        ):

            breakout = True

        elif (
            current_close > high50
            and current_rvol >= 1.5
            and clv > 0.75
        ):

            breakout = True

        if (
            current_close > high20
            and current_close > high50
            and current_rvol >= 2.0
            and clv > 0.75
        ):

            breakout_status = (
                "Strong Breakout"
            )

        elif breakout:

            breakout_status = "Breakout"

        elif (
            current_close
            >= high20 * 0.98
            and current_rvol >= 1.2
        ):

            breakout_status = (
                "Near Breakout"
            )

        else:

            breakout_status = (
                "No Breakout"
            )

        # ----------------------------
        # PULLBACK
        # ----------------------------

        ema20 = result.loc[
            result["TckrSymb"] == symbol,
            "EMA20"
        ]

        ema44 = result.loc[
            result["TckrSymb"] == symbol,
            "EMA44"
        ]

        trend_value = result.loc[
            result["TckrSymb"] == symbol,
            "TrendClassification"
        ]

        ema20_value = (
            float(ema20.iloc[0])
            if len(ema20) > 0
            and pd.notna(ema20.iloc[0])
            else float("nan")
        )

        ema44_value = (
            float(ema44.iloc[0])
            if len(ema44) > 0
            and pd.notna(ema44.iloc[0])
            else float("nan")
        )

        trend_text = (
            str(trend_value.iloc[0])
            if len(trend_value) > 0
            else "Insufficient Data"
        )

        lookback_high = float(
            previous["HghPric"]
            .tail(20)
            .max()
        )

        correction_from_high = 0.0

        if lookback_high > 0:

            correction_from_high = (
                (
                    lookback_high
                    - current_close
                )
                / lookback_high
            ) * 100

        near_ema20 = False
        near_ema44 = False

        if pd.notna(ema20_value):

            near_ema20 = (
                abs(
                    current_close
                    - ema20_value
                )
                / ema20_value
                <= 0.03
            )

        if pd.notna(ema44_value):

            near_ema44 = (
                abs(
                    current_close
                    - ema44_value
                )
                / ema44_value
                <= 0.03
            )

        controlled_pullback = (
            1.0
            <= correction_from_high
            <= 15.0
        )

        # Explicit bullish reversal candle confirmation for a pullback:
        # current close > open, current close > previous close, and CLV > 0.50.
        bullish_reversal_candle = (
            pd.notna(current_open)
            and pd.notna(previous_close)
            and current_close > current_open
            and current_close > previous_close
            and clv > 0.50
        )

        low_volume_days = result.loc[
            result["TckrSymb"] == symbol,
            "LowVolumeDays5D"
        ]

        low_days = (
            int(
                low_volume_days.iloc[0]
            )
            if len(low_volume_days) > 0
            and pd.notna(
                low_volume_days.iloc[0]
            )
            else 0
        )

        pullback_structure = (
            ("Bullish" in trend_text)
            and controlled_pullback
            and (near_ema20 or near_ema44)
            and current_rvol <= 1.5
        )

        # A confirmed pullback needs both volume contraction (>=3 of 5 days
        # below the 20-session average) and a bullish reversal candle.
        if pullback_structure and low_days >= 3 and bullish_reversal_candle:
            pullback_status = "Strong Pullback"

        elif (
            controlled_pullback
            and (near_ema20 or near_ema44)
        ):
            # Keep incomplete structures informational; never treat them as confirmed.
            pullback_status = "Possible Pullback"

        else:

            pullback_status = (
                "No Pullback"
            )

        if (
            breakout_status
            == "Strong Breakout"
        ):

            setup_type = "Breakout"

        elif (
            breakout_status
            == "Breakout"
        ):

            setup_type = "Breakout"

        elif (
            pullback_status
            == "Strong Pullback"
        ):

            setup_type = "Pullback"

        elif (
            pullback_status
            == "Pullback"
        ):

            setup_type = "Pullback"

        elif (
            breakout_status
            == "Near Breakout"
        ):

            setup_type = "Pre-Breakout"

        elif (
            pullback_status
            == "Possible Pullback"
        ):

            setup_type = (
                "Possible Pullback"
            )

        else:

            setup_type = (
                "No Clear Setup"
            )

        rows.append({
            "TckrSymb": symbol,
            "RecentSwingHigh":
                recent_swing_high,
            "RecentSwingLow":
                recent_swing_low,
            "High20D": high20,
            "High50D": high50,
            "ATR14": atr,
            "BreakoutStatus":
                breakout_status,
            "PullbackStatus":
                pullback_status,
            "SetupType":
                setup_type,
            "CorrectionFromHighPct":
                correction_from_high,
            "SetupRVOL":
                current_rvol,
        })

    setup_columns = [
        "TckrSymb", "RecentSwingHigh", "RecentSwingLow", "High20D", "High50D",
        "ATR14", "BreakoutStatus", "PullbackStatus", "SetupType",
        "CorrectionFromHighPct", "SetupRVOL",
    ]
    # Preserve the merge key when there are no delivery-qualified candidates.
    setup_df = pd.DataFrame(rows, columns=setup_columns)

    result = result.merge(
        setup_df,
        on="TckrSymb",
        how="left"
    )

    print(
        "Breakout / Pullback "
        "calculation completed."
    )

    return result


# ============================================================
# STEP 11 / SUPPORT & RESISTANCE
# ============================================================

def calculate_support_resistance(
    result,
    historical
):

    print(
        "\nSTEP 11: Support / "
        "Resistance Detection..."
    )

    sr_columns = [
        "PDH", "PDL", "PWH", "PWL", "SR20DHigh", "SR50DHigh",
        "SRSwingHigh", "SRSwingLow", "SRSupport", "SRResistance", "BreakoutLevel",
        "EntryZoneLow", "EntryZoneHigh", "SRStatus",
    ]
    if result is None or result.empty:
        # No screened candidates means there is no need to index historical dates.
        # Keep the output schema stable so downstream V8 layers can report WAIT_FOR_DATA.
        result = result.copy() if isinstance(result, pd.DataFrame) else pd.DataFrame()
        for column in sr_columns:
            if column not in result.columns:
                result[column] = pd.Series(dtype="object")
        return result

    rows = []

    # --------------------------------------------------------
    # Build chronological history
    # --------------------------------------------------------

    all_history, history_by_symbol = prepare_history_by_symbol(
        historical
    )

    # --------------------------------------------------------
    # Previous trading day
    # --------------------------------------------------------

    unique_dates = sorted(
        all_history["Date"].unique()
    )

    previous_date = None

    if len(unique_dates) >= 2:
        previous_date = unique_dates[-1]

    # --------------------------------------------------------
    # Previous calendar week
    # --------------------------------------------------------

    latest_date = pd.Timestamp(
        unique_dates[-1]
    )

    current_week = (
        latest_date
        - pd.Timedelta(
            days=latest_date.weekday()
        )
    ).normalize()

    previous_week_start = (
        current_week
        - pd.Timedelta(days=7)
    )

    previous_week_end = (
        current_week
        - pd.Timedelta(days=1)
    )

    previous_week_data = all_history[
        (
            all_history["Date"]
            >= previous_week_start
        )
        &
        (
            all_history["Date"]
            <= previous_week_end
        )
    ]

    previous_week_by_symbol = {
        symbol: frame
        for symbol, frame in previous_week_data.groupby(
            "TckrSymb",
            sort=False,
        )
    }

    # --------------------------------------------------------
    # Per stock
    # --------------------------------------------------------

    for symbol in result["TckrSymb"]:

        stock = history_by_symbol.get(symbol)

        if stock is None or len(stock) < 2:

            rows.append({
                "TckrSymb": symbol,
                "PDH": float("nan"),
                "PDL": float("nan"),
                "PWH": float("nan"),
                "PWL": float("nan"),
                "SR20DHigh": float("nan"),
                "SR50DHigh": float("nan"),
                "SRSwingHigh": float("nan"),
                "SRSwingLow": float("nan"),
                "SRSupport": float("nan"),
                "SRResistance": float("nan"),
                "BreakoutLevel": float("nan"),
                "EntryZoneLow": float("nan"),
                "EntryZoneHigh": float("nan"),
                "SRStatus": "Insufficient Data",
            })

            continue

        current = stock.iloc[-1]

        current_close = float(
            current["ClsPric"]
        )

        # ----------------------------------------------------
        # Previous Day High / Low
        # ----------------------------------------------------

        previous_rows = stock.iloc[:-1]

        previous_day = (
            previous_rows.iloc[-1]
        )

        pdh = float(
            previous_day["HghPric"]
        )

        pdl = float(
            previous_day["LwPric"]
        )

        # ----------------------------------------------------
        # Previous Week High / Low
        # ----------------------------------------------------

        stock_previous_week = previous_week_by_symbol.get(
            symbol
        )

        if stock_previous_week is not None and len(stock_previous_week) > 0:

            pwh = float(
                stock_previous_week[
                    "HghPric"
                ].max()
            )

            pwl = float(
                stock_previous_week[
                    "LwPric"
                ].min()
            )

        else:

            pwh = float("nan")
            pwl = float("nan")

        # ----------------------------------------------------
        # 20D / 50D High
        # ----------------------------------------------------

        previous_20 = (
            previous_rows.tail(20)
        )

        previous_50 = (
            previous_rows.tail(50)
        )

        high20 = float(
            previous_20[
                "HghPric"
            ].max()
        )

        low20 = float(
            previous_20[
                "LwPric"
            ].min()
        )

        high50 = float(
            previous_50[
                "HghPric"
            ].max()
        )

        low50 = float(
            previous_50[
                "LwPric"
            ].min()
        )

        # ----------------------------------------------------
        # Recent Swing High / Low
        # ----------------------------------------------------

        swing_high = float(
            previous_rows
            .tail(20)[
                "HghPric"
            ]
            .max()
        )

        swing_low = float(
            previous_rows
            .tail(20)[
                "LwPric"
            ]
            .min()
        )

        # ----------------------------------------------------
        # EMA20 / EMA44 from existing result
        # ----------------------------------------------------

        row_match = result[
            result["TckrSymb"]
            == symbol
        ]

        if len(row_match) > 0:

            ema20 = row_match[
                "EMA20"
            ].iloc[0]

            ema44 = row_match[
                "EMA44"
            ].iloc[0]

        else:

            ema20 = float("nan")
            ema44 = float("nan")

        # ----------------------------------------------------
        # SUPPORT CANDIDATES
        # ----------------------------------------------------

        support_candidates = [
            pdl,
            pwl,
            low20,
            low50,
            swing_low,
        ]

        if pd.notna(ema20):
            support_candidates.append(
                float(ema20)
            )

        if pd.notna(ema44):
            support_candidates.append(
                float(ema44)
            )

        support_candidates = [
            x
            for x in support_candidates
            if pd.notna(x)
            and x > 0
            and x <= current_close
        ]

        # Nearest support below price
        if support_candidates:

            support = max(
                support_candidates
            )

        else:

            support = float("nan")

        # ----------------------------------------------------
        # RESISTANCE CANDIDATES
        # ----------------------------------------------------

        resistance_candidates = [
            pdh,
            pwh,
            high20,
            high50,
            swing_high,
        ]

        resistance_candidates = [
            x
            for x in resistance_candidates
            if pd.notna(x)
            and x > 0
            and x >= current_close
        ]

        # Nearest resistance above price
        if resistance_candidates:

            resistance = min(
                resistance_candidates
            )

        else:

            resistance = float("nan")

        # ----------------------------------------------------
        # If current price is already above all
        # resistance levels, use strongest level.
        # ----------------------------------------------------

        if pd.isna(resistance):

            fallback_resistance = [
                pdh,
                pwh,
                high20,
                high50,
                swing_high,
            ]

            fallback_resistance = [
                x
                for x in fallback_resistance
                if pd.notna(x)
                and x > 0
            ]

            if fallback_resistance:

                resistance = max(
                    fallback_resistance
                )

        # ----------------------------------------------------
        # Breakout Level
        # ----------------------------------------------------

        breakout_level = resistance

        # ----------------------------------------------------
        # Entry Zone
        #
        # For a bullish setup:
        # Entry zone is around resistance/support.
        #
        # We do NOT create a BUY signal here.
        # This is only price-structure information.
        # ----------------------------------------------------

        if pd.notna(resistance):

            if (
                current_close
                <= resistance
            ):

                entry_zone_low = (
                    resistance * 0.995
                )

                entry_zone_high = (
                    resistance * 1.005
                )

            else:

                # Already above resistance.
                # Keep zone around breakout level.
                entry_zone_low = (
                    resistance
                )

                entry_zone_high = (
                    resistance * 1.01
                )

        else:

            entry_zone_low = (
                support
                if pd.notna(support)
                else float("nan")
            )

            entry_zone_high = (
                support
                if pd.notna(support)
                else float("nan")
            )

        # ----------------------------------------------------
        # S/R STATUS
        # ----------------------------------------------------

        if (
            pd.notna(resistance)
            and current_close > resistance
        ):

            sr_status = (
                "Above Resistance"
            )

        elif (
            pd.notna(resistance)
            and resistance > 0
            and (
                (
                    resistance
                    - current_close
                )
                / resistance
            ) <= 0.02
        ):

            sr_status = (
                "Near Resistance"
            )

        elif (
            pd.notna(support)
            and support > 0
            and (
                (
                    current_close
                    - support
                )
                / current_close
            ) <= 0.03
        ):

            sr_status = (
                "Near Support"
            )

        else:

            sr_status = (
                "Between Support/Resistance"
            )

        rows.append({
            "TckrSymb": symbol,

            "PDH": pdh,
            "PDL": pdl,

            "PWH": pwh,
            "PWL": pwl,

            "SR20DHigh": high20,
            "SR50DHigh": high50,

            "SRSwingHigh": swing_high,
            "SRSwingLow": swing_low,

            "SRSupport": support,
            "SRResistance": resistance,

            "BreakoutLevel":
                breakout_level,

            "EntryZoneLow":
                entry_zone_low,

            "EntryZoneHigh":
                entry_zone_high,

            "SRStatus":
                sr_status,
        })

    sr_columns = [
        "TckrSymb", "PDH", "PDL", "PWH", "PWL", "SR20DHigh", "SR50DHigh",
        "SRSwingHigh", "SRSwingLow", "SRSupport", "SRResistance", "BreakoutLevel",
        "EntryZoneLow", "EntryZoneHigh", "SRStatus",
    ]
    # Preserve the merge key when there are no delivery-qualified candidates.
    sr_df = pd.DataFrame(rows, columns=sr_columns)

    result = result.merge(
        sr_df,
        on="TckrSymb",
        how="left"
    )

    print(
        "Support / Resistance "
        "calculation completed."
    )

    return result


# ============================================================
# RELATIVE STRENGTH VS NIFTY
# ============================================================

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

    if len(nifty) < 21:

        raise RuntimeError(
            "Insufficient Nifty history for 20D return calculation."
        )

    nifty_last = nifty.iloc[-1]

    if (
        pd.Timestamp(nifty_last["Date"]).normalize()
        != pd.Timestamp(latest_date).normalize()
    ):

        raise RuntimeError(
            "Nifty history date does not match latest NSE EOD date."
        )

    nifty_base_close = float(
        nifty["NiftyClose"].iloc[-21]
    )

    nifty_last_close = float(
        nifty_last["NiftyClose"]
    )

    if nifty_base_close <= 0:

        raise RuntimeError(
            "Nifty 20D base close must be greater than zero."
        )

    nifty_return_20d = (
        (nifty_last_close / nifty_base_close) - 1
    ) * 100

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

def select_top20_analysis_candidates(result, eod_date):
    """Annotate every RVOL > 1.5 technical candidate after core EOD screens.

    Delivery Category A has passed: the average Delivery % across five valid sessions is >= 60.00%; Category B separately marks every day >=60.00%. A candidate
    must also have valid 20-session RVOL data, a real Breakout/Pullback setup, constructive
    trend/candle and setup-specific volume rules. Negative relative strength is
    retained as a scoring/ranking warning, not a standalone hard rejection.
    Final sector/news/3+1, risk/reward and chase gates remain in run_eod_layers().
    """
    if result is None or result.empty:
        print("[CANDIDATE SCREEN] No rows available; no candidates selected.")
        return result.copy() if isinstance(result, pd.DataFrame) else pd.DataFrame()

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
    # Keep every RVOL > 1.5 row flowing through sector/news/3+1 evidence collection.
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

    ranks = dict(zip(frame["TckrSymb"].astype(str).str.upper(), frame["CandidateRank"]))
    audit["CandidateRank"] = audit["TckrSymb"].map(ranks)
    audit.loc[audit["CandidateScreenStatus"].eq("PASS") & audit["CandidateRank"].isna(), "CandidateScreenStatus"] = "PASS"
    audit_path = os.path.join("data", "reports", f"v8_candidate_selection_audit_{pd.Timestamp(eod_date).strftime('%Y%m%d')}.csv")
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    audit.to_csv(audit_path, index=False)
    os.makedirs("outputs", exist_ok=True)
    frame.to_csv(os.path.join("outputs", "v8_pre_news_rvol_gt_1_5_candidates.csv"), index=False)

    counts = audit["CandidateScreenStatus"].value_counts().to_dict()
    passed = int(audit["CandidateScreenStatus"].eq("PASS").sum())
    print("[CANDIDATE SCREEN] Audit: " + audit_path)
    print(f"[CANDIDATE SCREEN] Core technical pass among RVOL > 1.5 candidates: {passed}/{len(frame)}")
    print(f"[CANDIDATE SCREEN] Continuing all RVOL > 1.5 candidates into news/sector/EOD evidence analysis: {len(frame)} (no Top-20/Top-50 cap)")
    print(f"[CANDIDATE SCREEN] Status counts: {counts}")
    return frame


# ============================================================
# DISPLAY ALL QUALIFYING RVOL CANDIDATES
# ============================================================

def display_top20(result):

    print(
        "\n"
        + "=" * 110
    )

    print(
        "V8 TECHNICAL CANDIDATES (RVOL > 1.5; NO RVOL CAP)"
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

def main():

    print(
        "\n"
        + "=" * 70
    )

    print(
        "NSE V8 MODULE A"
    )

    print(
        "NSE MAINBOARD + RVOL > 1.5 + DUAL DELIVERY + LIQUIDITY + FUNDAMENTALS + 5D "
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

    # --------------------------------------------------------
    # STEP 3: LOAD HISTORY AND CALCULATE RVOL BEFORE DELIVERY
    # --------------------------------------------------------
    historical = collect_historical_days(eod_date, HISTORY_DAYS)
    avg_volume = calculate_average_volume(historical)
    print("\nSTEP 3A: Calculate RVOL for the full verified Main Board universe...")
    current = calculate_rvol(current, avg_volume)
    current = select_rvol_above_threshold(current, eod_date, minimum_rvol=1.5)

    # --------------------------------------------------------
    # STEP 4: TWO DELIVERY CATEGORIES, AFTER RVOL > 1.5
    # --------------------------------------------------------
    print("\nSTEP 4: Applying separate 5-session Delivery Categories after RVOL > 1.5...")
    if current.empty:
        delivery_audit = current.copy()
        for col in ["DeliverySessions", "DeliveryDailyPassCount", "DeliveryMin5D", "AvgDelivery5D", "LatestDeliveryPct", "DeliveryStatus", "DeliveryFilterStatus", "DeliveryCategoryAStatus", "DeliveryCategoryBStatus"]:
            if col not in current.columns:
                current[col] = pd.Series(dtype="object")
    else:
        try:
            delivery_qualified, delivery_audit = apply_delivery_filter(
                current, eod_date, symbol_col="TckrSymb", series_col="SctySrs", minimum_average=60.0
            )
            os.makedirs("outputs", exist_ok=True)
            delivery_audit.to_csv("outputs/v8_delivery_dual_category_audit.csv", index=False)
            current = delivery_qualified.copy()
            if not current.empty:
                current["DeliveryFilterStatus"] = current["DeliveryStatus"].astype(str)
            print(f"[DELIVERY] Category A (5-day average >=60%) qualified={len(current)}")
            print("[DELIVERY] Category B (each of 5 days >=60%) is written as an independent report.")
        except Exception as exc:
            print(f"[DELIVERY] WAIT_FOR_DATA: delivery categories could not be verified: {exc}")
            current = current.iloc[0:0].copy()
            delivery_audit = current.copy()
            for col in ["DeliverySessions", "DeliveryDailyPassCount", "DeliveryMin5D", "AvgDelivery5D", "LatestDeliveryPct", "DeliveryStatus", "DeliveryFilterStatus", "DeliveryCategoryAStatus", "DeliveryCategoryBStatus"]:
                if col not in current.columns:
                    current[col] = pd.Series(dtype="object")

    # --------------------------------------------------------
    # STEP 5: FUNDAMENTAL DATA COLLECTION FOR ALL DELIVERY A/B STOCKS
    # --------------------------------------------------------
    print("\nSTEP 5: Collecting available fundamental data for every Delivery A/B stock; no fundamental rejection at this stage...")
    create_fundamental_templates()
    try:
        if delivery_audit is None or delivery_audit.empty:
            fundamental_universe = pd.DataFrame()
        else:
            a_pass = delivery_audit.get("DeliveryCategoryAStatus", pd.Series("", index=delivery_audit.index)).astype(str).eq("PASS_AVG_GE_60_PERCENT")
            b_pass = delivery_audit.get("DeliveryCategoryBStatus", pd.Series("", index=delivery_audit.index)).astype(str).eq("PASS_EACH_DAY_GE_60_PERCENT")
            fundamental_universe = delivery_audit.loc[a_pass | b_pass].copy()
            if "TckrSymb" in fundamental_universe.columns:
                fundamental_universe = fundamental_universe.drop_duplicates(subset=["TckrSymb"], keep="first")
        if fundamental_universe.empty:
            fundamental_audit = fundamental_universe.copy()
            fundamental_audit.to_csv("outputs/v8_fundamental_report.csv", index=False)
            for report_name in ["v8_fundamental_complete_data.csv", "v8_fundamental_partial_data.csv", "v8_fundamental_missing_data.csv",
                                "v8_delivery_a_fundamentals.csv", "v8_delivery_b_fundamentals.csv", "v8_delivery_ab_combined_fundamentals.csv"]:
                fundamental_audit.to_csv(os.path.join("outputs", report_name), index=False)
        else:
            # Fetch available fundamentals for every unique symbol in Delivery A/B.
            # Provider failures and missing metrics are recorded, never used to reject.
            try:
                collect_missing_fundamentals(fundamental_universe, asof_date=eod_date)
            except Exception as provider_exc:
                os.makedirs("outputs", exist_ok=True)
                pd.DataFrame([{
                    "ProviderStatus": "PROVIDER_STAGE_ERROR",
                    "ProviderReason": f"{type(provider_exc).__name__}: {provider_exc}",
                }]).to_csv("outputs/v8_fundamental_provider_diagnostics.csv", index=False)
                print(f"[FUNDAMENTAL PROVIDER] Stage error; keep all candidates: {provider_exc}")
            _, fundamental_audit = apply_fundamental_filter(fundamental_universe, eod_date)
            try:
                # Collection keeps every Delivery A/B row. The strong-fundamental
                # assessment is applied only after collection is complete.
                fundamental_audit = build_fundamental_shortlist(fundamental_audit, eod_date)
                fundamental_audit["FundamentalAssessmentStatus"] = fundamental_audit["FundamentalShortlistStatus"].astype(str)
                fundamental_audit["FundamentalAssessmentReason"] = fundamental_audit["FundamentalShortlistReason"].astype(str)
            except Exception as shortlist_exc:
                print(f"[FUNDAMENTAL SHORTLIST] Assessment failed closed; no candidates advance: {shortlist_exc}")
                fundamental_audit["FundamentalShortlistStatus"] = "WAIT_FOR_DATA"
                fundamental_audit["FundamentalShortlistReason"] = f"SHORTLIST_ASSESSMENT_ERROR:{type(shortlist_exc).__name__}"
                fundamental_audit["FundamentalAssessmentStatus"] = "WAIT_FOR_DATA"
                fundamental_audit["FundamentalAssessmentReason"] = fundamental_audit["FundamentalShortlistReason"]
            # Refresh the main report with the final assessment fields while
            # retaining all collected rows, including FAIL and WAIT_FOR_DATA.
            os.makedirs("outputs", exist_ok=True)
            fundamental_audit.to_csv("outputs/v8_fundamental_report.csv", index=False)
            fundamental_audit[fundamental_audit.get("FundamentalStatus", pd.Series("", index=fundamental_audit.index)).astype(str).eq("COMPLETE")].to_csv("outputs/v8_fundamental_complete_data.csv", index=False)
            fundamental_audit[fundamental_audit.get("FundamentalStatus", pd.Series("", index=fundamental_audit.index)).astype(str).eq("PARTIAL_DATA")].to_csv("outputs/v8_fundamental_partial_data.csv", index=False)
            fundamental_audit[fundamental_audit.get("FundamentalStatus", pd.Series("", index=fundamental_audit.index)).astype(str).eq("MISSING_DATA")].to_csv("outputs/v8_fundamental_missing_data.csv", index=False)
            a_mask = fundamental_audit.get("DeliveryCategoryAStatus", pd.Series("", index=fundamental_audit.index)).astype(str).eq("PASS_AVG_GE_60_PERCENT")
            b_mask = fundamental_audit.get("DeliveryCategoryBStatus", pd.Series("", index=fundamental_audit.index)).astype(str).eq("PASS_EACH_DAY_GE_60_PERCENT")
            fundamental_audit.loc[a_mask].to_csv("outputs/v8_delivery_a_fundamentals.csv", index=False)
            fundamental_audit.loc[b_mask].to_csv("outputs/v8_delivery_b_fundamentals.csv", index=False)
            fundamental_audit.to_csv("outputs/v8_delivery_ab_combined_fundamentals.csv", index=False)
        # all rows retained regardless of fundamental data status in the collection
        # reports above. Only verified strong-fundamental PASS candidates enter
        # the downstream liquidity/technical pipeline after collection is complete.
        category_a_mask = fundamental_audit.get("DeliveryCategoryAStatus", pd.Series("", index=fundamental_audit.index)).astype(str).eq("PASS_AVG_GE_60_PERCENT")
        fundamental_pass_mask = fundamental_audit.get("FundamentalShortlistStatus", pd.Series("", index=fundamental_audit.index)).astype(str).eq("PASS")
        current = fundamental_audit[category_a_mask & fundamental_pass_mask].copy() if not fundamental_audit.empty else fundamental_audit.copy()
        sort_cols = [c for c in ["FundamentalScore", "RVOL"] if c in current.columns]
        if sort_cols and not current.empty:
            current = current.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last", kind="stable").reset_index(drop=True)
        print(f"[FUNDAMENTAL COLLECTION] Category A rows={int(category_a_mask.sum())}; Category B rows={int((fundamental_audit.get('DeliveryCategoryBStatus', pd.Series(dtype=str)).astype(str) == 'PASS_EACH_DAY_GE_60_PERCENT').sum())}; Fundamental PASS advancing={len(current)}; all collection rows retained in reports.")
    except Exception as exc:
        # Fail closed: a failed fundamental collection/assessment must never
        # allow unassessed Delivery-A candidates into liquidity or later gates.
        print(f"[FUNDAMENTAL COLLECTION] Collection/assessment failed; no candidates advance: {exc}")
        fundamental_audit = delivery_audit.copy() if isinstance(delivery_audit, pd.DataFrame) else pd.DataFrame()
        if not fundamental_audit.empty:
            fundamental_audit["FundamentalStatus"] = "MISSING_DATA"
            fundamental_audit["FundamentalReason"] = f"FUNDAMENTAL_COLLECTION_ERROR:{type(exc).__name__}:{exc}"
            fundamental_audit["FundamentalAssessmentStatus"] = "WAIT_FOR_DATA"
            fundamental_audit["FundamentalAssessmentReason"] = fundamental_audit["FundamentalReason"]
            fundamental_audit["FundamentalShortlistStatus"] = "WAIT_FOR_DATA"
            fundamental_audit["FundamentalShortlistReason"] = fundamental_audit["FundamentalReason"]
            os.makedirs("outputs", exist_ok=True)
            fundamental_audit.to_csv("outputs/v8_fundamental_report.csv", index=False)
            fundamental_audit.to_csv("outputs/v8_fundamental_shortlist_all.csv", index=False)
            fundamental_audit[fundamental_audit["FundamentalShortlistStatus"].eq("PASS")].to_csv(
                "outputs/v8_fundamental_shortlist_pass.csv", index=False
            )
        current = pd.DataFrame(columns=list(fundamental_audit.columns) if not fundamental_audit.empty else [])

    # --------------------------------------------------------
    # STEP 6: EXISTING LIQUIDITY FILTER — THRESHOLD RELAXED TO ₹2 CRORE
    # --------------------------------------------------------
    print("\nSTEP 6: Applying existing liquidity gate (20D average traded value >= ₹2 crore)...")
    liquidity_audit_columns = ["LiquiditySessions", "AvgDailyTradedValue20D", "MinimumAvgDailyTradedValueINR", "LiquidityStatus", "LiquidityFilterStatus"]
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

    # Calculate 5-session descriptive volume patterns only after the required
    # RVOL, Delivery, Liquidity, and Fundamental stages have passed.
    result = current.merge(avg_volume, on="TckrSymb", how="left", suffixes=("", "_baseline")) if "AvgVolume20D" not in current.columns else current.copy()
    result = calculate_5d_volume(result, historical)
    result = prepare_primary_shortlist(result, eod_date)
    result = calculate_rvol(result, avg_volume)

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
    os.makedirs("outputs", exist_ok=True)
    result.to_csv("outputs/v8_technical_report.csv", index=False)

    # Check only the selected technical candidates against official NSE RSS feeds
    # and secondary coverage before news confirmation layers are scored.
    news_session_dates = [
        pd.to_datetime(frame["Date"], errors="coerce").dropna().iloc[0]
        for frame in historical[-4:]
        if "Date" in frame.columns and not frame.empty
        and not pd.to_datetime(frame["Date"], errors="coerce").dropna().empty
    ]
    news_session_dates.append(pd.Timestamp(eod_date))
    auto_news, news_feed_status = collect_catalyst_news(
        result,
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

    result = run_eod_layers(
        result,
        historical,
        current,
        nifty_history,
        eod_date,
    )

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
    _append_stage(delivery_audit, "DELIVERY_5D", "DeliveryFilterStatus")
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
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
