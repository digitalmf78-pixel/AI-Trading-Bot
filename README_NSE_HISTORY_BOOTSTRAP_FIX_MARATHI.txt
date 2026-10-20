NSE V8.0 — Historical Index API Session Bootstrap Fix
Date: 20-Oct-2026

LATEST LOG FINDING
The latest GitHub Actions log shows:
- NSE historical API session bootstrap returned HTTP 200 for /report-detail/eq_security.
- Requests to /api/historicalOR/indicesHistory returned {"data": []} for all six missing sectors.
- The code was initializing cookies from the equity-security report page, not the historical-index page. HTTP 200 alone did not establish a valid historical-index session.

CHANGE
- Bootstrap now uses https://www.nseindia.com/reports-indices-historical-index-data.
- Historical API calls use that page as Referer and explicitly send the NSE Origin header.
- The response parser and exact-date/name/positive-close validation remain unchanged.
- No missing closes are inferred or fabricated.

FILES
1. sector_data.py — full replacement
2. test_nse_official_index_api.py — full replacement
3. README_NSE_HISTORY_BOOTSTRAP_FIX_MARATHI.txt

APPLY
1. Open digitalmf78-pixel/AI-Trading-Bot.
2. Replace sector_data.py and test_nse_official_index_api.py with these files.
3. Commit and run NSE Data Test manually.
4. Inspect [SECTOR][NSE_HISTORY] logs and exact_date_sectors count.

LOCAL TESTS
Tests validate session-bootstrap URL/headers and response parsing with fixtures. They do not prove live NSE API access; the next GitHub Actions run must confirm that the live endpoint returns rows.

UNCHANGED
Daily delivery must be >=60% on each of the last 5 valid distinct sessions. Average daily traded value over 20 sessions must be >= ₹5 crore. Volume/RVOL/Top 20 and all other V8 business logic are unchanged. No separate Delivery Watchlist files are included.
