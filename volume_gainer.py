import io
import os
import time
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
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": "application/zip,application/octet-stream,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token:
        print("WARNING: TELEGRAM_BOT_TOKEN is not configured.")
        return False

    if not chat_id:
        print("WARNING: TELEGRAM_CHAT_ID is not configured.")
        return False

    url = TELEGRAM_URL.format(token=token)

    payload = {
        "chat_id": chat_id,
        "text": message,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=30,
        )

        print(f"Telegram HTTP status: {response.status_code}")
        print(f"Telegram response: {response.text}")

        response.raise_for_status()

        data = response.json()

        if data.get("ok"):
            print("Telegram message sent successfully.")
            return True

        print("Telegram API returned an error.")
        return False

    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False


# ============================================================
# NSE SESSION
# ============================================================

def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


# ============================================================
# DOWNLOAD BHAVCOPY
# ============================================================

def download_bhavcopy(session, date):

    date_str = date.strftime("%Y%m%d")
    url = BHAVCOPY_URL.format(date=date_str)

    print(f"Trying NSE Bhavcopy: {date_str}")

    try:
        response = session.get(
            url,
            timeout=30,
        )

        print(
            f"NSE response: "
            f"{response.status_code} | "
            f"{len(response.content)} bytes"
        )

        if response.status_code == 200:
            if len(response.content) > 1000:
                if zipfile.is_zipfile(
                    io.BytesIO(response.content)
                ):
                    return response.content

                print("Response is not a valid ZIP.")

        elif response.status_code == 404:
            print("Bhavcopy not found for this date.")

        elif response.status_code == 403:
            print("NSE returned 403 Forbidden.")

        else:
            print(
                f"NSE returned HTTP "
                f"{response.status_code}"
            )

    except Exception as e:
        print(f"Download error: {e}")

    return None


# ============================================================
# READ CSV FROM ZIP
# ============================================================

def read_bhavcopy(raw_data):

    with zipfile.ZipFile(
        io.BytesIO(raw_data)
    ) as z:

        files = z.namelist()

        csv_files = [
            f for f in files
            if f.lower().endswith(".csv")
        ]

        if not csv_files:
            raise RuntimeError(
                "No CSV file found inside NSE ZIP."
            )

        csv_file = csv_files[0]

        with z.open(csv_file) as f:
            df = pd.read_csv(
                f,
                low_memory=False
            )

    return df


# ============================================================
# FIND LATEST BHAVCOPY
# ============================================================

def find_latest_bhavcopy(session):

    today = datetime.now().date()

    for days_back in range(0, 10):

        check_date = (
            today -
            timedelta(days=days_back)
        )

        data = download_bhavcopy(
            session,
            check_date
        )

        if data:
            print(
                f"Bhavcopy found: "
                f"{check_date}"
            )

            return check_date, data

    raise RuntimeError(
        "Could not download recent "
        "NSE CM-UDiFF Bhavcopy."
    )


# ============================================================
# PREPARE VOLUME DATA
# ============================================================

def prepare_volume_data(df):

    required = [
        "TckrSymb",
        "TtlTradgVol",
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise RuntimeError(
            "Required columns missing: "
            + str(missing)
            + "\nAvailable columns: "
            + str(df.columns.tolist())
        )

    df["TtlTradgVol"] = pd.to_numeric(
        df["TtlTradgVol"],
        errors="coerce"
    )

    df = df.dropna(
        subset=[
            "TckrSymb",
            "TtlTradgVol",
        ]
    )

    df = df[
        df["TtlTradgVol"] > 0
    ]

    result = df[
        [
            "TckrSymb",
            "TtlTradgVol",
        ]
    ].copy()

    result = result.rename(
        columns={
            "TckrSymb": "SYMBOL",
            "TtlTradgVol": "VOLUME",
        }
    )

    return result


# ============================================================
# FIND PREVIOUS 20 TRADING DAYS
# ============================================================

def get_previous_20_days(
    session,
    latest_date
):

    historical_data = []

    check_date = (
        latest_date -
        timedelta(days=1)
    )

    calendar_days_checked = 0

    print(
        "\nCollecting previous "
        "20 trading days..."
    )

    while (
        len(historical_data) < 20
        and calendar_days_checked < 40
    ):

        data = download_bhavcopy(
            session,
            check_date
        )

        if data:

            try:
                df = read_bhavcopy(
                    data
                )

                volume_df = (
                    prepare_volume_data(
                        df
                    )
                )

                historical_data.append(
                    (
                        check_date,
                        volume_df
                    )
                )

                print(
                    f"Historical day "
                    f"{len(historical_data)}/20: "
                    f"{check_date}"
                )

            except Exception as e:

                print(
                    f"Could not process "
                    f"{check_date}: {e}"
                )

        check_date -= timedelta(days=1)
        calendar_days_checked += 1

    if len(historical_data) < 20:

        raise RuntimeError(
            "Could not collect 20 previous "
            "trading days. "
            f"Only found {len(historical_data)}."
        )

    return historical_data


# ============================================================
# CALCULATE 20D AVERAGE VOLUME
# ============================================================

def calculate_20d_average(
    historical_data
):

    print(
        "\nCalculating 20D Average Volume..."
    )

    all_history = []

    for trading_date, df in historical_data:

        temp = df.copy()

        temp["DATE"] = trading_date

        all_history.append(temp)

    combined = pd.concat(
        all_history,
        ignore_index=True
    )

    stats = (
        combined
        .groupby("SYMBOL")["VOLUME"]
        .agg(
            AVG_20D="mean",
            OBS_20D="count",
        )
        .reset_index()
    )

    return stats


# ============================================================
# CALCULATE CURRENT VOLUME GAINERS
# ============================================================

def calculate_volume_gainers(
    df,
    avg_20d
):

    required = [
        "TckrSymb",
        "ClsPric",
        "TtlTradgVol",
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise RuntimeError(
            "Required current-day columns "
            "missing: "
            + str(missing)
            + "\nAvailable columns: "
            + str(df.columns.tolist())
        )

    df["ClsPric"] = pd.to_numeric(
        df["ClsPric"],
        errors="coerce"
    )

   
