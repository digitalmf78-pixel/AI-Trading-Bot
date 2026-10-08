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
# -> 20D Average Volume
# -> RVOL
# -> Previous 5 Days Volume
# -> 60% Low Volume Rule
# -> Price + Volume Relationship
#
# IMPORTANT:
# This is still a SCREENING layer.
# It is NOT a BUY signal.
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
# TELEGRAM
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
# DOWNLOAD BHAVCOPY
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
            return None

        if len(response.content) < 1000:
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
# PREPARE CURRENT DATA
# ============================================================

def prepare_volume_data(df):

    if df is None:
        return None

    if df.empty:
        return None

    required_columns = [
        "TckrSymb",
        "ClsPric",
        "PrvsClsgPric",
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

    data["ClsPric"] = pd.to_numeric(
        data["ClsPric"],
        errors="coerce",
    )

    data["PrvsClsgPric"] = pd.to_numeric(
        data["PrvsClsgPric"],
        errors="coerce",
    )

    data["TtlTradgVol"] = pd.to_numeric(
        data["TtlTradgVol"],
        errors="coerce",
    )

    data = data.dropna(
        subset=required_columns
    )

    data = data[
        (data["ClsPric"] > 0)
        &
        (data["PrvsClsgPric"] > 0)
        &
        (data["TtlTradgVol"] > 0)
    ].copy()

    data = data.drop_duplicates(
        subset=["TckrSymb"]
    )

    return data


# ============================================================
# PREVIOUS 20 TRADING DAYS
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

        if (
            current_date - check_date
        ).days > 70:

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
# 20D AVERAGE VOLUME
# ============================================================

def calculate_20d_average(
    previous_days
):

    print("")
    print("=" * 60)
    print("CALCULATING 20D AVERAGE VOLUME")
    print("=" * 60)

    if not previous_days:
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
# RVOL
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

    last_5_days = previous_days[:5]

    combined_5d = pd.concat(
        last_5_days,
        ignore_index=True,
    )

    combined_5d = combined_5d.merge(
        average_volume,
        on="TckrSymb",
        how="left",
    )

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

    low_volume_stats[
        "60PctRule"
    ] = (
        low_volume_stats[
            "LowVolumeDays5D"
        ]
        >= 3
    )

    candidates = candidates.merge(
        low_volume_stats,
        on="TckrSymb",
        how="left",
    )

    # --------------------------------------------------------
    # 5D PATTERN
    # --------------------------------------------------------

    pattern_rows = []

    for symbol, group in combined_5d.groupby(
        "TckrSymb"
    ):

        group = group.copy()

        group["Date"] = pd.to_datetime(
            group["Date"],
            errors="coerce",
        )

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

                pattern = "Contraction"

            elif (
                last_two_average
                >
                first_two_average * 1.20
            ):

                pattern = "Expansion"

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
# PRICE + VOLUME RELATIONSHIP
#
# V8 SOURCE-OF-TRUTH RULE
#
# Price UP   + Volume UP   = Strong Bullish
# Price UP   + Volume DOWN = Weak / Caution
# Price DOWN + Volume UP   = Selling / Distribution
# Price DOWN + Volume DOWN = Normal Pullback
# Price FLAT + Volume UP   = Possible Accumulation / Event
#
# This classification is NOT a BUY signal.
# ============================================================

def calculate_price_volume_relationship(
    candidates
):

    print("")
    print("=" * 60)
    print("PRICE + VOLUME RELATIONSHIP")
    print("=" * 60)

    result = candidates.copy()

    # --------------------------------------------------------
    # PRICE CHANGE %
    # --------------------------------------------------------

    result[
        "PriceChangePct"
    ] = (
        (
            result["ClsPric"]
            -
            result["PrvsClsgPric"]
        )
        /
        result["PrvsClsgPric"]
        *
        100
    )

    # --------------------------------------------------------
    # PRICE DIRECTION
    #
    # Flat = absolute change below 0.10%
    # --------------------------------------------------------

    result[
        "PriceDirection"
    ] = "Flat"

    result.loc[
        result["PriceChangePct"] > 0.10,
        "PriceDirection"
    ] = "Up"

    result.loc[
        result["PriceChangePct"] < -0.10,
        "PriceDirection"
    ] = "Down"

    # --------------------------------------------------------
    # VOLUME DIRECTION
    #
    # Current volume compared with 20D average.
    # Above average = Up
    # Below average = Down
    # --------------------------------------------------------

    result[
        "VolumeDirection"
    ] = "Down"

    result.loc[
        result["TtlTradgVol"]
        >
        result["AVG_20D_VOLUME"],
        "VolumeDirection"
    ] = "Up"

    # --------------------------------------------------------
    # RELATIONSHIP CLASSIFICATION
    # --------------------------------------------------------

    result[
        "PriceVolumeRelationship"
    ] = "Unknown"

    # Price UP + Volume UP
    result.loc[
        (
            result["PriceDirection"] == "Up"
        )
        &
        (
            result["VolumeDirection"] == "Up"
        ),
        "PriceVolumeRelationship"
    ] = "Strong Bullish"

    # Price UP + Volume DOWN
    result.loc[
        (
            result["PriceDirection"] == "Up"
        )
        &
        (
            result["VolumeDirection"] == "Down"
        ),
        "PriceVolumeRelationship"
    ] = "Weak / Caution"

    # Price DOWN + Volume UP
    result.loc[
        (
            result["PriceDirection"] == "Down"
        )
        &
        (
            result["VolumeDirection"] == "Up"
        ),
        "PriceVolumeRelationship"
    ] = "Selling / Distribution"

    # Price DOWN + Volume DOWN
    result.loc[
        (
            result["PriceDirection"] == "Down"
        )
        &
        (
            result["VolumeDirection"] == "Down"
        ),
        "PriceVolumeRelationship"
    ] = "Normal Pullback"

    # Price FLAT + Volume UP
    result.loc[
        (
            result["PriceDirection"] == "Flat"
        )
        &
        (
            result["VolumeDirection"] == "Up"
        ),
        "PriceVolumeRelationship"
    ] = "Possible Accumulation / Event"

    # Price FLAT + Volume DOWN
    result.loc[
        (
            result["PriceDirection"] == "Flat"
        )
        &
        (
            result["VolumeDirection"] == "Down"
        ),
        "PriceVolumeRelationship"
    ] = "Low Activity / Neutral"

    return result


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
# TELEGRAM MESSAGE
# ============================================================

def create_telegram_message(
    result,
    current_date
):

    lines = []

    lines.append(
        "📊 NSE V8 EOD VOLUME + PRICE ANALYSIS"
    )

    lines.append(
        f"📅 {current_date:%d-%b-%Y}"
    )

    lines.append("")

    lines.append(
        "Volume + RVOL + 5D + Price/Volume"
    )

    lines.append(
        "⚠️ Screening layer only"
    )

    lines.append(
        "❌ NOT a BUY signal"
    )

    lines.append("")

    for rank, (_, row) in enumerate(
        result.head(20).iterrows(),
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

        price_change = float(
            row["PriceChangePct"]
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

        relationship = str(
            row["PriceVolumeRelationship"]
        )

        rule_status = (
            "PASS"
            if bool(
                row["60PctRule"]
            )
            else "NO"
        )

        lines.append(
            f"{rank}. {symbol}"
        )

        lines.append(
            f"Price: {price_change:+.2f}%"
        )

        lines.append(
            f"Vol: {volume:,}"
        )

        lines.append(
            f"20D Avg: {average:,}"
        )

        lines.append(
            f"RVOL: {rvol:.2f}x "
            f"({get_rvol_classification(rvol)})"
        )

        lines.append(
            f"5D Low Vol: "
            f"{low_days}/5 "
            f"({low_pct:.0f}%)"
        )

        lines.append(
            f"5D Pattern: {pattern}"
        )

        lines.append(
            f"Price + Volume: {relationship}"
        )

        lines.append(
            f"60% Rule: {rule_status}"
        )

        lines.append("")

    return "\n".join(lines)


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
        "EOD VOLUME + 20D AVG + RVOL + 5D + PRICE/VOLUME"
    )
    print("=" * 60)

    print(
        "Python script started successfully."
    )

    # --------------------------------------------------------
    # STEP 1
    # FIND LATEST EOD BHAVCOPY
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

        print(
            "ERROR: No NSE Bhavcopy found."
        )

        return

    # --------------------------------------------------------
    # STEP 2
    # CURRENT EOD DATA
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
            "ERROR: Current EOD data failed."
        )

        return

    print(
        "Current valid symbols:",
        len(current_data),
    )

    # --------------------------------------------------------
    # STEP 3
    # PREVIOUS 20 DAYS
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

        print(
            "ERROR: Could not collect "
            "20 trading days."
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
            "ERROR: 20D average failed."
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
            "ERROR: RVOL calculation failed."
        )

        return

    # --------------------------------------------------------
    # STEP 6
    # 5-DAY VOLUME
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

    if (
        result is None
        or result.empty
    ):

        print(
            "ERROR: 5-day analysis failed."
        )

        return

    # --------------------------------------------------------
    # STEP 7
    # PRICE + VOLUME RELATIONSHIP
    # --------------------------------------------------------

    print("")
    print(
        "STEP 7: Calculating "
        "Price + Volume Relationship..."
    )

    result = calculate_price_volume_relationship(
        result
    )

    if (
        result is None
        or result.empty
    ):

        print(
            "ERROR: Price + Volume "
            "analysis failed."
        )

        return

    # --------------------------------------------------------
    # TOP 20
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print(
        "TOP 20 RVOL + 5D + PRICE/VOLUME"
    )
    print("=" * 60)

    for rank, (_, row) in enumerate(
        result.head(20).iterrows(),
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

        price_change = float(
            row["PriceChangePct"]
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

        relationship = str(
            row["PriceVolumeRelationship"]
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
            f"Price={price_change:+.2f}% | "
            f"Vol={volume:,} | "
            f"20D={average:,} | "
            f"RVOL={rvol:.2f}x | "
            f"Low5D={low_days}/5 "
            f"({low_pct:.0f}%) | "
            f"Pattern={pattern:<12} | "
            f"P+V={relationship:<28} | "
            f"60%={rule_status}"
        )

    # --------------------------------------------------------
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
    # COMPLETE
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print(
        "MODULE A COMPLETED"
    )
    print(
        "VOLUME + RVOL + 5D + PRICE/VOLUME"
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
# ============================================================

if __name__ == "__main__":
    main()
