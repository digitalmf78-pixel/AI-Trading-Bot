import os
import io
import zipfile
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# ============================================================
# NSE V8 MODULE A
# EOD VOLUME + RVOL + 5D + PRICE/VOLUME + CLV
# + TREND EMA20/50/200 + RSI14 + ADX14
# ============================================================

NSE_BASE_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# EMA200 needs sufficient history.
# We collect more than 200 trading sessions.
TREND_HISTORY_DAYS = 220

# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram secrets not configured.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
    }

    try:
        response = requests.post(
            url,
            data=payload,
            timeout=20
        )

        print(f"Telegram HTTP status: {response.status_code}")

        if response.status_code != 200:
            print(
                "Telegram response:",
                response.text[:500]
            )

    except Exception as exc:
        print("Telegram error:", exc)


# ============================================================
# DOWNLOAD NSE BHAVCOPY
# ============================================================

def download_bhavcopy(date_obj):

    date_str = date_obj.strftime("%Y%m%d")

    url = NSE_BASE_URL.format(date=date_str)

    print("\n" + "-" * 60)
    print(
        f"Downloading NSE Bhavcopy: "
        f"{date_obj.strftime('%Y-%m-%d')}"
    )
    print(f"URL: {url}")

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        print(
            f"HTTP status: {response.status_code}"
        )

        print(
            f"Response size: "
            f"{len(response.content)} bytes"
        )

        if response.status_code != 200:
            return None

        with zipfile.ZipFile(
            io.BytesIO(response.content)
        ) as z:

            names = z.namelist()

            if not names:
                print("ZIP is empty.")
                return None

            csv_name = names[0]

            print(
                f"Extracting CSV: {csv_name}"
            )

            with z.open(csv_name) as csv_file:
                df = pd.read_csv(csv_file)

        print(
            f"Rows downloaded: {len(df)}"
        )

        print(
            f"Columns: {list(df.columns)}"
        )

        return df

    except Exception as exc:

        print(
            f"Download/read error: {exc}"
        )

        return None


# ============================================================
# FIND LATEST AVAILABLE EOD BHAVCOPY
# ============================================================

def get_latest_bhavcopy():

    print(
        "\nSTEP 1: Searching for latest "
        "NSE EOD Bhavcopy..."
    )

    today = datetime.now().date()

    for offset in range(0, 8):

        check_date = (
            today - timedelta(days=offset)
        )

        print(
            f"\nTrying date: "
            f"{check_date.strftime('%Y-%m-%d')}"
        )

        df = download_bhavcopy(
            datetime.combine(
                check_date,
                datetime.min.time()
            )
        )

        if df is not None and len(df) > 0:

            print(
                f"\nLatest available EOD date: "
                f"{check_date.strftime('%Y-%m-%d')}"
            )

            return df, check_date

    raise RuntimeError(
        "Could not find NSE Bhavcopy "
        "in the last 7 days."
    )


# ============================================================
# PREPARE CURRENT DATA
# ============================================================

def prepare_current_data(df):

    required_columns = [
        "TckrSymb",
        "OpnPric",
        "HghPric",
        "LwPric",
        "ClsPric",
        "PrvsClsgPric",
        "TtlTradgVol",
    ]

    missing = [
        col
        for col in required_columns
        if col not in df.columns
    ]

    if missing:

        raise RuntimeError(
            f"Missing required columns: {missing}"
        )

    data = df[
        required_columns
    ].copy()

    numeric_columns = [
        "OpnPric",
        "HghPric",
        "LwPric",
        "ClsPric",
        "PrvsClsgPric",
        "TtlTradgVol",
    ]

    for col in numeric_columns:

        data[col] = pd.to_numeric(
            data[col],
            errors="coerce"
        )

    data = data.dropna(
        subset=[
            "TckrSymb",
            "ClsPric",
            "PrvsClsgPric",
            "TtlTradgVol",
        ]
    )

    data = data[
        data["TtlTradgVol"] >= 0
    ]

    data = data.drop_duplicates(
        subset=["TckrSymb"],
        keep="last"
    )

    print(
        f"Current valid symbols: {len(data)}"
    )

    return data


# ============================================================
# COLLECT HISTORICAL DAYS
# ============================================================

def collect_historical_days(
    latest_date,
    days_needed=220
):

    print(
        "\nSTEP 3: Collecting historical "
        f"{days_needed} trading days..."
    )

    print("\n" + "=" * 60)
    print(
        f"COLLECTING PREVIOUS "
        f"{days_needed} TRADING DAYS"
    )
    print("=" * 60)

    historical = []

    check_date = (
        latest_date - timedelta(days=1)
    )

    # 220 trading days generally need
    # around 310 calendar days.
    # Give additional buffer for holidays.
    max_days = 360

    checked = 0

    while (
        len(historical) < days_needed
        and checked < max_days
    ):

        print(
            f"\nChecking "
            f"{check_date.strftime('%Y-%m-%d')} | "
            f"Found {len(historical)}/"
            f"{days_needed}"
        )

        df = download_bhavcopy(
            datetime.combine(
                check_date,
                datetime.min.time()
            )
        )

        if df is not None and len(df) > 0:

            required = [
                "TckrSymb",
                "OpnPric",
                "HghPric",
                "LwPric",
                "ClsPric",
                "TtlTradgVol",
            ]

            if all(
                col in df.columns
                for col in required
            ):

                hist = df[
                    required
                ].copy()

                numeric_columns = [
                    "OpnPric",
                    "HghPric",
                    "LwPric",
                    "ClsPric",
                    "TtlTradgVol",
                ]

                for col in numeric_columns:

                    hist[col] = pd.to_numeric(
                        hist[col],
                        errors="coerce"
                    )

                hist = hist.dropna(
                    subset=[
                        "TckrSymb",
                        "ClsPric",
                        "TtlTradgVol",
                    ]
                )

                hist = hist.drop_duplicates(
                    subset=["TckrSymb"],
                    keep="last"
                )

                hist["Date"] = check_date

                historical.append(hist)

                print(
                    f"Accepted trading day: "
                    f"{check_date.strftime('%Y-%m-%d')}"
                )

        check_date -= timedelta(days=1)

        checked += 1

    print(
        f"\nHistorical trading days collected: "
        f"{len(historical)}"
    )

    if len(historical) < days_needed:

        raise RuntimeError(
            "Could not collect enough historical "
            "trading days for EMA200."
        )

    return historical[:days_needed]


# ============================================================
# 20D AVERAGE VOLUME
# ============================================================

def calculate_20d_average(
    historical
):

    print(
        "\nSTEP 4: Calculating "
        "20D average volume..."
    )

    print("\n" + "=" * 60)
    print(
        "CALCULATING 20D AVERAGE VOLUME"
    )
    print("=" * 60)

    # Historical list is newest first.
    # Use first 20 sessions.
    volume_history = historical[:20]

    all_history = pd.concat(
        volume_history,
        ignore_index=True
    )

    avg_volume = (
        all_history
        .groupby("TckrSymb")["TtlTradgVol"]
        .mean()
        .rename("Avg20DVolume")
    )

    print(
        f"Symbols with 20D average: "
        f"{len(avg_volume)}"
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

    print("\n" + "=" * 60)
    print("CALCULATING RVOL")
    print("=" * 60)

    data = current.merge(
        avg_volume,
        left_on="TckrSymb",
        right_index=True,
        how="inner"
    )

    data = data[
        data["Avg20DVolume"] > 0
    ].copy()

    data["RVOL"] = (
        data["TtlTradgVol"]
        / data["Avg20DVolume"]
    )

    print(
        f"RVOL calculated for: "
        f"{len(data)} symbols"
    )

    return data


# ============================================================
# 5-DAY VOLUME ANALYSIS
# ============================================================

def calculate_5d_volume(
    data,
    historical
):

    print(
        "\nSTEP 6: Calculating "
        "5-day volume analysis..."
    )

    print("\n" + "=" * 60)
    print("5-DAY VOLUME ANALYSIS")
    print("=" * 60)

    recent_days = historical[:5]

    volume_maps = []

    for day in recent_days:

        day_map = day.set_index(
            "TckrSymb"
        )["TtlTradgVol"]

        volume_maps.append(
            day_map
        )

    low_counts = []
    low_percentages = []
    patterns = []

    for symbol in data["TckrSymb"]:

        volumes = []

        for day_map in volume_maps:

            value = day_map.get(symbol)

            if value is not None:
                volumes.append(
                    float(value)
                )

        avg20 = data.loc[
            data["TckrSymb"] == symbol,
            "Avg20DVolume"
        ].iloc[0]

        if len(volumes) == 0:

            low_count = 0
            low_pct = 0
            pattern = "Insufficient data"

        else:

            low_count = sum(
                v < avg20
                for v in volumes
            )

            low_pct = (
                low_count
                / len(volumes)
            ) * 100

            if len(volumes) >= 4:

                first_part = (
                    sum(volumes[:2])
                    / 2
                )

                last_part = (
                    sum(volumes[-2:])
                    / 2
                )

                if first_part > 0:

                    if (
                        last_part
                        < first_part * 0.80
                    ):

                        pattern = "Contraction"

                    elif (
                        last_part
                        > first_part * 1.20
                    ):

                        pattern = "Expansion"

                    else:

                        pattern = "Mixed"

                else:

                    pattern = "Insufficient data"

            else:

                pattern = "Insufficient data"

        low_counts.append(
            low_count
        )

        low_percentages.append(
            low_pct
        )

        patterns.append(
            pattern
        )

    data["LowVolumeDays5D"] = (
        low_counts
    )

    data["LowVolumePct5D"] = (
        low_percentages
    )

    data["5DVolumePattern"] = (
        patterns
    )

    data["60Rule"] = data[
        "LowVolumeDays5D"
    ].apply(
        lambda x:
            "PASS"
            if x >= 3
            else "NO"
    )

    return data


# ============================================================
# PRICE + VOLUME RELATIONSHIP
# ============================================================

def calculate_price_volume_relationship(
    data
):

    print(
        "\nSTEP 7: Calculating "
        "Price + Volume Relationship..."
    )

    print("\n" + "=" * 60)
    print(
        "PRICE + VOLUME RELATIONSHIP"
    )
    print("=" * 60)

    data["PriceChangePct"] = (
        (
            data["ClsPric"]
            - data["PrvsClsgPric"]
        )
        / data["PrvsClsgPric"]
    ) * 100

    def price_direction(value):

        if value > 0.10:
            return "Up"

        if value < -0.10:
            return "Down"

        return "Flat"

    data["PriceDirection"] = (
        data["PriceChangePct"]
        .apply(price_direction)
    )

    data["VolumeDirection"] = data.apply(
        lambda row:
            "Up"
            if (
                row["TtlTradgVol"]
                > row["Avg20DVolume"]
            )
            else "Down",
        axis=1
    )

    def relationship(row):

        price = row[
            "PriceDirection"
        ]

        volume = row[
            "VolumeDirection"
        ]

        if (
            price == "Up"
            and volume == "Up"
        ):

            return "Strong Bullish"

        if (
            price == "Up"
            and volume == "Down"
        ):

            return "Weak / Caution"

        if (
            price == "Down"
            and volume == "Up"
        ):

            return "Selling / Distribution"

        if (
            price == "Down"
            and volume == "Down"
        ):

            return "Normal Pullback"

        if (
            price == "Flat"
            and volume == "Up"
        ):

            return (
                "Possible Accumulation / Event"
            )

        return "Low Activity / Neutral"

    data[
        "PriceVolumeRelationship"
    ] = data.apply(
        relationship,
        axis=1
    )

    return data


# ============================================================
# CLV / CANDLE QUALITY
# ============================================================

def calculate_clv(data):

    print(
        "\nSTEP 8: Calculating "
        "CLV / Candle Quality..."
    )

    print("\n" + "=" * 60)
    print("CLV / CANDLE QUALITY")
    print("=" * 60)

    candle_range = (
        data["HghPric"]
        - data["LwPric"]
    )

    data["CLV"] = 0.0

    valid_range = (
        candle_range > 0
    )

    data.loc[
        valid_range,
        "CLV"
    ] = (
        (
            data.loc[
                valid_range,
                "ClsPric"
            ]
            - data.loc[
                valid_range,
                "LwPric"
            ]
        )
        / candle_range[
            valid_range
        ]
    )

    def classify_clv(value):

        if value > 0.75:
            return "Strong"

        if value >= 0.50:
            return "Good"

        if value >= 0.25:
            return "Weak"

        return "Very Weak"

    data["CandleQuality"] = (
        data["CLV"]
        .apply(classify_clv)
    )

    print(
        "CLV calculated successfully."
    )

    return data


# ============================================================
# RSI 14
# ============================================================

def calculate_rsi(
    close_series,
    period=14
):

    delta = close_series.diff()

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

    rs = (
        avg_gain
        / avg_loss.replace(
            0,
            np.nan
        )
    )

    rsi = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    return rsi


# ============================================================
# ADX 14
# ============================================================

def calculate_adx(
    high,
    low,
    close,
    period=14
):

    previous_close = (
        close.shift(1)
    )

    up_move = (
        high
        - high.shift(1)
    )

    down_move = (
        low.shift(1)
        - low
    )

    plus_dm = pd.Series(
        np.where(
            (
                up_move > down_move
            )
            & (
                up_move > 0
            ),
            up_move,
            0.0
        ),
        index=high.index
    )

    minus_dm = pd.Series(
        np.where(
            (
                down_move > up_move
            )
            & (
                down_move > 0
            ),
            down_move,
            0.0
        ),
        index=high.index
    )

    tr1 = (
        high - low
    )

    tr2 = (
        high - previous_close
    ).abs()

    tr3 = (
        low - previous_close
    ).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    plus_dm_smoothed = (
        plus_dm.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period
        ).mean()
    )

    minus_dm_smoothed = (
        minus_dm.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period
        ).mean()
    )

    plus_di = (
        100
        * plus_dm_smoothed
        / atr.replace(
            0,
            np.nan
        )
    )

    minus_di = (
        100
        * minus_dm_smoothed
        / atr.replace(
            0,
            np.nan
        )
    )

    di_sum = (
        plus_di
        + minus_di
    )

    dx = (
        100
        * (
            plus_di
            - minus_di
        ).abs()
        / di_sum.replace(
            0,
            np.nan
        )
    )

    adx = dx.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    return adx


# ============================================================
# TREND ANALYSIS
# ============================================================

def calculate_trend(
    data,
    historical
):

    print(
        "\nSTEP 9: Calculating "
        "Trend EMA20/50/200 + RSI14 + ADX14..."
    )

    print("\n" + "=" * 60)
    print(
        "TREND ANALYSIS"
    )
    print("=" * 60)

    # Historical data is newest first.
    # Reverse it so indicators calculate
    # chronologically from oldest -> newest.
    all_history = pd.concat(
        historical,
        ignore_index=True
    )

    all_history = all_history.sort_values(
        ["TckrSymb", "Date"]
    )

    result_rows = []

    for symbol, group in all_history.groupby(
        "TckrSymb"
    ):

        group = group.copy()

        group["ClsPric"] = pd.to_numeric(
            group["ClsPric"],
            errors="coerce"
        )

        group["HghPric"] = pd.to_numeric(
            group["HghPric"],
            errors="coerce"
        )

        group["LwPric"] = pd.to_numeric(
            group["LwPric"],
            errors="coerce"
        )

        group = group.dropna(
            subset=[
                "ClsPric",
                "HghPric",
                "LwPric"
            ]
        )

        if len(group) < 200:
            continue

        close = group[
            "ClsPric"
        ]

        high = group[
            "HghPric"
        ]

        low = group[
            "LwPric"
        ]

        ema20 = close.ewm(
            span=20,
            adjust=False
        ).mean()

        ema50 = close.ewm(
            span=50,
            adjust=False
        ).mean()

        ema200 = close.ewm(
            span=200,
            adjust=False
        ).mean()

        rsi14 = calculate_rsi(
            close,
            period=14
        )

        adx14 = calculate_adx(
            high,
            low,
            close,
            period=14
        )

        latest = group.index[-1]

        result_rows.append(
            {
                "TckrSymb": symbol,
                "EMA20": float(
                    ema20.loc[latest]
                ),
                "EMA50": float(
                    ema50.loc[latest]
                ),
                "EMA200": float(
                    ema200.loc[latest]
                ),
                "RSI14": float(
                    rsi14.loc[latest]
                )
                if pd.notna(
                    rsi14.loc[latest]
                )
                else np.nan,
                "ADX14": float(
                    adx14.loc[latest]
                )
                if pd.notna(
                    adx14.loc[latest]
                )
                else np.nan,
            }
        )

    trend_df = pd.DataFrame(
        result_rows
    )

    if trend_df.empty:

        raise RuntimeError(
            "Trend indicators could not "
            "be calculated."
        )

    data = data.merge(
        trend_df,
        on="TckrSymb",
        how="left"
    )

    def classify_trend(row):

        close = row[
            "ClsPric"
        ]

        ema20 = row[
            "EMA20"
        ]

        ema50 = row[
            "EMA50"
        ]

        ema200 = row[
            "EMA200"
        ]

        rsi = row[
            "RSI14"
        ]

        adx = row[
            "ADX14"
        ]

        if any(
            pd.isna(x)
            for x in [
                close,
                ema20,
                ema50,
                ema200,
                rsi,
                adx
            ]
        ):

            return "Insufficient Data"

        if (
            close > ema20
            and ema20 > ema50
            and ema50 > ema200
        ):

            if (
                rsi >= 50
                and adx >= 20
            ):

                return "Strong Bullish Trend"

            return "Bullish Trend"

        if (
            close < ema20
            and ema20 < ema50
            and ema50 < ema200
        ):

            if (
                rsi < 50
                and adx >= 20
            ):

                return "Strong Bearish Trend"

            return "Bearish Trend"

        if (
            close > ema50
            and ema20 > ema50
        ):

            return "Mixed / Improving"

        if (
            close < ema50
            and ema20 < ema50
        ):

            return "Mixed / Weak"

        return "Sideways / Mixed"

    data["TrendClassification"] = data.apply(
        classify_trend,
        axis=1
    )

    print(
        f"Trend indicators calculated for: "
        f"{data['EMA200'].notna().sum()} symbols"
    )

    return data


# ============================================================
# TOP RESULTS
# ============================================================

def print_top_results(
    data
):

    print(
        "\n" + "=" * 110
    )

    print(
        "TOP 20 RVOL + 5D + P/V + CLV + TREND"
    )

    print(
        "=" * 110
    )

    top = data.sort_values(
        "RVOL",
        ascending=False
    ).head(20)

    for index, (_, row) in enumerate(
        top.iterrows(),
        start=1
    ):

        ema20 = row["EMA20"]
        ema50 = row["EMA50"]
        ema200 = row["EMA200"]
        rsi = row["RSI14"]
        adx = row["ADX14"]

        ema20_text = (
            f"{ema20:.2f}"
            if pd.notna(ema20)
            else "NA"
        )

        ema50_text = (
            f"{ema50:.2f}"
            if pd.notna(ema50)
            else "NA"
        )

        ema200_text = (
            f"{ema200:.2f}"
            if pd.notna(ema200)
            else "NA"
        )

        rsi_text = (
            f"{rsi:.1f}"
            if pd.notna(rsi)
            else "NA"
        )

        adx_text = (
            f"{adx:.1f}"
            if pd.notna(adx)
            else "NA"
        )

        print(
            f"{index:02d}. "
            f"{str(row['TckrSymb']):<16} "
            f"Price={row['PriceChangePct']:+.2f}% | "
            f"RVOL={row['RVOL']:.2f}x | "
            f"Low5D="
            f"{int(row['LowVolumeDays5D'])}/5 | "
            f"P+V="
            f"{row['PriceVolumeRelationship']:<30} | "
            f"CLV={row['CLV']:.2f} "
            f"{row['CandleQuality']:<10} | "
            f"EMA20={ema20_text} | "
            f"EMA50={ema50_text} | "
            f"EMA200={ema200_text} | "
            f"RSI={rsi_text} | "
            f"ADX={adx_text} | "
            f"Trend="
            f"{row['TrendClassification']}"
        )

    return top


# ============================================================
# TELEGRAM
# ============================================================

def send_results_to_telegram(
    data,
    latest_date
):

    top = data.sort_values(
        "RVOL",
        ascending=False
    ).head(20)

    message_lines = [
        "NSE V8 MODULE A",
        "",
        f"EOD Date: {latest_date}",
        "",
        "Volume + RVOL + 5D + P/V",
        "+ CLV + TREND",
        "",
        "TOP 20 RVOL:",
    ]

    for index, (_, row) in enumerate(
        top.iterrows(),
        start=1
    ):

        rsi = row["RSI14"]
        adx = row["ADX14"]

        rsi_text = (
            f"{rsi:.1f}"
            if pd.notna(rsi)
            else "NA"
        )

        adx_text = (
            f"{adx:.1f}"
            if pd.notna(adx)
            else "NA"
        )

        message_lines.append(
            f"{index}. "
            f"{row['TckrSymb']} | "
            f"{row['PriceChangePct']:+.2f}% | "
            f"RVOL {row['RVOL']:.2f}x | "
            f"CLV {row['CLV']:.2f} | "
            f"RSI {rsi_text} | "
            f"ADX {adx_text} | "
            f"{row['TrendClassification']}"
        )

    message_lines.extend(
        [
            "",
            "Screening/confirmation layers only.",
            "NOT a final BUY signal.",
        ]
    )

    send_telegram(
        "\n".join(message_lines)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n" + "=" * 70
    )

    print(
        "NSE V8 MODULE A"
    )

    print(
        "EOD VOLUME + RVOL + 5D + "
        "PRICE/VOLUME + CLV + TREND"
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

    current_raw, latest_date = (
        get_latest_bhavcopy()
    )

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    print(
        "\nSTEP 2: Preparing current EOD data..."
    )

    current = prepare_current_data(
        current_raw
    )

    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

    historical = collect_historical_days(
        latest_date,
        days_needed=TREND_HISTORY_DAYS
    )

    # --------------------------------------------------------
    # STEP 4
    # --------------------------------------------------------

    avg_volume = calculate_20d_average(
        historical
    )

    # --------------------------------------------------------
    # STEP 5
    # --------------------------------------------------------

    data = calculate_rvol(
        current,
        avg_volume
    )

    # --------------------------------------------------------
    # STEP 6
    # --------------------------------------------------------

    data = calculate_5d_volume(
        data,
        historical
    )

    # --------------------------------------------------------
    # STEP 7
    # --------------------------------------------------------

    data = calculate_price_volume_relationship(
        data
    )

    # --------------------------------------------------------
    # STEP 8
    # --------------------------------------------------------

    data = calculate_clv(
        data
    )

    # --------------------------------------------------------
    # STEP 9
    # --------------------------------------------------------

    data = calculate_trend(
        data,
        historical
    )

    # --------------------------------------------------------
    # TOP RESULTS
    # --------------------------------------------------------

    print_top_results(
        data
    )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    send_results_to_telegram(
        data,
        latest_date
    )

    # --------------------------------------------------------
    # COMPLETION
    # --------------------------------------------------------

    print(
        "\n" + "=" * 70
    )

    print(
        "MODULE A CURRENT STAGE COMPLETED"
    )

    print(
        "=" * 70
    )

    print(
        f"EOD Date: {latest_date}"
    )

    print(
        f"Final symbols: {len(data)}"
    )

    print(
        "\nLayers completed:"
    )

    print(
        "1. NSE Bhavcopy"
    )

    print(
        "2. 20D Average Volume"
    )

    print(
        "3. RVOL"
    )

    print(
        "4. 5D Volume Analysis"
    )

    print(
        "5. 60% Low-Volume Rule"
    )

    print(
        "6. Price + Volume Relationship"
    )

    print(
        "7. CLV / Candle Quality"
    )

    print(
        "8. Trend - EMA20/50/200"
    )

    print(
        "9. RSI14"
    )

    print(
        "10. ADX14"
    )

    print(
        "\nPython exit code: 0"
    )


if __name__ == "__main__":
    main()
