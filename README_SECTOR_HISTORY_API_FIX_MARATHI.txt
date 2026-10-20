NSE V8.0 — Sector History API Fix (20-Oct-2026)

ROOT CAUSE FOUND
The latest uploaded repository still called the legacy NiftyIndices ASP.NET endpoint:
https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString
The latest Actions log shows this endpoint redirecting to a Sitefinity login page (HTTP 302 chain), so the response is HTML rather than historical JSON. The repository did NOT contain the claimed NSE official API fallback, despite earlier README notes.

FIX INCLUDED
1. sector_data.py now tries NSE's official GET endpoint first for sectors missing from the exact-date daily archive:
   https://www.nseindia.com/api/historicalOR/indicesHistory
2. Query parameters use indexType, from, to with DD-MM-YYYY dates.
3. Reads data.indexCloseOnlineRecords and validates EOD_INDEX_NAME, EOD_TIMESTAMP, and EOD_CLOSE_INDEX_VAL.
4. Only exact/explicit index-name aliases are accepted. Wrong index identity, invalid dates, non-positive closes, HTML responses and HTTP errors are rejected.
5. If the official NSE API still has missing sectors, the existing legacy NiftyIndices fallback is tried afterwards as a secondary attempt. Missing data remains missing; no synthetic close is generated.
6. test_nse_official_index_api.py now tests the actual official NSE endpoint contract.

FILES IN THIS PATCH
- sector_data.py (complete replacement)
- test_nse_official_index_api.py (complete replacement)

APPLY
1. Open the main repository digitalmf78-pixel/AI-Trading-Bot.
2. Replace sector_data.py with this ZIP's sector_data.py.
3. Replace test_nse_official_index_api.py with this ZIP's test file.
4. Commit, then manually run NSE Data Test.
5. Upload the new Actions log and report artifact for verification.

LOCAL VALIDATION PERFORMED
- Python compilation: PASS
- test_nse_official_index_api.py + test_niftyindices_history_bootstrap.py + sector/news/cache-related tests: 42/42 PASS
- test_v8_regression.py: 27/27 PASS
- test_news_catalyst_parser.py: 4/4 PASS
These are local/mocked tests; live GitHub Actions access to NSE is not proven until the next run.

UNCHANGED
- Delivery threshold: each of the last 5 valid distinct sessions must be >=60.00%; exactly 60.00% passes.
- Liquidity threshold: 20-session Average Daily Traded Value >= INR 5 crore.
- Volume/RVOL/Top 20, technical/risk-reward, News/Catalyst business logic are not changed by this patch.
- No separate Delivery Watchlist project files are included.
