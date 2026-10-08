import os
import io
import zipfile
import requests
import pandas as pd
from datetime import datetime, timedelta


# ============================================================
# NSE V8 MODULE A
# EOD VOLUME + 20D AVG + RVOL + 5D + PRICE/VOLUME + CLV
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
            print("Telegram response:", response.text[:500])

    except Exception as exc:
        print("Telegram error:", exc)


# ============================================================
# DOWNLOAD NSE BHAVCOPY
# ============================================================

def download_bhavcopy(date_obj):
    date_str = date_obj.strftime("%Y%m%d")

    url = NSE_BASE_URL.format(date=date_str)

    print("\n" + "-" * 60)
    print(f"Downloading NSE Bhavcopy: {date_obj.strftime('%Y-%m-%d')}")
    print(f"URL: {url}")

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        print(f"HTTP status: {response.status_code}")
        print(f"Response size: {len(response.content)} bytes")

        if response.status_code != 200:
            return None

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            names = z.namelist()

            if not names:
                print("ZIP is empty.")
                return None

            csv_name = names[0]

            print(f"Extracting CSV: {csv_name}")

            with z.open(csv_name) as csv_file:
                df = pd.read_csv(csv_file)

        print(f"Rows downloaded: {len(df)}")
        print(f"Columns: {list(df.columns)}")

        return df

    except Exception as exc:
        print(f"Download/read error: {exc}")
        return None


# ============================================================
# FIND LATEST AVAILABLE EOD BHAVCOPY
# ============================================================

def get_latest_bhavcopy():
    print("\nSTEP 1: Searching for latest NSE EOD Bhavcopy...")

    today = datetime.now().date()

    for offset in range(0, 8):
        check_date = today - timedelta(days=offset)

        print(
            f"\nTrying date: "
            f"{check_date.strftime('%Y-%m-%d')}"
        )

        df = download_bhavcopy(
            datetime.combine(check_date, datetime.min.time())
        )

        if df is not None and len(df) > 0:
            print(
                f"\nLatest available EOD date: "
                f"{check_date.strftime('%Y-%m-%d')}"
            )

            return df, check_date

    raise RuntimeError(
        "Could not find NSE Bhavcopy in the last 7 days."
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
        col for col in required_columns
        if col not in df.columns
    ]

    if missing:
        raise RuntimeError(
            f"Missing required columns: {missing}"
        )

    data = df[required_columns].copy()

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
# COLLECT PREVIOUS 20 TRADING DAYS
# ============================================================

def collect_previous_days(latest_date, days_needed=20):
    print("\nSTEP 3: Collecting previous 20 trading days...")

    print("\n" + "=" * 60)
    print("COLLECTING PREVIOUS 20 TRADING DAYS")
    print("=" * 60)

    historical = []

    check_date = latest_date - timedelta(days=1)

    max_days = 70

    checked = 0

    while (
        len(historical) < days_needed
        and checked < max_days
    ):
        print(
            f"\nChecking "
            f"{check_date.strftime('%Y-%m-%d')} | "
            f"Found {len(historical)}/{days_needed}"
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
                "TtlTradgVol"
            ]

            if all(col in df.columns for col in required):

                hist = df[
                    ["TckrSymb", "TtlTradgVol"]
                ].copy()

                hist["TtlTradgVol"] = pd.to_numeric(
                    hist["TtlTradgVol"],
                    errors="coerce"
                )

                hist = hist.dropna(
                    subset=[
                        "TckrSymb",
                        "TtlTradgVol"
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
        f"\nPrevious trading days collected: "
        f"{len(historical)}"
    )

    if len(historical) < days_needed:
        raise RuntimeError(
            "Could not collect required 20 trading days."
        )

    return historical[:days_needed]


# ============================================================
# 20D AVERAGE VOLUME
# ============================================================

def calculate_20d_average(historical):
    print("\nSTEP 4: Calculating 20D average volume...")

    print("\n" + "=" * 60)
    print("CALCULATING 20D AVERAGE VOLUME")
    print("=" * 60)

    all_history = pd.concat(
        historical,
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

def calculate_rvol(current, avg_volume):
    print("\nSTEP 5: Calculating RVOL...")

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
        f"RVOL calculated for: {len(data)} symbols"
    )

    return data


# ============================================================
# 5-DAY VOLUME ANALYSIS
# ============================================================

def calculate_5d_volume(data, historical):
    print("\nSTEP 6: Calculating 5-day volume analysis...")

    print("\n" + "=" * 60)
    print("5-DAY VOLUME ANALYSIS")
    print("=" * 60)

    recent_days = historical[:5]

    volume_maps = []

    for day in recent_days:
        day_map = day.set_index(
            "TckrSymb"
        )["TtlTradgVol"]

        volume_maps.append(day_map)

    low_counts = []
    low_percentages = []
    patterns = []

    for symbol in data["TckrSymb"]:

        volumes = []

        for day_map in volume_maps:
            value = day_map.get(symbol)

            if value is not None:
                volumes.append(float(value))

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
                low_count / len(volumes)
            ) * 100

            if len(volumes) >= 4:

                first_part = sum(
                    volumes[:2]
                ) / 2

                last_part = sum(
                    volumes[-2:]
                ) / 2

                if first_part > 0:

                    if last_part < first_part * 0.80:
                        pattern = "Contraction"

                    elif last_part > first_part * 1.20:
                        pattern = "Expansion"

                    else:
                        pattern = "Mixed"

                else:
                    pattern = "Insufficient data"

            else:
                pattern = "Insufficient data"

        low_counts.append(low_count)
        low_percentages.append(low_pct)
        patterns.append(pattern)

    data["LowVolumeDays5D"] = low_counts
    data["LowVolumePct5D"] = low_percentages
    data["5DVolumePattern"] = patterns

    data["60Rule"] = data[
        "LowVolumeDays5D"
    ].apply(
        lambda x: "PASS" if x >= 3 else "NO"
    )

    return data


# ============================================================
# PRICE + VOLUME RELATIONSHIP
# ============================================================

def calculate_price_volume_relationship(data):
    print(
        "\nSTEP 7: Calculating "
        "Price + Volume Relationship..."
    )

    print("\n" + "=" * 60)
    print("PRICE + VOLUME RELATIONSHIP")
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
            if row["TtlTradgVol"]
            > row["Avg20DVolume"]
            else "Down",
        axis=1
    )

    def relationship(row):

        price = row["PriceDirection"]
        volume = row["VolumeDirection"]

        if price == "Up" and volume == "Up":
            return "Strong Bullish"

        if price == "Up" and volume == "Down":
            return "Weak / Caution"

        if price == "Down" and volume == "Up":
            return "Selling / Distribution"

        if price == "Down" and volume == "Down":
            return "Normal Pullback"

        if price == "Flat" and volume == "Up":
            return "Possible Accumulation / Event"

        return "Low Activity / Neutral"

    data["PriceVolumeRelationship"] = data.apply(
        relationship,
        axis=1
    )

    return data


# ============================================================
# CLV / CANDLE QUALITY
# ============================================================

def calculate_clv(data):
    print("\nSTEP 8: Calculating CLV / Candle Quality...")

    print("\n" + "=" * 60)
    print("CLV / CANDLE QUALITY")
    print("=" * 60)

    candle_range = (
        data["HghPric"]
        - data["LwPric"]
    )

    data["CLV"] = 0.0

    valid_range = candle_range > 0

    data.loc[valid_range, "CLV"] = (
        (
            data.loc[valid_range, "ClsPric"]
            - data.loc[valid_range, "LwPric"]
        )
        / candle_range[valid_range]
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

    print("CLV calculated successfully.")

    return data


# ============================================================
# TOP RESULTS
# ============================================================

def print_top_results(data):

    print("\n" + "=" * 80)
    print("TOP 20 RVOL + 5D + PRICE/VOLUME + CLV")
    print("=" * 80)

    top = data.sort_values(
        "RVOL",
        ascending=False
    ).head(20)

    for index, (_, row) in enumerate(
        top.iterrows(),
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{str(row['TckrSymb']):<16} "
            f"Price={row['PriceChangePct']:+.2f}% | "
            f"Vol={row['TtlTradgVol']:,.0f} | "
            f"20D={row['Avg20DVolume']:,.0f} | "
            f"RVOL={row['RVOL']:.2f}x | "
            f"Low5D="
            f"{int(row['LowVolumeDays5D'])}/5 "
            f"({row['LowVolumePct5D']:.0f}%) | "
            f"Pattern={row['5DVolumePattern']:<17} | "
            f"P+V={row['PriceVolumeRelationship']:<30} | "
            f"CLV={row['CLV']:.2f} | "
            f"Candle={row['CandleQuality']:<10} | "
            f"60%={row['60Rule']}"
        )

    return top


# ============================================================
# TELEGRAM SUMMARY
# ============================================================

def send_results_to_telegram(data, latest_date):

    top = data.sort_values(
        "RVOL",
        ascending=False
    ).head(20)

    message_lines = [
        "NSE V8 MODULE A",
        "",
        f"EOD Date: {latest_date}",
        "Volume + RVOL + 5D + P/V + CLV",
        "",
        "TOP 20 RVOL:",
    ]

    for index, (_, row) in enumerate(
        top.iterrows(),
        start=1
    ):

        message_lines.append(
            f"{index}. {row['TckrSymb']} | "
            f"{row['PriceChangePct']:+.2f}% | "
            f"RVOL {row['RVOL']:.2f}x | "
            f"5D {int(row['LowVolumeDays5D'])}/5 | "
            f"P+V {row['PriceVolumeRelationship']} | "
            f"CLV {row['CLV']:.2f} "
            f"({row['CandleQuality']})"
        )

    message_lines.extend(
        [
            "",
            "Note: Volume/RVOL/CLV are screening",
            "and confirmation layers, NOT final BUY signals.",
        ]
    )

    message = "\n".join(message_lines)

    send_telegram(message)


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n" + "=" * 60)
    print("NSE V8 MODULE A")
    print(
        "EOD VOLUME + 20D AVG + RVOL + "
        "5D + PRICE/VOLUME + CLV"
    )
    print("=" * 60)

    print("\nPython script started successfully.")

    # STEP 1
    current_raw, latest_date = get_latest_bhavcopy()

    # STEP 2
    print("\nSTEP 2: Preparing current EOD data...")

    current = prepare_current_data(
        current_raw
    )

    # STEP 3
    historical = collect_previous_days(
        latest_date,
        days_needed=20
    )

    # STEP 4
    avg_volume = calculate_20d_average(
        historical
    )

    # STEP 5
    data = calculate_rvol(
        current,
        avg_volume
    )

    # STEP 6
    data = calculate_5d_volume(
        data,
        historical
    )

    # STEP 7
    data = calculate_price_volume_relationship(
        data
    )

    # STEP 8
    data = calculate_clv(
        data
    )

    # TOP RESULTS
    top = print_top_results(data)

    # TELEGRAM
    send_results_to_telegram(
        data,
        latest_date
    )

    print("\n" + "=" * 60)
    print("MODULE A CURRENT STAGE COMPLETED")
    print("=" * 60)

    print(
        f"EOD Date: {latest_date}"
    )

    print(
        f"Final symbols: {len(data)}"
    )

    print(
        "Layers completed:"
    )

    print("1. NSE Bhavcopy")
    print("2. 20D Average Volume")
    print("3. RVOL")
    print("4. 5D Volume Analysis")
    print("5. 60% Low-Volume Rule")
    print("6. Price + Volume Relationship")
    print("7. CLV / Candle Quality")

    print(
        "\nPython exit code: 0"
    )


if __name__ == "__main__":
    main()
