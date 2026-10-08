import os
import io
import zipfile
import requests
import pandas as pd
from datetime import datetime, timedelta

# ============================================================
# NSE V8 MODULE A
# EOD VOLUME + RVOL + 5D + PRICE/VOLUME + CLV
# + TREND + BREAKOUT / PULLBACK
# ============================================================

NSE_BASE_URL = "https://nsearchives.nseindia.com/content/cm/"
HISTORY_DAYS = 220

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

    url = (
        f"{NSE_BASE_URL}"
        f"BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
    )

    print("\n" + "-" * 60)
    print(f"Downloading NSE Bhavcopy: {date_obj.strftime('%Y-%m-%d')}")
    print(f"URL: {url}")

    try:
        response = session.get(url, timeout=30)

        print(f"HTTP status: {response.status_code}")
        print(f"Response size: {len(response.content)} bytes")

        if response.status_code != 200:
            return None

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            csv_files = [
                name for name in z.namelist()
                if name.lower().endswith(".csv")
            ]

            if not csv_files:
                print("CSV file not found inside ZIP.")
                return None

            csv_name = csv_files[0]
            print(f"Extracting CSV: {csv_name}")

            with z.open(csv_name) as f:
                df = pd.read_csv(f)

        print(f"Rows downloaded: {len(df)}")
        print(f"Columns: {list(df.columns)}")

        return df

    except Exception as e:
        print(f"Download error: {e}")
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
            raise ValueError(f"Required column missing: {col}")

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
        data[col] = pd.to_numeric(data[col], errors="coerce")

    data = data[
        data["TckrSymb"].notna()
        & data["ClsPric"].notna()
        & data["TtlTradgVol"].notna()
    ].copy()

    data = data[
        (data["ClsPric"] > 0)
        & (data["TtlTradgVol"] >= 0)
    ].copy()

    # Prefer normal equity series where available.
    if "SctySrs" in data.columns:
        equity = data[
            data["SctySrs"].astype(str).isin(
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
        (data["ClsPric"] - data["PrvsClsgPric"])
        / data["PrvsClsgPric"]
    ) * 100

    return data


# ============================================================
# FIND LATEST EOD
# ============================================================

def get_latest_eod():
    print("\nSTEP 1: Searching for latest NSE EOD Bhavcopy...")

    today = datetime.now().date()

    for i in range(10):
        check_date = today - timedelta(days=i)

        print(f"Trying date: {check_date}")

        df = download_bhavcopy(
            datetime.combine(check_date, datetime.min.time())
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

def collect_historical_days(latest_date, days=HISTORY_DAYS):
    print("\nSTEP 3: Collecting historical 220 trading days...")

    print("\n" + "=" * 60)
    print(f"COLLECTING PREVIOUS {days} TRADING DAYS")
    print("=" * 60)

    historical = []

    current_date = latest_date - timedelta(days=1)

    while len(historical) < days:
        print(
            f"\nChecking {current_date} | "
            f"Found {len(historical)}/{days}"
        )

        df = download_bhavcopy(
            datetime.combine(current_date, datetime.min.time())
        )

        if df is not None and len(df) > 0:
            try:
                clean = prepare_equity_data(df)

                if len(clean) > 0:
                    clean["Date"] = pd.Timestamp(current_date)
                    historical.append(clean)

                    print(
                        f"Accepted trading day: "
                        f"{current_date}"
                    )

            except Exception as e:
                print(f"Historical data error: {e}")

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
# 20D AVERAGE VOLUME
# ============================================================

def calculate_average_volume(historical):
    print("\nSTEP 4: Calculating 20D Average Volume...")

    frames = []

    for df in historical:
        temp = df[["TckrSymb", "TtlTradgVol"]].copy()
        frames.append(temp)

    if not frames:
        return pd.DataFrame()

    all_volume = pd.concat(
        frames,
        ignore_index=True
    )

    avg_volume = (
        all_volume
        .groupby("TckrSymb")["TtlTradgVol"]
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

def calculate_rvol(current, avg_volume):
    print("\nSTEP 5: Calculating RVOL...")

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
# 5 DAY VOLUME ANALYSIS
# ============================================================

def calculate_5d_volume(result, historical):
    print("\nSTEP 6: 5D Volume Analysis...")

    recent = historical[-5:]

    volume_map = {}

    for df in recent:
        for _, row in df.iterrows():
            symbol = row["TckrSymb"]

            volume_map.setdefault(
                symbol, []
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
        vols = volume_map.get(symbol, [])
        avg = avg_map.get(symbol)

        if avg is None or pd.isna(avg) or avg <= 0:
            low_days.append(0)
            patterns.append("Insufficient")
            continue

        lows = sum(
            1 for v in vols
            if v < avg
        )

        low_days.append(lows)

        if len(vols) < 5:
            patterns.append("Insufficient")

        else:
            first_two = sum(vols[:2]) / 2
            last_two = sum(vols[-2:]) / 2
            current = vols[-1]

            if (
                first_two > 0
                and last_two < first_two * 0.80
                and current > avg * 1.20
            ):
                patterns.append(
                    "Contraction -> Expansion"
                )

            elif last_two < first_two * 0.80:
                patterns.append("Contraction")

            elif last_two > first_two * 1.20:
                patterns.append("Expansion")

            else:
                patterns.append("Mixed")

    result["LowVolumeDays5D"] = low_days
    result["LowVolumePct5D"] = (
        result["LowVolumeDays5D"] / 5
    ) * 100

    result["VolumePattern5D"] = patterns

    result["LowVolume60Pass"] = (
        result["LowVolumeDays5D"] >= 3
    )

    return result


# ============================================================
# PRICE + VOLUME RELATIONSHIP
# ============================================================

def calculate_price_volume_relationship(result):
    print("\nSTEP 7: Price + Volume Relationship...")

    labels = []

    for _, row in result.iterrows():

        price = row["PriceChangePct"]
        rvol = row["RVOL"]

        if price > 0.10 and rvol >= 1.5:
            label = "Strong Bullish"

        elif price > 0.10 and rvol < 1.5:
            label = "Weak Bullish"

        elif price < -0.10 and rvol >= 1.5:
            label = "Selling / Distribution"

        elif price < -0.10 and rvol < 1.5:
            label = "Normal Pullback"

        else:
            label = "Possible Accumulation/Event"

        labels.append(label)

    result["PriceVolumeRelationship"] = labels

    return result


# ============================================================
# CLV / CANDLE QUALITY
# ============================================================

def calculate_clv(result):
    print("\nSTEP 8: Calculating CLV / Candle Quality...")

    candle_range = (
        result["HghPric"]
        - result["LwPric"]
    )

    result["CLV"] = (
        (result["ClsPric"] - result["LwPric"])
        / candle_range
    )

    result.loc[
        candle_range <= 0,
        "CLV"
    ] = 0.5

    result["CLV"] = (
        result["CLV"]
        .clip(lower=0, upper=1)
    )

    def clv_label(value):
        if value > 0.75:
            return "Strong"
        elif value >= 0.50:
            return "Good"
        elif value >= 0.25:
            return "Weak"
        return "Very Weak"

    result["CLVQuality"] = result["CLV"].apply(
        clv_label
    )

    print("CLV calculated successfully.")

    return result


# ============================================================
# RSI
# ============================================================

def calculate_rsi(series, period=14):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

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

    rsi = 100 - (
        100 / (1 + rs)
    )

    return rsi


# ============================================================
# ADX
# ============================================================

def calculate_adx(df, period=14):
    high = df["HghPric"]
    low = df["LwPric"]
    close = df["ClsPric"]

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    up_move = high - prev_high
    down_move = prev_low - low

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

    plus_dm.loc[plus_condition] = (
        up_move.loc[plus_condition]
    )

    minus_dm.loc[minus_condition] = (
        down_move.loc[minus_condition]
    )

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
        100 * plus_dm_avg / atr
    )

    minus_di = (
        100 * minus_dm_avg / atr
    )

    denominator = plus_di + minus_di

    dx = (
        100
        * (plus_di - minus_di).abs()
        / denominator
    )

    adx = dx.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    return adx


# ============================================================
# TREND INDICATORS
# ============================================================

def calculate_trend(result, historical):
    print("\nSTEP 9: Calculating Trend indicators...")
    print("EMA20 / EMA50 / EMA200 + RSI14 + ADX14")

    trend_rows = []

    all_frames = historical.copy()

    for symbol in result["TckrSymb"]:

        frames = []

        for df in all_frames:
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

        hist = hist.sort_values("Date")

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

        current_close = float(last["ClsPric"])
        ema20 = float(last["EMA20"])
        ema50 = float(last["EMA50"])
        ema200 = float(last["EMA200"])
        rsi = float(last["RSI14"])
        adx = float(last["ADX14"])

        if (
            current_close > ema20
            and ema20 > ema50
            and ema50 > ema200
            and rsi >= 50
            and adx >= 20
        ):
            trend = "Strong Bullish Trend"

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
            trend = "Strong Bearish Trend"

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

    trend_df = pd.DataFrame(trend_rows)

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
# ATR
# Used for breakout / pullback quality and future risk layers
# ============================================================

def calculate_atr(df, period=14):
    high = df["HghPric"]
    low = df["LwPric"]
    close = df["ClsPric"]

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

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
# BREAKOUT / PULLBACK
# ============================================================

def calculate_breakout_pullback(
    result,
    historical
):
    print(
        "\nSTEP 10: Breakout / Pullback Detection..."
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
                "RecentSwingHigh": float("nan"),
                "RecentSwingLow": float("nan"),
                "High20D": float("nan"),
                "High50D": float("nan"),
                "ATR14": float("nan"),
                "BreakoutStatus": "Insufficient Data",
                "PullbackStatus": "Insufficient Data",
                "SetupType": "Insufficient Data",
            })
            continue

        hist = pd.concat(
            frames,
            ignore_index=True
        )

        hist = hist.sort_values("Date")

        if len(hist) < 20:
            rows.append({
                "TckrSymb": symbol,
                "RecentSwingHigh": float("nan"),
                "RecentSwingLow": float("nan"),
                "High20D": float("nan"),
                "High50D": float("nan"),
                "ATR14": float("nan"),
                "BreakoutStatus": "Insufficient Data",
                "PullbackStatus": "Insufficient Data",
                "SetupType": "Insufficient Data",
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

        current_open = float(
            hist["OpnPric"].iloc[-1]
        )

        current_volume = float(
            hist["TtlTradgVol"].iloc[-1]
        )

        # ----------------------------------------------------
        # IMPORTANT:
        # Resistance is based on PREVIOUS data.
        # Current day is excluded to avoid look-ahead.
        # ----------------------------------------------------

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

        recent_swing_high = float(
            previous["HghPric"]
            .tail(20)
            .max()
        )

        recent_swing_low = float(
            previous["LwPric"]
            .tail(20)
            .min()
        )

        atr = float(
            hist["ATR14"].iloc[-1]
        )

        # ----------------------------------------------------
        # Previous volume average
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Candle quality
        # ----------------------------------------------------

        candle_range = (
            current_high - current_low
        )

        if candle_range > 0:
            clv = (
                current_close - current_low
            ) / candle_range
        else:
            clv = 0.5

        # ----------------------------------------------------
        # BREAKOUT DETECTION
        # ----------------------------------------------------

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

        # Strong breakout classification
        if (
            current_close > high20
            and current_close > high50
            and current_rvol >= 2.0
            and clv >= 0.75
        ):
            breakout_status = "Strong Breakout"

        elif breakout:
            breakout_status = "Breakout"

        elif (
            current_close >= high20 * 0.98
            and current_rvol >= 1.2
        ):
            breakout_status = "Near Breakout"

        else:
            breakout_status = "No Breakout"

        # ----------------------------------------------------
        # PULLBACK DETECTION
        # ----------------------------------------------------

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

        # Previous high before correction
        lookback_high = float(
            previous["HghPric"]
            .tail(20)
            .max()
        )

        correction_from_high = 0.0

        if lookback_high > 0:
            correction_from_high = (
                (lookback_high - current_close)
                / lookback_high
            ) * 100

        near_ema20 = False
        near_ema50 = False
        controlled_pullback = False

        if pd.notna(ema20_value):
            near_ema20 = (
                abs(current_close - ema20_value)
                / ema20_value
                <= 0.03
            )

        if pd.notna(ema50_value):
            near_ema50 = (
                abs(current_close - ema50_value)
                / ema50_value
                <= 0.04
            )

        if (
            1.0
            <= correction_from_high
            <= 15.0
        ):
            controlled_pullback = True

        pullback = (
            (
                "Bullish" in trend_text
                or "Improving" in trend_text
            )
            and controlled_pullback
            and (near_ema20 or near_ema50)
            and current_rvol <= 1.5
        )

        # Strong pullback:
        # bullish trend + controlled correction +
        # support/EMA + volume contraction
        low_volume_days = result.loc[
            result["TckrSymb"] == symbol,
            "LowVolumeDays5D"
        ]

        low_days = (
            int(low_volume_days.iloc[0])
            if len(low_volume_days) > 0
            and pd.notna(low_volume_days.iloc[0])
            else 0
        )

        if (
            pullback
            and low_days >= 3
        ):
            pullback_status = "Strong Pullback"

        elif pullback:
            pullback_status = "Pullback"

        elif (
            controlled_pullback
            and (near_ema20 or near_ema50)
        ):
            pullback_status = "Possible Pullback"

        else:
            pullback_status = "No Pullback"

        # ----------------------------------------------------
        # FINAL SETUP TYPE
        # ----------------------------------------------------

        if breakout_status == "Strong Breakout":
            setup_type = "Breakout"

        elif breakout_status == "Breakout":
            setup_type = "Breakout"

        elif pullback_status == "Strong Pullback":
            setup_type = "Pullback"

        elif pullback_status == "Pullback":
            setup_type = "Pullback"

        elif (
            breakout_status == "Near Breakout"
        ):
            setup_type = "Pre-Breakout"

        elif (
            pullback_status == "Possible Pullback"
        ):
            setup_type = "Possible Pullback"

        else:
            setup_type = "No Clear Setup"

        rows.append({
            "TckrSymb": symbol,
            "RecentSwingHigh": recent_swing_high,
            "RecentSwingLow": recent_swing_low,
            "High20D": high20,
            "High50D": high50,
            "ATR14": atr,
            "BreakoutStatus": breakout_status,
            "PullbackStatus": pullback_status,
            "SetupType": setup_type,
            "CorrectionFromHighPct":
                correction_from_high,
            "SetupRVOL": current_rvol,
        })

    setup_df = pd.DataFrame(rows)

    result = result.merge(
        setup_df,
        on="TckrSymb",
        how="left"
    )

    print(
        "Breakout / Pullback calculation completed."
    )

    return result


# ============================================================
# TOP 20 DISPLAY
# ============================================================

def display_top20(result):
    print("\n" + "=" * 100)
    print("TOP 20 V8 CANDIDATES")
    print("=" * 100)

    display = result.copy()

    display = display.sort_values(
        by="RVOL",
        ascending=False
    ).head(20)

    for i, (_, row) in enumerate(
        display.iterrows(),
        start=1
    ):

        def fmt(value, digits=2):
            if pd.isna(value):
                return "NA"
            return f"{value:.{digits}f}"

        print(
            f"\n{i}. {row['TckrSymb']:<15}"
            f" Price={fmt(row['PriceChangePct'])}%"
            f" | RVOL={fmt(row['RVOL'])}x"
            f" | Low5D={int(row['LowVolumeDays5D'])}/5"
            f" | P+V={row['PriceVolumeRelationship']:<30}"
            f" | CLV={fmt(row['CLV'])} "
            f"{row['CLVQuality']:<10}"
        )

        print(
            f"   EMA20={fmt(row['EMA20'])}"
            f" | EMA50={fmt(row['EMA50'])}"
            f" | EMA200={fmt(row['EMA200'])}"
            f" | RSI={fmt(row['RSI14'], 1)}"
            f" | ADX={fmt(row['ADX14'], 1)}"
            f" | Trend={row['TrendClassification']}"
        )

        print(
            f"   20DHigh={fmt(row['High20D'])}"
            f" | 50DHigh={fmt(row['High50D'])}"
            f" | SwingHigh={fmt(row['RecentSwingHigh'])}"
            f" | SwingLow={fmt(row['RecentSwingLow'])}"
        )

        print(
            f"   Breakout={row['BreakoutStatus']}"
            f" | Pullback={row['PullbackStatus']}"
            f" | Setup={row['SetupType']}"
        )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(result, eod_date):

    if not TELEGRAM_BOT_TOKEN:
        print("Telegram bot token not configured.")
        return

    if not TELEGRAM_CHAT_ID:
        print("Telegram chat ID not configured.")
        return

    top = (
        result
        .sort_values(
            by="RVOL",
            ascending=False
        )
        .head(10)
    )

    lines = []

    lines.append(
        "NSE V8 MODULE A - EOD UPDATE"
    )

    lines.append(
        f"Date: {eod_date}"
    )

    lines.append(
        "Layers: Volume + RVOL + 5D + P/V "
        "+ CLV + Trend + Breakout/Pullback"
    )

    lines.append("")

    for _, row in top.iterrows():

        def fmt(value, digits=2):
            if pd.isna(value):
                return "NA"
            return f"{value:.{digits}f}"

        lines.append(
            f"{row['TckrSymb']} | "
            f"RVOL {fmt(row['RVOL'])}x | "
            f"Trend {row['TrendClassification']}"
        )

        lines.append(
            f"Setup: {row['SetupType']} | "
            f"RSI {fmt(row['RSI14'], 1)} | "
            f"ADX {fmt(row['ADX14'], 1)}"
        )

        lines.append(
            f"CLV {fmt(row['CLV'])} | "
            f"P/V {row['PriceVolumeRelationship']}"
        )

        lines.append("")

    message = "\n".join(lines)

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
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
        print(f"Telegram error: {e}")


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n" + "=" * 70)
    print("NSE V8 MODULE A")
    print(
        "EOD VOLUME + RVOL + 5D + PRICE/VOLUME "
        "+ CLV + TREND + BREAKOUT/PULLBACK"
    )
    print("=" * 70)

    print("\nPython script started successfully.")

    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    eod_date, raw_current = get_latest_eod()

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    print("\nSTEP 2: Preparing current EOD data...")

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

    historical = collect_historical_days(
        eod_date,
        HISTORY_DAYS
    )

    # --------------------------------------------------------
    # STEP 4
    # --------------------------------------------------------

    avg_volume = calculate_average_volume(
        historical
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

    result = calculate_price_volume_relationship(
        result
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
        historical
    )

    # --------------------------------------------------------
    # STEP 10
    # --------------------------------------------------------

    result = calculate_breakout_pullback(
        result,
        historical
    )

    # --------------------------------------------------------
    # FINAL DISPLAY
    # --------------------------------------------------------

    display_top20(result)

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    send_telegram(
        result,
        eod_date
    )

    # --------------------------------------------------------
    # COMPLETION
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("MODULE A CURRENT STAGE COMPLETED")
    print("=" * 70)

    print(f"\nEOD Date: {eod_date}")
    print(f"\nFinal symbols: {len(result)}")

    print("\nLayers completed:")
    print("1. NSE Bhavcopy")
    print("2. 20D Average Volume")
    print("3. RVOL")
    print("4. 5D Volume Analysis")
    print("5. 60% Low-Volume Rule")
    print("6. Price + Volume Relationship")
    print("7. CLV / Candle Quality")
    print("8. Trend - EMA20/50/200")
    print("9. RSI14")
    print("10. ADX14")
    print("11. Breakout / Pullback Detection")

    print("\nPython exit code: 0")


if __name__ == "__main__":
    main()
