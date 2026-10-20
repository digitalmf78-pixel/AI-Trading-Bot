NSE V8.0 — Sector History Fallback Chain Fix
Date: 20-Oct-2026

WHY THE LAST RUN STILL FAILED
The uploaded log confirms:
- Official NSE daily archive: 17/23 exact-date sector index closes.
- NSE historicalOR/indicesHistory: HTTP 200, but data=[] for the six missing sectors.
- The old Nifty Indices fallback was not part of the live refresh path in the last patched run.
- Unit tests passed because they use controlled/mock responses; that does not prove live endpoint coverage.

WHAT THIS PATCH CHANGES
1. Keeps the official NSE daily archive as the primary source.
2. Tries NSE historicalOR/indicesHistory for the missing exact-date sectors.
3. If that returns no exact-date closes, tries the official Nifty Indices historical-data endpoint again, bootstrapping the older historical-data route first and current /reports landing page second. The Referer points at the current /reports page.
4. If both history APIs still have no rows, tries NSE /api/allIndices only as a forward-only EOD snapshot:
   - only when the Bhavcopy as-of date equals today's IST date;
   - only at/after 15:45 IST;
   - only for exact matching official index names and positive values;
   - never assigns today's value to a prior date.
5. Existing history is merged and retained. No synthetic or estimated closes are generated.

IMPORTANT LIMITATION
If NSE's historical endpoints do not publish the six indices and /api/allIndices does not return them, the code will keep them missing and log the reason. This patch cannot manufacture missing historical data. The snapshot fallback starts collecting daily values going forward; a full 20-session Sector Strength history for a previously absent index will only become available after enough valid daily closes have accumulated, unless the official historical endpoint starts returning the back-history.

FILES TO REPLACE
- sector_data.py
- test_nse_official_index_api.py

Apply both files to the main repository digitalmf78-pixel/AI-Trading-Bot. Do not replace news_catalyst.py, delivery_filter.py, volume_gainer.py, or the separate Delivery Watchlist project.

TESTS RUN LOCALLY
- Python compilation: PASS
- V8 regression tests: 27/27 PASS
- Sector/News/Cache/API unittest group: 41/41 PASS
- News parser pytest: 4/4 PASS

These tests validate code and mocked response handling, not live NSE access. After committing, run NSE Data Test and inspect:
[SECTOR][NSE_HISTORY_API]
[SECTOR][NIFTYINDICES]
[SECTOR][NSE_ALL_INDICES]
[SECTOR] Combined official history exact-date sectors=
