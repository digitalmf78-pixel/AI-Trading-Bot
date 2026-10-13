import sys
import requests

url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/"
}

try:
    response = requests.get(url, headers=headers, timeout=30)
    print("Status Code:", response.status_code)

    if response.status_code != 200:
        print("Download failed")
        print(response.text[:500])
        sys.exit(1)

    try:
        data = response.json()
    except ValueError as exc:
        print(f"Download failed: response was not valid JSON: {exc}")
        sys.exit(1)

    stocks = data.get("data", [])
    if not isinstance(stocks, list) or not stocks:
        print("Download failed: response contains no NIFTY 500 stock records")
        sys.exit(1)

    print("Download successful")
    print("Stocks received:", len(stocks))
    print("\nFirst stock:")
    print(stocks[0])

except requests.RequestException as exc:
    print(f"Download failed: {exc}")
    sys.exit(1)
