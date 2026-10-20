NSE V8.0 — OFFICIAL SECTOR INDEX HISTORY FALLBACK PATCH
Date: 20-Oct-2026

WHAT WAS FOUND IN THE CURRENT REPOSITORY
- sector_data.py's primary source is NSE's daily all-indices CSV archive.
- When exact-date closes are missing, the code only tried the older NiftyIndices Backpage.aspx endpoint.
- That legacy endpoint has repeatedly returned HTML/login responses in GitHub Actions.
- The repository's README described an official NSE historical-index API fallback, but the current sector_data.py did not actually call that API. This patch adds it.

FILES IN THIS PATCH
1. sector_data.py — complete replacement.
2. test_nse_official_index_api.py — complete replacement with tests for the current NSE API plus existing legacy fallback tests.
3. README_SECTOR_HISTORY_API_PATCH_MARATHI.txt — these instructions.

WHAT CHANGES
- For sectors missing an exact-date close from the official daily archive, first query:
  https://www.nseindia.com/api/historicalOR/indicesHistory
- The session is warmed with the official NSE historical index page.
- Query uses indexType/from/to; requested dates are limited to the latest 75 calendar days.
- Accept only a valid EOD_TIMESTAMP, positive EOD_CLOSE_INDEX_VAL, and an explicit expected EOD_INDEX_NAME for that sector.
- Known response-name aliases are explicitly listed in code; no fuzzy or substring matching.
- If the current NSE API does not return valid data, the legacy NiftyIndices fallback is still attempted for remaining missing sectors.
- Missing data stays missing; no synthetic or cross-index close values are created.
- No changes are made to news_catalyst.py because its current issuer-specific matching and API-coverage status logic is already strict and existing regression tests pass. News source availability still needs to be verified by the next live GitHub Actions run.

LOCAL VALIDATION
- Python compilation for sector_data.py, news_catalyst.py, v8_layers_14_41.py, delivery_filter.py, liquidity_filter.py: PASS.
- Sector/News/Cache/API unittest suite: 37/37 PASS.
- News parser pytest suite: 4/4 PASS.
- V8 regression / delivery / liquidity / ETF mapping / structural resistance suite: run separately before commit; see results from the current local validation context.
- Live NSE endpoint access was NOT tested in this local environment. GitHub Actions must confirm it returns JSON and exact-date sector coverage improves.

APPLY
1. Open the main repository: digitalmf78-pixel/AI-Trading-Bot.
2. Replace sector_data.py with the file in this ZIP.
3. Replace test_nse_official_index_api.py with the file in this ZIP.
4. Commit the two files.
5. Manually run the NSE Data Test workflow.
6. In the new Actions log, look for:
   [SECTOR][NSE_HISTORY] SESSION_BOOTSTRAP
   [SECTOR][NSE_HISTORY] sector=...
   [SECTOR] Combined official index sources exact-date sectors=...
7. Upload the fresh Actions log/artifact for review.

UNCHANGED RULES
- Every one of the previous 5 valid distinct trading sessions must have Delivery % >= 60.00%; exactly 60.00% passes.
- 20-session Average Daily Traded Value >= INR 5 crore.
- Volume/RVOL/Top 20 and all other V8 selection layers remain unchanged.
- The separate Delivery Watchlist project is not included or modified.
