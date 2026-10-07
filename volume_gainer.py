import requests
from datetime import datetime

URL = "https://www.nseindia.com/api/live-analysis-variations?index=gainers&type=FOSec"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/market-data/volume-gainers-spurts"
}

def main():
    session = requests.Session()

    # First open NSE website to establish session cookies
    session.get(
        "https://www.nseindia.com/market-data/volume-gainers-spurts",
        headers=HEADERS,
        timeout=30
    )

    response = session.get(
        URL,
        headers=HEADERS,
        timeout=30
    )

    print("Status Code:", response.status_code)

    if response.status_code != 200:
        print("NSE request failed")
        print(response.text[:500])
        return

    data = response.json()

    print("NSE response received successfully")
    print("Response keys:", list(data.keys()))

    print("\nTop records:")

    records = data.get("data", [])

    for i, stock in enumerate(records[:10], start=1):
        symbol = stock.get("symbol", "N/A")
        volume = stock.get("volume", stock.get("totalTradedVolume", "N/A"))

        print(f"{i}. {symbol} | Volume: {volume}")

if __name__ == "__main__":
    main()
