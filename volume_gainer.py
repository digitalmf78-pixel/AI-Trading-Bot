import io
import os
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests


# ============================================================
# NSE SWING TRADING V8
# MODULE A - EOD VOLUME ANALYSIS
#
# Current Bhavcopy
#       ↓
# 20D Average Volume
#       ↓
# RVOL
#       ↓
# Previous 5 Days Volume
#       ↓
# Low Volume %
#       ↓
# 60% Low Volume Rule
#       ↓
# 5D Volume Pattern
#       ↓
# Telegram Output
#
# IMPORTANT:
# Volume/RVOL is ONLY a screening layer.
# It is NOT a BUY signal.
# ============================================================


# ============================================================
# CONFIGURATION
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

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID"
)


# ============================================================
# TELEGRAM FUNCTION
# ============================================================

def send_telegram(message):

    print("")
    print("=" * 60)
    print("TELEGRAM")
    print("=" * 60)

    if not TELEGRAM_BOT_TOKEN:
        print(
            "TELEGRAM_BOT_TOKEN is not configured."
        )
        return

    if not TELEGRAM_CHAT_ID:
        print(
            "TELEGRAM_CHAT_ID is not configured."
        )
        return

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}"
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

        print(
            "Telegram HTTP status:",
            response.status_code,
        )

        print(
            "Telegram response:",
            response.text[:500],
        )

    except Exception as exc:

        print(
            "Telegram error:",
            repr(exc),
        )


# ============================================================
# DOWNLOAD NSE BHAVCOPY
# ============================================================

def download_bhavcopy(date_obj):

    date_string = date_obj.strftime(
        "%Y%m%d"
    )

    url = BHAVCOPY_URL.format(
        date=date_string
    )

    print("")
    print("-" * 60)
    print(
        "Downloading NSE Bhavcopy:",
        date_obj.strftime("%Y-%m-%d"),
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
            response.status_code,
        )

        print(
            "Response size:",
            len(response.content),
            "bytes",
        )

        if response.status_code != 200:

            print(
                "Bhavcopy not available for:",
                date_obj.strftime("%Y-%m-%d"),
            )

            return None

        if len(response.content) < 1000:

            print(
                "Response is too small."
            )

            return None

        try:

            with zipfile.ZipFile(
                io.BytesIO(response.content)
            ) as zip_file:

                csv_files = [
                    name
                    for name in zip_file.namelist()
                    if name.lower().endswith(".csv")
                ]

                if not csv_files:

                    print(
                        "No CSV file found "
                        "inside ZIP."
                    )

                    return None

                csv_name = csv_files[0]

                print(
                    "Extracting CSV:",
                    csv_name,
                )

                with zip_file.open(
                    csv_name
                ) as csv_file:

                    df = pd.read_csv(
                        csv_file
                    )

        except zipfile.BadZipFile:

            print(
                "Downloaded file is not a valid ZIP."
            )

            return None

        print(
            "Rows downloaded:",
            len(df),
        )

        print(
            "Columns:",
            list(df.columns)[:20],
        )

        return df

    except requests.RequestException as exc:

        print(
            "NSE request error:",
            repr(exc),
        )

        return None

    except Exception as exc:

        print(
            "Bhavcopy error:",
            repr(exc),
        )

        return None


# ============================================================
# PREPARE VOLUME DATA
# ============================================================

def prepare_volume_data(df):

    if df is None:

        return None

    if df.empty:

        return None

    required_columns = [
        "TckrSymb",
        "ClsPric",
        "TtlTradgVol",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        print(
            "Missing required columns:",
            missing_columns,
        )

        return None

    data = df[
        required_columns
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
        subset=required_columns
    )

    data = data[
        (data["ClsPric"] > 0)
        &
        (data["TtlTradgVol"] > 0)
    ].copy()

    data = data.drop_duplicates(
        subset=["TckrSymb"]
    )

    return data


# ============================================================
# GET PREVIOUS 20 TRADING DAYS
# ============================================================

def get_previous_20_days(
    current_date
):

    print("")
    print("=" * 60)
    print("COLLECTING PREVIOUS 20 TRADING DAYS")
    print("=" * 60)

    trading_days = []

    check_date = (
        current_date
        - timedelta(days=1)
    )

    maximum_calendar_days = 70

    while len(trading_days) < 20:

        print(
            f"Checking "
            f"{check_date:%Y-%m-%d} | "
            f"Found "
            f"{len(trading_days)}/20"
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
                and not prepared.empty
            ):

                prepared["Date"] = (
                    check_date.strftime(
                        "%Y-%m-%d"
                    )
                )

                trading_days.append(
                    prepared
                )

                print(
                    "Accepted trading day:",
                    check_date.strftime(
                        "%Y-%m-%d"
                    ),
                )

        check_date -= timedelta(
            days=1
        )

        elapsed_days = (
            current_date - check_date
        ).days

        if elapsed_days > maximum_calendar_days:

            print(
                "ERROR: Could not collect "
                "20 trading days."
            )

            break

    print("")
    print(
        "Previous trading days collected:",
        len(trading_days),
    )

    return trading_days


# ============================================================
# CALCULATE 20D AVERAGE VOLUME
# ============================================================

def calculate_20d_average(
    previous_days
):

    print("")
    print("=" * 60)
    print("CALCULATING 20D AVERAGE VOLUME")
    print("=" * 60)

    if not previous_days:

        print(
            "No previous day data."
        )

        return None

    combined = pd.concat(
        previous_days,
        ignore_index=True,
    )

    average_volume = (
        combined
        .groupby("TckrSymb")[
            "TtlTradgVol"
        ]
        .mean()
        .reset_index()
    )

    average_volume.rename(
        columns={
            "TtlTradgVol":
                "AVG_20D_VOLUME"
        },
        inplace=True,
    )

    average_volume = average_volume[
        average_volume[
            "AVG_20D_VOLUME"
        ] > 0
    ].copy()

    print(
        "Symbols with 20D average:",
        len(average_volume),
    )

    return average_volume


# ============================================================
# CALCULATE RVOL
#
# RVOL = Today's Volume / 20D Average Volume
#
# < 1      = Weak
# 1 - 1.5  = Normal
# 1.5 - 2  = Good
# 2 - 3    = Strong
# > 3      = Exceptional
# ============================================================

def calculate_rvol(
    current_data,
    average_volume
):

    print("")
    print("=" * 60)
    print("CALCULATING RVOL")
    print("=" * 60)

    result = current_data.merge(
        average_volume,
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
        by="RVOL",
        ascending=False,
    ).reset_index(
        drop=True
    )

    print(
        "RVOL calculated for:",
        len(result),
        "symbols",
    )

    return result


# ============================================================
# 5-DAY VOLUME ANALYSIS
#
# V8 RULE:
# Previous 5 days are checked individually.
#
# Daily Volume % of 20D Average =
# Daily Volume / 20D Average × 100
#
# 60% LOW VOLUME RULE:
# At least 3 of previous 5 days
# should have volume below 20D average
# for accumulation/pullback setups.
#
# IMPORTANT:
# This is NOT a universal hard filter.
# Genuine breakouts can still qualify.
# ============================================================

def calculate_5d_volume_analysis(
    candidates,
    previous_days,
    average_volume
):

    print("")
    print("=" * 60)
    print("5-DAY VOLUME ANALYSIS")
    print("=" * 60)

    if len(previous_days) < 5:

        print(
            "WARNING: Less than 5 "
            "previous trading days available."
        )

        candidates[
            "LowVolumeDays5D"
        ] = 0

        candidates[
            "LowVolumePct5D"
        ] = 0.0

        candidates[
            "60PctRule"
        ] = False

        candidates[
            "5DVolumePattern"
        ] = "Insufficient data"

        return candidates

    # --------------------------------------------------------
    # Take the previous 5 trading days.
    #
    # previous_days is stored newest -> oldest.
    # --------------------------------------------------------

    last_5_days = previous_days[:5]

    combined_5d = pd.concat(
        last_5_days,
        ignore_index=True,
    )

    # --------------------------------------------------------
    # Add 20D average
    # --------------------------------------------------------

    combined_5d = combined_5d.merge(
        average_volume,
        on="TckrSymb",
        how="left",
    )

    # --------------------------------------------------------
    # Daily volume as % of 20D average
    # --------------------------------------------------------

    combined_5d[
        "VolumePct20D"
    ] = (
        combined_5d[
            "TtlTradgVol"
        ]
        /
        combined_5d[
            "AVG_20D_VOLUME"
        ]
        *
        100
    )

    # --------------------------------------------------------
    # Low-volume day
    # --------------------------------------------------------

    combined_5d[
        "LowVolumeDay"
    ] = (
        combined_5d[
            "TtlTradgVol"
        ]
        <
        combined_5d[
            "AVG_20D_VOLUME"
        ]
    )

    # --------------------------------------------------------
    # Count low-volume days
    # --------------------------------------------------------

    low_volume_stats = (
        combined_5d
        .groupby("TckrSymb")[
            "LowVolumeDay"
        ]
        .sum()
        .reset_index()
    )

    low_volume_stats.rename(
        columns={
            "LowVolumeDay":
                "LowVolumeDays5D"
        },
        inplace=True,
    )

    # --------------------------------------------------------
    # Low-volume percentage
    # --------------------------------------------------------

    low_volume_stats[
        "LowVolumePct5D"
    ] = (
        low_volume_stats[
            "LowVolumeDays5D"
        ]
        /
        5
        *
        100
    )

    # --------------------------------------------------------
    # 60% RULE
    #
    # 3 out of 5 = 60%
    # --------------------------------------------------------

    low_volume_stats[
        "60PctRule"
    ] = (
        low_volume_stats[
            "LowVolumeDays5D"
        ]
        >= 3
    )

    # --------------------------------------------------------
    # Merge with current candidates
    # --------------------------------------------------------

    candidates = candidates.merge(
        low_volume_stats,
        on="TckrSymb",
        how="left",
    )

    # --------------------------------------------------------
    # 5-DAY VOLUME PATTERN
    #
    # We compare the first two days and
    # last two days of the 5-day sequence.
    #
    # This is a screening description only.
    # Final V8 interpretation also requires
    # current price + volume confirmation.
    # --------------------------------------------------------

    pattern_rows = []

    for symbol, group in combined_5d.groupby(
        "TckrSymb"
    ):

        # Convert date to datetime
        group = group.copy()

        group["Date"] = pd.to_datetime(
            group["Date"],
            errors="coerce",
        )

        # Oldest -> newest
        group = group.sort_values(
            by="Date"
        )

        volumes = (
            group[
                "TtlTradgVol"
            ]
            .tolist()
        )

        if len(volumes) < 5:

            pattern = (
                "Insufficient data"
            )

        else:

            first_two_average = (
                sum(volumes[:2])
                /
                2
            )

            last_two_average = (
                sum(volumes[-2:])
                /
                2
            )

            if (
                last_two_average
                <
                first_two_average * 0.80
            ):

                pattern = (
                    "Contraction"
                )

            elif (
                last_two_average
                >
                first_two_average * 1.20
            ):

                pattern = (
                    "Expansion"
                )

            else:

                pattern = "Mixed"

        pattern_rows.append(
            {
                "TckrSymb": symbol,
                "5DVolumePattern": pattern,
            }
        )

    pattern_df = pd.DataFrame(
        pattern_rows
    )

    candidates = candidates.merge(
        pattern_df,
        on="TckrSymb",
        how="left",
    )

    # --------------------------------------------------------
    # Fill missing values
    # --------------------------------------------------------

    candidates[
        "LowVolumeDays5D"
    ] = (
        candidates[
            "LowVolumeDays5D"
        ]
        .fillna(0)
        .astype(int)
    )

    candidates[
        "LowVolumePct5D"
    ] = (
        candidates[
            "LowVolumePct5D"
        ]
        .fillna(0.0)
    )

    candidates[
        "60PctRule"
    ] = (
        candidates[
            "60PctRule"
        ]
        .fillna(False)
        .astype(bool)
    )

    candidates[
        "5DVolumePattern"
    ] = (
        candidates[
            "5DVolumePattern"
        ]
        .fillna(
            "Insufficient data"
        )
    )

    return candidates


# ============================================================
# RVOL CLASSIFICATION
# ============================================================

def get_rvol_classification(
    rvol
):

    if rvol > 3:
        return "Exceptional"

    if rvol >= 2:
        return "Strong"

    if rvol >= 1.5:
        return "Good"

    if rvol >= 1:
        return "Normal"

    return "Weak"


# ============================================================
# CREATE TELEGRAM MESSAGE
# ============================================================

def create_telegram_message(
    result,
    current_date
):

    message_lines = []

    message_lines.append(
        "📊 NSE V8 EOD VOLUME ANALYSIS"
    )

    message_lines.append(
        f"📅 {current_date:%d-%b-%Y}"
    )

    message_lines.append("")

    message_lines.append(
        "Volume + RVOL + 5D Analysis"
    )

    message_lines.append(
        "⚠️ Screening layer only"
    )

    message_lines.append(
        "❌ NOT a BUY signal"
    )

    message_lines.append("")

    top_rows = result.head(20)

    for rank, (_, row) in enumerate(
        top_rows.iterrows(),
        start=1,
    ):

        symbol = str(
            row["TckrSymb"]
        )

        volume = int(
            row["TtlTradgVol"]
        )

        average = int(
            row["AVG_20D_VOLUME"]
        )

        rvol = float(
            row["RVOL"]
        )

        low_days = int(
            row["LowVolumeDays5D"]
        )

        low_pct = float(
            row["LowVolumePct5D"]
        )

        pattern = str(
            row["5DVolumePattern"]
        )

        rule_status = (
            "PASS"
            if bool(
                row["60PctRule"]
            )
            else "NO"
        )

        classification = (
            get_rvol_classification(
                rvol
            )
        )

        message_lines.append(
            f"{rank}. {symbol}"
        )

        message_lines.append(
            f"Vol: {volume:,}"
        )

        message_lines.append(
            f"20D Avg: {average:,}"
        )

        message_lines.append(
            f"RVOL: {rvol:.2f}x "
            f"({classification})"
        )

        message_lines.append(
            f"5D Low Vol: "
            f"{low_days}/5 "
            f"({low_pct:.0f}%)"
        )

        message_lines.append(
            f"5D Pattern: {pattern}"
        )

        message_lines.append(
            f"60% Rule: {rule_status}"
        )

        message_lines.append("")

    return "\n".join(
        message_lines
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 60)
    print(
        "NSE V8 MODULE A"
    )
    print(
        "EOD VOLUME + 20D AVG + RVOL + 5D ANALYSIS"
    )
    print("=" * 60)

    print(
        "Python script started successfully."
    )

    # --------------------------------------------------------
    # STEP 1
    # FIND LATEST AVAILABLE BHAVCOPY
    # --------------------------------------------------------

    print("")
    print(
        "STEP 1: Searching for latest NSE EOD Bhavcopy..."
    )

    today = datetime.now()

    current_df = None
    current_date = None

    for days_back in range(7):

        test_date = (
            today
            -
            timedelta(days=days_back)
        )

        print(
            "Trying date:",
            test_date.strftime(
                "%Y-%m-%d"
            ),
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
                ),
            )

            break

    if current_df is None:

        print("")
        print(
            "ERROR: No NSE Bhavcopy found "
            "within last 7 days."
        )

        return

    # --------------------------------------------------------
    # STEP 2
    # PREPARE CURRENT DATA
    # --------------------------------------------------------

    print("")
    print(
        "STEP 2: Preparing current EOD data..."
    )

    current_data = prepare_volume_data(
        current_df
    )

    if (
        current_data is None
        or current_data.empty
    ):

        print(
            "ERROR: Current EOD data "
            "preparation failed."
        )

        return

    print(
        "Current valid symbols:",
        len(current_data),
    )

    # --------------------------------------------------------
    # STEP 3
    # PREVIOUS 20 TRADING DAYS
    # --------------------------------------------------------

    print("")
    print(
        "STEP 3: Collecting previous "
        "20 trading days..."
    )

    previous_days = (
        get_previous_20_days(
            current_date
        )
    )

    if len(previous_days) < 20:

        print("")
        print(
            "ERROR: Full 20 trading days "
            "could not be collected."
        )

        return

    # --------------------------------------------------------
    # STEP 4
    # 20D AVERAGE
    # --------------------------------------------------------

    print("")
    print(
        "STEP 4: Calculating 20D average volume..."
    )

    average_volume = (
        calculate_20d_average(
            previous_days
        )
    )

    if (
        average_volume is None
        or average_volume.empty
    ):

        print(
            "ERROR: 20D average "
            "calculation failed."
        )

        return

    # --------------------------------------------------------
    # STEP 5
    # RVOL
    # --------------------------------------------------------

    print("")
    print(
        "STEP 5: Calculating RVOL..."
    )

    result = calculate_rvol(
        current_data,
        average_volume,
    )

    if (
        result is None
        or result.empty
    ):

        print(
            "ERROR: RVOL calculation "
            "returned no data."
        )

        return

    # --------------------------------------------------------
    # STEP 6
    # 5-DAY VOLUME ANALYSIS
    # --------------------------------------------------------

    print("")
    print(
        "STEP 6: Calculating "
        "5-day volume analysis..."
    )

    result = calculate_5d_volume_analysis(
        result,
        previous_days,
        average_volume,
    )

    if result is None or result.empty:

        print(
            "ERROR: 5-day volume "
            "analysis returned no data."
        )

        return

    # --------------------------------------------------------
    # STEP 7
    # TOP 20 RESULTS
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print(
        "TOP 20 RVOL + 5D VOLUME ANALYSIS"
    )
    print("=" * 60)

    top_20 = result.head(20)

    for rank, (_, row) in enumerate(
        top_20.iterrows(),
        start=1,
    ):

        symbol = str(
            row["TckrSymb"]
        )

        volume = int(
            row["TtlTradgVol"]
        )

        average = int(
            row["AVG_20D_VOLUME"]
        )

        rvol = float(
            row["RVOL"]
        )

        low_days = int(
            row["LowVolumeDays5D"]
        )

        low_pct = float(
            row["LowVolumePct5D"]
        )

        pattern = str(
            row["5DVolumePattern"]
        )

        rule_status = (
            "PASS"
            if bool(
                row["60PctRule"]
            )
            else "NO"
        )

        print(
            f"{rank:02d}. "
            f"{symbol:<16} "
            f"Vol={volume:,} | "
            f"20D={average:,} | "
            f"RVOL={rvol:.2f}x | "
            f"Low5D={low_days}/5 "
            f"({low_pct:.0f}%) | "
            f"Pattern={pattern:<12} | "
            f"60%={rule_status}"
        )

    # --------------------------------------------------------
    # STEP 8
    # TELEGRAM
    # --------------------------------------------------------

    print("")
    print(
        "STEP 8: Sending Telegram report..."
    )

    telegram_message = (
        create_telegram_message(
            result,
            current_date,
        )
    )

    send_telegram(
        telegram_message
    )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print(
        "MODULE A COMPLETED"
    )
    print(
        "VOLUME + 20D AVG + RVOL + 5D ANALYSIS"
    )
    print("=" * 60)

    print(
        "Current EOD date:",
        current_date.strftime(
            "%Y-%m-%d"
        ),
    )

    print(
        "Final symbols analyzed:",
        len(result),
    )

    print(
        "===== SCRIPT FINISHED SUCCESSFULLY ====="
    )


# ============================================================
# PYTHON ENTRY POINT
#
# DO NOT MOVE THIS INSIDE ANY FUNCTION.
# ============================================================

if __name__ == "__main__":
    main()
