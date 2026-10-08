import os
import io
import zipfile
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from v8_layers_14_41 import (
    monitor_positions,
    run_eod_layers,
    validate_next_day,
    write_layer_status_summary,
)

# ============================================================
# NSE V8 MODULE A
# EOD VOLUME + RVOL + 5D + PRICE/VOLUME + CLV
# + TREND + BREAKOUT/PULLBACK + SUPPORT/RESISTANCE + RELATIVE STRENGTH
# ============================================================

NSE_BASE_URL = "https://nsearchives.nseindia.com/content/cm/"
HISTORY_DAYS = 220
DATA_CACHE_DIR = os.path.join("data", "bhavcopy")
BHAVCOPY_404_CACHE_DAYS = 2
NIFTY_HISTORY_CACHE = os.path.join(DATA_CACHE_DIR, "nifty50_index_history.csv")
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

def prepare_equity_data(df):

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

        equity = data[
            data["SctySrs"]
            .astype(str)
            .isin(
                ["EQ", "BE", "SM", "ST", "SZ"]
            )
        ].copy()

        if len(equity) > 0:
            data = equity

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
    days=HISTORY_DAYS
):

    print(
        "\nSTEP 3: Collecting historical "
        "220 trading days..."
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

    while len(historical) < days:

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
        len(cached_asof) >= 21
        and not cached_asof.empty
        and cached_asof["Date"].max() == target_date
    )

    if cache_is_current:

        print(
            f"Nifty history cache hit: "
            f"{NIFTY_HISTORY_CACHE}"
        )

        return cached

    fetch_start = (
        pd.Timestamp(latest_date)
        - pd.Timedelta(days=70)
    ).date()

    if not cached.empty:

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

    if len(aligned) < 21:

        raise RuntimeError(
            "At least 21 Nifty closes are required "
            "to calculate a 20D return."
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

    print(
        "\nSTEP 4: Calculating "
        "20D Average Volume..."
    )

    frames = []

    for df in historical:

        temp = df[
            ["TckrSymb", "TtlTradgVol"]
        ].copy()

        frames.append(temp)

    if not frames:

        return pd.DataFrame()

    all_volume = pd.concat(
        frames,
        ignore_index=True
    )

    avg_volume = (
        all_volume
        .groupby("TckrSymb")[
            "TtlTradgVol"
        ]
        .mean()
        .rename("AvgVolume20D")
        .reset_index()
    )

    print(
        f"20D average calculated for "
        f"{len(avg_volume)} symbols"
    )

    return avg_volume


# ============================================================
# RVOL
# ============================================================

def calculate_rvol(
    current,
    avg_volume
):

    print(
        "\nSTEP 5: Calculating RVOL..."
    )

    result = current.merge(
        avg_volume,
        on="TckrSymb",
        how="left"
    )

    result["RVOL"] = (
        result["TtlTradgVol"]
        / result["AvgVolume20D"]
    )

    result["DailyVolumePct20D"] = (
        result["RVOL"] * 100
    )

    result = result[
        result["AvgVolume20D"].notna()
        & (result["AvgVolume20D"] > 0)
    ].copy()

    print(
        f"RVOL calculated for "
        f"{len(result)} symbols"
    )

    return result


# ============================================================
# 5D VOLUME
# ============================================================

def calculate_5d_volume(
    result,
    historical
):

    print(
        "\nSTEP 6: 5D Volume Analysis..."
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

def calculate_trend(
    result,
    historical
):

    print(
        "\nSTEP 9: Calculating Trend indicators..."
    )

    print(
        "EMA20 / EMA50 / EMA200 "
        "+ RSI14 + ADX14"
    )

    trend_rows = []

    for symbol in result["TckrSymb"]:

        frames = []

        for df in historical:

            temp = df[
                df["TckrSymb"] == symbol
            ][
                [
                    "Date",
                    "OpnPric",
                    "HghPric",
                    "LwPric",
                    "ClsPric",
                    "TtlTradgVol",
                ]
            ].copy()

            if len(temp) > 0:
                frames.append(temp)

        if not frames:

            trend_rows.append({
                "TckrSymb": symbol,
                "EMA20": float("nan"),
                "EMA50": float("nan"),
                "EMA200": float("nan"),
                "RSI14": float("nan"),
                "ADX14": float("nan"),
                "TrendClassification":
                    "Insufficient Data",
            })

            continue

        hist = pd.concat(
            frames,
            ignore_index=True
        )

        hist = hist.sort_values(
            "Date"
        )

        close = pd.to_numeric(
            hist["ClsPric"],
            errors="coerce"
        )

        if len(hist) < 200:

            trend_rows.append({
                "TckrSymb": symbol,
                "EMA20": float("nan"),
                "EMA50": float("nan"),
                "EMA200": float("nan"),
                "RSI14": float("nan"),
                "ADX14": float("nan"),
                "TrendClassification":
                    "Insufficient Data",
            })

            continue

        hist["EMA20"] = close.ewm(
            span=20,
            adjust=False
        ).mean()

        hist["EMA50"] = close.ewm(
            span=50,
            adjust=False
        ).mean()

        hist["EMA200"] = close.ewm(
            span=200,
            adjust=False
        ).mean()

        hist["RSI14"] = calculate_rsi(
            close,
            14
        )

        hist["ADX14"] = calculate_adx(
            hist,
            14
        )

        last = hist.iloc[-1]

        current_close = float(
            last["ClsPric"]
        )

        ema20 = float(
            last["EMA20"]
        )

        ema50 = float(
            last["EMA50"]
        )

        ema200 = float(
            last["EMA200"]
        )

        rsi = float(
            last["RSI14"]
        )

        adx = float(
            last["ADX14"]
        )

        if (
            current_close > ema20
            and ema20 > ema50
            and ema50 > ema200
            and rsi >= 50
            and adx >= 20
        ):

            trend = (
                "Strong Bullish Trend"
            )

        elif (
            current_close > ema20
            and ema20 > ema50
            and ema50 > ema200
        ):

            trend = "Bullish Trend"

        elif (
            current_close < ema20
            and ema20 < ema50
            and ema50 < ema200
            and rsi < 50
            and adx >= 20
        ):

            trend = (
                "Strong Bearish Trend"
            )

        elif (
            current_close < ema20
            and ema20 < ema50
            and ema50 < ema200
        ):

            trend = "Bearish Trend"

        elif (
            current_close > ema50
            and ema20 > ema50
        ):

            trend = "Mixed / Improving"

        elif (
            current_close < ema50
            and ema20 < ema50
        ):

            trend = "Mixed / Weak"

        else:

            trend = "Sideways / Mixed"

        trend_rows.append({
            "TckrSymb": symbol,
            "EMA20": ema20,
            "EMA50": ema50,
            "EMA200": ema200,
            "RSI14": rsi,
            "ADX14": adx,
            "TrendClassification": trend,
        })

    trend_df = pd.DataFrame(
        trend_rows
    )

    result = result.merge(
        trend_df,
        on="TckrSymb",
        how="left"
    )

    print(
        f"Trend indicators calculated for "
        f"{len(trend_df)} symbols"
    )

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

    for symbol in result["TckrSymb"]:

        frames = []

        for df in historical:

            temp = df[
                df["TckrSymb"] == symbol
            ][
                [
                    "Date",
                    "OpnPric",
                    "HghPric",
                    "LwPric",
                    "ClsPric",
                    "TtlTradgVol",
                ]
            ].copy()

            if len(temp) > 0:
                frames.append(temp)

        if not frames:

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

        hist = pd.concat(
            frames,
            ignore_index=True
        )

        hist = hist.sort_values(
            "Date"
        )

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

        breakout = False

        if (
            current_close > high20
            and current_rvol >= 2.0
            and clv >= 0.50
        ):

            breakout = True

        elif (
            current_close > high50
            and current_rvol >= 1.5
            and clv >= 0.50
        ):

            breakout = True

        if (
            current_close > high20
            and current_close > high50
            and current_rvol >= 2.0
            and clv >= 0.75
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

        ema50 = result.loc[
            result["TckrSymb"] == symbol,
            "EMA50"
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

        ema50_value = (
            float(ema50.iloc[0])
            if len(ema50) > 0
            and pd.notna(ema50.iloc[0])
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
        near_ema50 = False

        if pd.notna(ema20_value):

            near_ema20 = (
                abs(
                    current_close
                    - ema20_value
                )
                / ema20_value
                <= 0.03
            )

        if pd.notna(ema50_value):

            near_ema50 = (
                abs(
                    current_close
                    - ema50_value
                )
                / ema50_value
                <= 0.04
            )

        controlled_pullback = (
            1.0
            <= correction_from_high
            <= 15.0
        )

        pullback = (
            (
                "Bullish" in trend_text
                or "Improving" in trend_text
            )
            and controlled_pullback
            and (
                near_ema20
                or near_ema50
            )
            and current_rvol <= 1.5
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

        if (
            pullback
            and low_days >= 3
        ):

            pullback_status = (
                "Strong Pullback"
            )

        elif pullback:

            pullback_status = (
                "Pullback"
            )

        elif (
            controlled_pullback
            and (
                near_ema20
                or near_ema50
            )
        ):

            pullback_status = (
                "Possible Pullback"
            )

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

    setup_df = pd.DataFrame(
        rows
    )

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

    rows = []

    # --------------------------------------------------------
    # Build chronological history
    # --------------------------------------------------------

    all_history = pd.concat(
        historical,
        ignore_index=True
    )

    all_history["Date"] = pd.to_datetime(
        all_history["Date"]
    )

    all_history = all_history.sort_values(
        "Date"
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

    # --------------------------------------------------------
    # Per stock
    # --------------------------------------------------------

    for symbol in result["TckrSymb"]:

        stock = all_history[
            all_history["TckrSymb"]
            == symbol
        ].sort_values("Date")

        if len(stock) < 2:

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

        stock_previous_week = (
            previous_week_data[
                previous_week_data[
                    "TckrSymb"
                ] == symbol
            ]
        )

        if len(stock_previous_week) > 0:

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
        # EMA20 / EMA50 from existing result
        # ----------------------------------------------------

        row_match = result[
            result["TckrSymb"]
            == symbol
        ]

        if len(row_match) > 0:

            ema20 = row_match[
                "EMA20"
            ].iloc[0]

            ema50 = row_match[
                "EMA50"
            ].iloc[0]

        else:

            ema20 = float("nan")
            ema50 = float("nan")

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

        if pd.notna(ema50):
            support_candidates.append(
                float(ema50)
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

    sr_df = pd.DataFrame(
        rows
    )

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
# DISPLAY TOP 20
# ============================================================

def display_top20(result):

    print(
        "\n"
        + "=" * 110
    )

    print(
        "TOP 20 V8 CANDIDATES"
    )

    print(
        "=" * 110
    )

    display = (
        result
        .sort_values(
            by="RVOL",
            ascending=False
        )
        .head(20)
    )

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
            f" | EMA50="
            f"{fmt(row['EMA50'])}"
            f" | EMA200="
            f"{fmt(row['EMA200'])}"
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
        "EOD VOLUME + RVOL + 5D "
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
        f"Current valid symbols: "
        f"{len(current)}"
    )

    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

    historical = (
        collect_historical_days(
            eod_date,
            HISTORY_DAYS
        )
    )

    # Keep the current session out of rolling-volume baselines, but include it
    # for indicators and price-structure calculations that describe today's EOD.
    current_history = current.copy()
    current_history["Date"] = pd.Timestamp(eod_date)
    analysis_history = historical + [current_history]

    # --------------------------------------------------------
    # STEP 4
    # --------------------------------------------------------

    avg_volume = (
        calculate_average_volume(
            historical
        )
    )

    # --------------------------------------------------------
    # STEP 5
    # --------------------------------------------------------

    result = calculate_rvol(
        current,
        avg_volume
    )

    # --------------------------------------------------------
    # STEP 6
    # --------------------------------------------------------

    result = calculate_5d_volume(
        result,
        historical
    )

    # --------------------------------------------------------
    # STEP 7
    # --------------------------------------------------------

    result = (
        calculate_price_volume_relationship(
            result
        )
    )

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

    # --------------------------------------------------------
    # STEPS 13–41: EOD scoring, next-day validation, positions
    # --------------------------------------------------------

    result = run_eod_layers(
        result,
        historical,
        current,
        nifty_history,
        eod_date,
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
        send_telegram(
            result,
            eod_date
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
