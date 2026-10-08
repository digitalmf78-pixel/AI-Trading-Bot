import io
import os
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests


# ============================================================
# NSE V8 - MODULE A
# EOD VOLUME GAINER + 20D AVERAGE VOLUME + RVOL
# ============================================================

BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
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

    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not configured.")
        return

    if not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_CHAT_ID not configured.")
        return

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
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

        print(
            "Telegram HTTP status:",
            response.status_code
        )

        print(
            "Telegram response:",
            response.text[:500]
        )

    except Exception as e:

        print(
            "Telegram error:",
            repr(e)
        )


# ============================================================
# DOWNLOAD NSE BHAVCOPY
# ============================================================

def download_bhavcopy(date_obj):

    date_str = date_obj.strftime("%Y%m%d")

    url = BHAVCOPY_URL.format(
        date=date_str
    )

    print("\n----------------------------------------")
    print(
        "Downloading NSE Bhavcopy:",
        date_str
    )
    print("URL:", url)

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=60,
        )

        print(
            "HTTP status:",
            response.status_code
        )

        print(
            "Response size:",
            len(response.content),
            "bytes"
        )

        if response.status_code != 200:

            print(
                "Bhavcopy unavailable for:",
                date_str
            )

            return None

        if len(response.content) < 1000:

            print(
                "ERROR: Response is too small."
            )

            return None

        try:

            zip_file = zipfile.ZipFile(
                io.BytesIO(response.content)
            )

        except zipfile.BadZipFile:

            print(
                "ERROR: Downloaded file is not a valid ZIP."
            )

            return None

        files = zip_file.namelist()

        print(
            "ZIP contents:",
            files
        )

        csv_files = [
            file_name
            for file_name in files
            if file_name.lower().endswith(".csv")
        ]

        if not csv_files:

            print(
                "ERROR: No CSV file found in ZIP."
            )

            return None

        csv_name = csv_files[0]

        print(
            "Reading CSV:",
            csv_name
        )

        with zip_file.open(csv_name) as csv_file:

            df = pd.read_csv(
                csv_file
            )

        print(
            "Rows:",
            len(df)
        )

        print(
            "Columns:",
            list(df.columns)
        )

        return df

    except requests.RequestException as e:

        print(
            "NSE request error:",
            repr(e)
        )

        return None

    except Exception as e:

        print(
            "Bhavcopy processing error:",
            repr(e)
        )

        return None


# ============================================================
# PREPARE VOLUME DATA
# ============================================================

def prepare_volume_data(df):

    print(
        "\nPreparing volume data..."
    )

    if df is None:

        print(
            "ERROR: DataFrame is None."
        )

        return None

    if df.empty:

        print(
            "ERROR: DataFrame is empty."
        )

        return None

    required_columns = [
        "TckrSymb",
        "ClsPric",
        "TtlTradgVol",
    ]

    for column in required_columns:

        if column not in df.columns:

            print(
                "ERROR: Missing column:",
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

    print(
        "Valid symbols:",
        len(data)
    )

    return data


# ============================================================
# FIND PREVIOUS 20 TRADING DAYS
# ============================================================

def get_previous_20_days(current_date):

    print("\n")
    print("=" * 60)
    print("COLLECTING PREVIOUS 20 TRADING DAYS")
    print("=" * 60)

    previous_days = []

    check_date = (
        current_date
        - timedelta(days=1)
    )

    attempts = 0

    while (
        len(previous_days) < 20
        and
        attempts < 50
    ):

        date_text = check_date.strftime(
            "%Y-%m-%d"
        )

        print(
            f"\nChecking {date_text} "
            f"| Trading days found: "
            f"{len(previous_days)}/20"
        )

        df = download_bhavcopy(
            check_date
        )

        if df is not None:

            prepared = prepare_volume_data(
                df
            )

            if (
                prepared is not None
                and
                not prepared.empty
            ):

                prepared["Date"] = date_text

                previous_days.append(
                    prepared
                )

                print(
                    "Accepted:",
                    date_text
                )

        check_date -= timedelta(
            days=1
        )

        attempts += 1

    print("\n")
    print(
        "Previous trading days collected:",
        len(previous_days)
    )

    return previous_days


# ============================================================
# CALCULATE 20D AVERAGE VOLUME
# ============================================================

def calculate_20d_average(
    previous_days
):

    print("\n")
    print("=" * 60)
    print("CALCULATING 20D AVERAGE VOLUME")
    print("=" * 60)

    if not previous_days:

        print(
            "ERROR: No previous-day data."
        )

        return None

    combined = pd.concat(
        previous_days,
        ignore_index=True,
    )

    avg_volume = (
        combined
        .groupby("TckrSymb")[
            "TtlTradgVol"
        ]
        .mean()
        .reset_index()
    )

    avg_volume.rename(
        columns={
            "TtlTradgVol":
            "AVG_20D_VOLUME"
        },
        inplace=True,
    )

    print(
        "Symbols with 20D average:",
        len(avg_volume)
    )

    return avg_volume


# ============================================================
# CALCULATE RVOL
# ============================================================

def calculate_rvol(
    current_data,
    avg_volume
):

    print("\n")
    print("=" * 60)
    print("CALCULATING RVOL")
    print("=" * 60)

    if current_data is None:

        print(
            "ERROR: Current data unavailable."
        )

        return None

    if avg_volume is None:

        print(
            "ERROR: 20D average unavailable."
        )

        return None

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

    print(
        "RVOL calculated for:",
        len(result),
        "symbols"
    )

    return result


# ============================================================
# RVOL CLASSIFICATION
# ============================================================

def rvol_classification(
    rvol
):

    if rvol > 3:

        return "Exceptional"

    elif rvol >= 2:

        return "Strong"

    elif rvol >= 1.5:

        return "Good"

    elif rvol >= 1:

        return "Normal"

    else:

        return "Weak"


# ============================================================
# CREATE TELEGRAM MESSAGE
# ============================================================

def create_telegram_message(
    result,
    current_date
):

    top20 = result.head(20)

    lines = []

    lines.append(
        "📊 NSE V8 EOD VOLUME GAINER + RVOL"
    )

    lines.append(
        f"📅 {current_date.strftime('%d-%b-%Y')}"
    )

    lines.append("")

    lines.append(
        "⚠️ Screening layer only"
    )

    lines.append(
        "❌ NOT a BUY signal"
    )

    lines.append("")

    for rank, (_, row) in enumerate(
        top20.iterrows(),
        start=1
    ):

        symbol = str(
            row["TckrSymb"]
        )

        volume = int(
            row["TtlTradgVol"]
        )

        avg_volume = int(
            row["AVG_20D_VOLUME"]
        )

        rvol = float(
            row["RVOL"]
        )

        classification = (
            rvol_classification(
                rvol
            )
        )

        lines.append(
            f"{rank}. {symbol}"
        )

        lines.append(
            f"Vol: {volume:,}"
        )

        lines.append(
            f"20D Avg: {avg_volume:,}"
        )

        lines.append(
            f"RVOL: {rvol:.2f}x "
            f"({classification})"
        )

        lines.append("")

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 60)
    print("NSE V8 MODULE A")
    print("EOD VOLUME GAINER + 20D AVG + RVOL")
    print("=" * 60)
    print("")

    print(
        "Python script started successfully."
    )

    # --------------------------------------------------------
    # FIND LATEST AVAILABLE BHAVCOPY
    # --------------------------------------------------------

    today = datetime.now()

    current_df = None
    current_date = None

    print("")
    print(
        "Searching for latest NSE EOD Bhavcopy..."
    )

    for days_back in range(0, 7):

        test_date = (
            today
            - timedelta(days=days_back)
        )

        df = download_bhavcopy(
            test_date
        )

        if df is not None:

            current_df = df
            current_date = test_date

            print("")
            print(
                "Latest available EOD date:",
                current_date.strftime(
                    "%Y-%m-%d"
                )
            )

            break

    if current_df is None:

        print("")
        print(
            "ERROR: Could not find NSE Bhavcopy."
        )

        return

    # --------------------------------------------------------
    # PREPARE CURRENT DATA
    # --------------------------------------------------------

    current_data = prepare_volume_data(
        current_df
    )

    if current_data is None:

        print(
            "ERROR: Current data preparation failed."
        )

        return

    # --------------------------------------------------------
    # PREVIOUS 20 DAYS
    # --------------------------------------------------------

    previous_days = (
        get_previous_20_days(
            current_date
        )
    )

    if not previous_days:

        print(
            "ERROR: Previous trading data unavailable."
        )

        return

    # --------------------------------------------------------
    # 20D AVERAGE
    # --------------------------------------------------------

    avg_volume = (
        calculate_20d_average(
            previous_days
        )
    )

    if avg_volume is None:

        print(
            "ERROR: 20D average calculation failed."
        )

        return

    # --------------------------------------------------------
    # RVOL
    # --------------------------------------------------------

    result = calculate_rvol(
        current_data,
        avg_volume
    )

    if result is None:

        print(
            "ERROR: RVOL calculation failed."
        )

        return

    if result.empty:

        print(
            "ERROR: RVOL result is empty."
        )

        return

    # --------------------------------------------------------
    # TOP 20 RVOL
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("TOP 20 RVOL")
    print("=" * 60)

    top20 = result.head(20)

    for rank, (_, row) in enumerate(
        top20.iterrows(),
        start=1
    ):

        symbol = str(
            row["TckrSymb"]
        )

        volume = int(
            row["TtlTradgVol"]
        )

        avg_volume = int(
            row["AVG_20D_VOLUME"]
        )

        rvol = float(
            row["RVOL"]
        )

        category = (
            rvol_classification(
                rvol
            )
        )

        print(
            f"{rank:02d}. "
            f"{symbol:<15} "
            f"Vol={volume:,} "
            f"20D={avg_volume:,} "
            f"RVOL={rvol:.2f}x "
            f"[{category}]"
        )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    message = create_telegram_message(
        result,
        current_date
    )

    send_telegram(
        message
    )

    # --------------------------------------------------------
    # COMPLETE
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("MODULE A VOLUME + RVOL COMPLETED")
    print("=" * 60)
    print("")


# ============================================================
# SCRIPT ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
