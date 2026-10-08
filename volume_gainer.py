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
# DOWNLOAD UDiFF BHAVCOPY
# ============================================================

def download_bhavcopy(session, date):

    date_str = date.strftime("%Y%m%d")

    url = BHAVCOPY_URL.format(
        date=date_str
    )

    print(f"Trying NSE Bhavcopy: {date_str}")
    print(f"URL: {url}")

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

                # Validate ZIP
                if zipfile.is_zipfile(
                    io.BytesIO(response.content)
                ):
                    return response.content

                print("Response is not a valid ZIP.")

        elif response.status_code == 403:

            print("NSE returned 403 Forbidden.")

        elif response.status_code == 404:

            print("Bhavcopy not found for this date.")

        else:

            print(
                f"NSE returned HTTP "
                f"{response.status_code}"
            )

    except Exception as e:

        print(
            f"Download error: {e}"
        )

    return None


# ============================================================
# FIND LATEST TRADING DAY
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

        time.sleep(1)

    raise RuntimeError(
        "Could not download recent "
        "NSE CM-UDiFF Bhavcopy."
    )


# ============================================================
# READ ZIP
# ============================================================

def read_bhavcopy(raw_data):

    with zipfile.ZipFile(
        io.BytesIO(raw_data)
    ) as z:

        files = z.namelist()

        print("Files inside ZIP:")

        for file_name in files:
            print(f" - {file_name}")

        csv_files = [
            f for f in files
            if f.lower().endswith(".csv")
        ]

        if not csv_files:

            raise RuntimeError(
                "No CSV file found inside NSE ZIP."
            )

        csv_file = csv_files[0]

        print(
            f"Reading CSV: {csv_file}"
        )

        with z.open(csv_file) as f:

            df = pd.read_csv(
                f,
                low_memory=False
            )

    return df


# ============================================================
# CALCULATE VOLUME GAINERS
# ============================================================

def calculate_volume_gainers(df):

    # Normalize column names
    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    print("\nNSE columns detected:")

    print(
        df.columns.tolist()
    )

    # UDiFF columns
    required = [
        "TckrSymb",
        "ClsPric",
        "TtlTradgVol",
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:

        raise RuntimeError(
            "Required UDiFF columns missing: "
            + str(missing)
            + "\nAvailable columns: "
            + str(df.columns.tolist())
        )

    # Convert numeric columns
    df["ClsPric"] = pd.to_numeric(
        df["ClsPric"],
        errors="coerce"
    )

    df["TtlTradgVol"] = pd.to_numeric(
        df["TtlTradgVol"],
        errors="coerce"
    )

    # Remove invalid rows
    df = df.dropna(
        subset=[
            "TckrSymb",
            "ClsPric",
            "TtlTradgVol",
        ]
    )

    # Keep positive prices and volume
    df = df[
        (df["ClsPric"] > 0)
        &
        (df["TtlTradgVol"] > 0)
    ]

    result = df[
        [
            "TckrSymb",
            "ClsPric",
            "TtlTradgVol",
        ]
    ].copy()

    result = result.rename(
        columns={
            "TckrSymb": "SYMBOL",
            "ClsPric": "CLOSE",
            "TtlTradgVol": "VOLUME",
        }
    )

    # Sort by EOD volume
    result = result.sort_values(
        "VOLUME",
        ascending=False
    )

    result["VOLUME_RANK"] = range(
        1,
        len(result) + 1
    )

    return result.head(20)


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def build_telegram_message(
    trading_date,
    gainers
):

    lines = []

    lines.append(
        "📊 NSE EOD VOLUME GAINER"
    )

    lines.append(
        f"Trading Date: "
        f"{trading_date.strftime('%d-%b-%Y')}"
    )

    lines.append("")

    lines.append(
        "Top 20 by EOD Volume:"
    )

    lines.append("")

    for _, row in gainers.iterrows():

        symbol = row["SYMBOL"]

        close = row["CLOSE"]

        volume = int(
            row["VOLUME"]
        )

        rank = int(
            row["VOLUME_RANK"]
        )

        lines.append(
            f"{rank}. {symbol} | "
            f"Close ₹{close:.2f} | "
            f"Vol {volume:,}"
        )

    lines.append("")

    lines.append(
        "⚠️ Screening layer only."
    )

    lines.append(
        "Volume Gainer is NOT a BUY signal."
    )

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Starting NSE EOD "
        "Volume Gainer test..."
    )

    session = get_session()

    trading_date, raw_data = (
        find_latest_bhavcopy(
            session
        )
    )

    print(
        f"\nTrading date: "
        f"{trading_date}"
    )

    print(
        f"Downloaded bytes: "
        f"{len(raw_data)}"
    )

    df = read_bhavcopy(
        raw_data
    )

    print(
        f"Rows received: "
        f"{len(df)}"
    )

    gainers = (
        calculate_volume_gainers(
            df
        )
    )

    print(
        "\nTop 20 volume stocks:"
    )

    print(
        gainers.to_string(
            index=False
        )
    )

    # Telegram
    message = build_telegram_message(
        trading_date,
        gainers
    )

    print(
        "\nSending result to Telegram..."
    )

    send_telegram(
        message
    )


if __name__ == "__main__":
    main()
