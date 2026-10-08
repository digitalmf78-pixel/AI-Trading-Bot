import io
import os
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests


# ============================================================
# NSE V8 MODULE A
# EOD VOLUME GAINER + 20D AVG + RVOL + 5D VOLUME ANALYSIS
# ============================================================

BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    print("\nSending Telegram message...")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not configured.")
        return

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=30,
        )

        print("Telegram HTTP status:", response.status_code)
        print("Telegram response:", response.text[:500])

    except Exception as e:
        print("Telegram error:", repr(e))


# ============================================================
# DOWNLOAD BHAVCOPY
# ============================================================

def download_bhavcopy(date_obj):

    date_str = date_obj.strftime("%Y%m%d")

    url = BHAVCOPY_URL.format(date=date_str)

    print("\n----------------------------------------")
    print("Downloading NSE Bhavcopy:", date_str)

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=60,
        )

        print("HTTP status:", response.status_code)
        print("Response size:", len(response.content), "bytes")

        if response.status_code != 200:
            return None

        if len(response.content) < 1000:
            return None

        with zipfile.ZipFile(
            io.BytesIO(response.content)
        ) as z:

            csv_files = [
                x for x in z.namelist()
                if x.lower().endswith(".csv")
            ]

            if not csv_files:
                print("No CSV found.")
                return None

            csv_name = csv_files[0]

            print("Reading:", csv_name)

            with z.open(csv_name) as f:
                df = pd.read_csv(f)

        print("Rows:", len(df))

        return df

    except Exception as e:

        print("Bhavcopy error:", repr(e))

        return None


# ============================================================
# PREPARE DATA
# ============================================================

def prepare_volume_data(df):

    if df is None or df.empty:
        return None

    required = [
        "TckrSymb",
        "ClsPric",
        "TtlTradgVol",
    ]

    for column in required:

        if column not in df.columns:
            print("Missing column:", column)
            return None

    data = df[
        [
            "TckrSymb",
            "ClsPric",
            "TtlTradgVol",
        ]
    ].copy()

    data["TtlTradgVol"] = pd.to_numeric(
        data["TtlTradgVol"],
        errors="coerce",
    )

    data["ClsPric"] = pd.to_numeric(
        data["ClsPric"],
        errors="coerce",
    )

    data = data.dropna(
        subset=[
            "TckrSymb",
            "ClsPric",
            "TtlTradgVol",
        ]
    )

    data = data[
        (data["ClsPric"] > 0)
        &
        (data["TtlTradgVol"] > 0)
    ]

    return data


# ============================================================
# GET PREVIOUS 20 TRADING DAYS
# ============================================================

def get_previous_20_days(current_date):

    print("\n========================================")
    print("COLLECTING PREVIOUS 20 TRADING DAYS")
    print("========================================")

    previous_days = []

    check_date = current_date - timedelta(days=1)

    attempts = 0

    while len(previous_days) < 20 and attempts < 50:

        date_text = check_date.strftime("%Y-%m-%d")

        print(
            f"Checking {date_text} | "
            f"Found {len(previous_days)}/20"
        )

        df = download_bhavcopy(check_date)

        if df is not None:

            prepared = prepare_volume_data(df)

            if prepared is not None and not prepared.empty:

                prepared["Date"] = date_text

                previous_days.append(prepared)

                print("Accepted:", date_text)

        check_date -= timedelta(days=1)
        attempts += 1

    print(
        "Previous trading days collected:",
        len(previous_days)
    )

    return previous_days


# ============================================================
# 20D AVERAGE VOLUME
# ============================================================

def calculate_20d_average(previous_days):

    if not previous_days:
        return None

    combined = pd.concat(
        previous_days,
        ignore_index=True,
    )

    avg_volume = (
        combined
        .groupby("TckrSymb")["TtlTradgVol"]
        .mean()
        .reset_index()
    )

    avg_volume.rename(
        columns={
            "TtlTradgVol": "AVG_20D_VOLUME"
        },
        inplace=True,
    )

    print(
        "20D average calculated for:",
        len(avg_volume),
        "symbols"
    )

    return avg_volume


# ============================================================
# RVOL
# ============================================================

def calculate_rvol(
    current_data,
    avg_volume,
):

    result = current_data.merge(
        avg_volume,
        on="TckrSymb",
        how="left",
    )

    result = result[
        result["AVG_20D_VOLUME"] > 0
    ].copy()

    result["RVOL"] = (
        result["TtlTradgVol"]
        /
        result["AVG_20D_VOLUME"]
    )

    result = result.dropna(
        subset=[
            "AVG_20D_VOLUME",
            "RVOL",
        ]
    )

    result = result.sort_values(
        "RVOL",
        ascending=False,
    )

    return result


# ============================================================
# 5-DAY VOLUME ANALYSIS
# ============================================================

def calculate_5d_volume_analysis(
    candidates,
    previous_days,
    avg_volume,
):

    print("\n")
    print("=" * 60)
    print("5-DAY VOLUME ANALYSIS")
    print("=" * 60)

    if not previous_days:
        return candidates

    # Previous 5 trading days
    last_5_days = previous_days[:5]

    combined_5d = pd.concat(
        last_5_days,
        ignore_index=True,
    )

    # Merge 20D average
    combined_5d = combined_5d.merge(
        avg_volume,
        on="TckrSymb",
        how
