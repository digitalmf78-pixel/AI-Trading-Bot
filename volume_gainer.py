import io
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests


NSE_URL = "https://www.nseindia.com"
BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/CM/"
    "sec_bhavdata_full_{date}.csv"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/csv,*/*",
    "Referer": "https://www.nseindia.com/",
}


def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)

    response = session.get(NSE_URL, timeout=30)
    response.raise_for_status()

    return session


def download_bhavcopy(session, date):
    date_str = date.strftime("%d%m%Y")
    url = BHAVCOPY_URL.format(date=date_str)

    response = session.get(url, timeout=30)

    if response.status_code == 200 and len(response.content) > 1000:
        return response.content

    return None


def find_latest_bhavcopy(session):
    today = datetime.now().date()

    for days_back in range(0, 10):
        check_date = today - timedelta(days=days_back)

        data = download_bhavcopy(session, check_date)

        if data:
            print(f"Bhavcopy found: {check_date}")
            return check_date, data

    raise RuntimeError("Could not find recent NSE Bhavcopy.")


def calculate_volume_gainers(df):
    df.columns = [str(col).strip().upper() for col in df.columns]

    required = ["SYMBOL", "CLOSE_PRICE", "TTL_TRD_QNTY"]

    for column in required:
        if column not in df.columns:
            raise RuntimeError(
                f"Required column missing: {column}\n"
                f"Available columns: {list(df.columns)}"
            )

    df["CLOSE_PRICE"] = pd.to_numeric(
        df["CLOSE_PRICE"], errors="coerce"
    )

    df["TTL_TRD_QNTY"] = pd.to_numeric(
        df["TTL_TRD_QNTY"], errors="coerce"
    )

    df = df.dropna(
        subset=["SYMBOL", "CLOSE_PRICE", "TTL_TRD_QNTY"]
    )

    # Exclude ETFs/index-like instruments where appropriate.
    df = df[df["SYMBOL"].str.len() > 0]

    result = df[
        ["SYMBOL", "CLOSE_PRICE", "TTL_TRD_QNTY"]
    ].copy()

    result = result.sort_values(
        "TTL_TRD_QNTY",
        ascending=False
    )

    result["VOLUME_RANK"] = range(1, len(result) + 1)

    return result.head(20)


def main():
    print("Starting NSE EOD Volume Gainer test...")

    session = get_session()

    date, raw_data = find_latest_bhavcopy(session)

    df = pd.read_csv(io.BytesIO(raw_data))

    print(f"Trading date: {date}")
    print(f"Rows received: {len(df)}")

    gainers = calculate_volume_gainers(df)

    print("\nTop 20 volume stocks:")
    print(
        gainers.to_string(index=False)
    )


if __name__ == "__main__":
    main()
