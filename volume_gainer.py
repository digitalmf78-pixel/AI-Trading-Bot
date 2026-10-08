import io
import os
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests


# ============================================================
# NSE CM-UDiFF EOD BHAVCOPY
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


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not configured.")
        return

    url = (
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        "/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:
        response = requests.post(
            url,
            data=payload,
            timeout=30,
        )

        print("Telegram status:", response.status_code)
        print("Telegram response:", response.text[:500])

    except Exception as e:
        print("Telegram error:", repr(e))


# ============================================================
# DOWNLOAD NSE BHAVCOPY
# ============================================================

def download_bhavcopy(date_obj):

    date_str = date_obj.strftime("%Y%m%d")

    url = BHAVCOPY_URL.format(date=date_str)

    print("\n----------------------------------------")
    print("Downloading NSE Bhavcopy:", date_str)
    print("URL:", url)

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=60,
        )

        print("HTTP status:", response.status_code)
        print("File size:", len(response.content))

        if response.status_code != 200:
            print("Bhavcopy not available.")
            return None

        if len(response.content) < 1000:
            print("Response too small.")
            return None

        with zipfile.ZipFile(
            io.BytesIO(response.content)
        ) as z:

            files = z.namelist()

            print("ZIP files:", files)

            csv_files = [
                f for f in files
                if f.lower().endswith(".csv")
            ]

            if not csv_files:
                print("No CSV file found.")
                return None

            csv_name = csv_files[0]

            print("Reading CSV:", csv_name)

            with z.open(csv_name) as f:
                df = pd.read_csv(f)

        print("Rows:", len(df))
        print("Columns:", list(df.columns))

        return df

    except Exception as e:

        print(
            "Bhavcopy error:",
            repr(e)
        )

        return None


# ============================================================
# PREPARE VOLUME DATA
# ============================================================

def prepare_volume_data(df):

    if df is None or df.empty:
        return None

    required_columns = [
        "TckrSymb",
        "ClsPric",
        "TtlTradgVol",
    ]

    for column in required_columns:

        if column not in df.columns:

            print(
                "Missing required column:",
                column
            )

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
        data
