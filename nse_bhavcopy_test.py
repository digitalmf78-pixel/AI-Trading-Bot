import requests
from datetime import datetime

url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/"
}

response = requests.get(url, headers=headers, timeout=30)

print("Status Code:", response.status_code)

if response.status_code == 200:
    data = response.json()
    stocks = data.get("data", [])

    print("Download successful")
    print("Stocks received:", len(stocks))

    if stocks:
        print("\nFirst stock:")
        print(stocks[0])
else:
    print("Download failed")
    print(response.text[:500])
