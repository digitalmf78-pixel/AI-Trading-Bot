NSE V8.0 — Nifty Indices Historical Endpoint Route Fix
Date: 20-Oct-2026

WHY THIS PATCH
The latest GitHub Actions log (logs_106806438508.zip) shows:
- NSE historical API: HTTP 200, but data=[] for six missing indices.
- Nifty Indices historical fallback requested the legacy route:
  /Backpage.aspx/getHistoricaldatatabletoString
- That route redirected (302) to Sitefinity/Login and returned HTML, not JSON.
- The daily NSE archive still had exact-date data for 17/23 configured indices.
- The live all-indices snapshot was correctly skipped because the scanner's as-of date was 19-Oct while the run was on 20-Oct. Do not stamp 20-Oct prices onto 19-Oct.

CHANGE
- Change the Nifty Indices historical POST route to:
  https://www.niftyindices.com/BackPage/getHistoricaldatatabletoString
- Use MM/DD/YYYY dates for this route.
- Keep strict validation of returned index date and positive Close; no inferred or fabricated historical values.
- Update regression test to assert the exact endpoint and date format.

FILES
Replace only:
1. sector_data.py
2. test_nse_official_index_api.py

TESTS RUN LOCALLY
- Python compile check: PASS
- V8 regression tests: 27/27 PASS
- Sector/News/Cache/API unittest suite: 38 tests PASS
- News parser pytest suite: 4/4 PASS
- Focused official-index API test file: 7/7 PASS

LIMITATION
These tests validate code and mocked response parsing. They do not prove the live Nifty Indices endpoint will allow GitHub Actions requests. After commit, run the workflow and check [SECTOR][NIFTYINDICES] logs, HTTP status/final URL, accepted_rows, and exact_date_sectors. If the new route still redirects or returns an empty list, keep the sector WAIT_FOR_DATA and inspect the response; do not guess a Close.

APPLY
1. Open the main repository digitalmf78-pixel/AI-Trading-Bot.
2. Replace the complete sector_data.py.
3. Replace the complete test_nse_official_index_api.py.
4. Commit and manually run NSE Data Test.

UNCHANGED
No News/Announcement logic changed in this patch. Once Sector History is confirmed working, the next task is News/Announcement matching. Delivery >=60% on each of the previous 5 valid sessions, liquidity >= INR 5 crore over 20 sessions, Volume/RVOL/Top 20 and all other V8 rules are unchanged. The separate Delivery Watchlist project is not included.
