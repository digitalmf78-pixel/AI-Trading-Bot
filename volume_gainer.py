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
        print("Response size:", len(response.content), "bytes")

        if response.status_code != 200:
            print("Bhavcopy unavailable.")
            return None

        if len(response.content) < 1000:
            print("Response too small.")
            return None

        with zipfile.ZipFile(
            io.BytesIO(response.content)
        ) as z:

            csv_files = [
                x
                for x in z.namelist()
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
# PREPARE VOLUME DATA
# ============================================================

def prepare_volume_data(df):

    if df is None or df.empty:
        return None

    required = [
        "TckrSymb",
        "ClsPric",
        "TtlTradgVol",
    ]

   
