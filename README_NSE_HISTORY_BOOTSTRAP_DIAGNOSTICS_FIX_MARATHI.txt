NSE V8.0 — Historical Index API Session Bootstrap + Diagnostics Fix
Date: 20-Oct-2026

WHY THIS PATCH
The uploaded GitHub Actions log for run logs_106799743248.zip shows:
- [SECTOR][NSE_HISTORY_API] SESSION_BOOTSTRAP status=403 for https://www.nseindia.com/
- The six missing sector requests then logged EMPTY_RECORDS, but did not include enough response metadata to tell whether NSE returned a genuinely empty dataset or a blocked/filtered payload.

CHANGE
1. Bootstrap first against https://www.nseindia.com/report-detail/eq_security, which is used by documented NSE client implementations for session establishment.
2. If that page does not return HTTP 200 HTML, try the Historical Index Data page, then the homepage as last fallback.
3. Keep the official endpoint GET /api/historicalOR/indicesHistory and the indexType/from/to parameters unchanged.
4. When API rows are empty or invalid, log HTTP status, final URL, content type, top-level keys, nested data keys, and cookie count. This helps distinguish true no-data from access/session issues.
5. Preserve strict index name, date and positive-close validation. No values are synthesized.

FILES
- sector_data.py (full replacement)
- test_nse_official_index_api.py (full replacement)
- README_NSE_HISTORY_BOOTSTRAP_DIAGNOSTICS_FIX_MARATHI.txt
- TEST_RESULTS_NSE_HISTORY_BOOTSTRAP_DIAGNOSTICS_FIX.txt

LOCAL TESTS
- Python compilation: PASS
- unittest suite (official index API, NiftyIndices fallback, cache reconciliation, Sector/News and issuer matching): 38/38 PASS
- V8 regression tests: 27/27 PASS
- News parser pytest: 4/4 PASS
These validate local parsing and mocked request behavior, not live NSE availability.

APPLY
1. Open main repository digitalmf78-pixel/AI-Trading-Bot.
2. Replace sector_data.py with this ZIP's sector_data.py.
3. Replace test_nse_official_index_api.py with this ZIP's test file.
4. Add the README and test-results text file.
5. Commit and manually run NSE Data Test.
6. In the log, inspect [SECTOR][NSE_HISTORY_API] SESSION_BOOTSTRAP and EMPTY_RECORDS/INVALID_SCHEMA lines. They now include the response details needed to identify the remaining live issue.

UNCHANGED
No delivery, liquidity, volume/RVOL, Top 20, News/Catalyst business logic or separate Delivery Watchlist files are changed. Delivery remains >=60% on each of the previous five valid distinct sessions; 20-session average daily traded value remains >= ₹5 crore.
