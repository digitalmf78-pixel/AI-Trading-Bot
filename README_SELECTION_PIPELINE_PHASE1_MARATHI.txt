NSE V8.0 — Selection Pipeline Phase 1

Repository: digitalmf78-pixel/AI-Trading-Bot
Source ZIP reviewed: AI-Trading-Bot-main(6).zip

WHAT CHANGED
1. Kept the five-session actual NSE Delivery % gate before RVOL ranking.
   - Each of the five distinct valid sessions must have DELIV_PER >= 60.00%.
   - Exactly 60.00% passes; any day below 60.00% rejects.
   - Missing/incomplete five-session data remains WAIT_FOR_DATA.
2. Moved the existing liquidity filter so it runs AFTER the RVOL Top 20 selection and BEFORE technical analysis.
3. Kept the existing liquidity rule unchanged: 20 prior valid sessions' average traded value (TtlTrfVal) must be >= INR 5 crore/day; missing data fails closed to WAIT_FOR_DATA.
4. Added a regression test for the required ordering and added the relevant tests to the main NSE Data Test workflow.

EXPECTED ORDER NOW
NSE EOD -> official Main Board universe -> five daily Delivery >=60% -> volume history/RVOL -> RVOL Top 20 -> Liquidity -> Price/Volume and technical analysis -> existing sector/news/market regime -> risk/reward -> final EOD watchlist -> next-day validation.

SCOPE LIMIT
This patch only fixes the position of the existing liquidity filter in the main scanner. Fundamental Strength and Operating Cash Flow/Free Cash Flow stages are NOT yet implemented in the main scanner. Those must be added as a separate, audited phase with sourced financial data and explicit thresholds; do not mark them PASS from missing data or infer financials.

FILES INCLUDED (replace each file at the matching repository path)
- volume_gainer.py
- test_liquidity_filter.py
- test_selection_pipeline_order.py (new)
- .github/workflows/nse-test-scheduled.yml

LOCAL VALIDATION
- Python compile checks: PASS
- Main Board tests: 3 passed
- Delivery/Liquidity/Selection-order tests: 12 passed
- V8 regression tests: 27/27 PASS
- Sector/news/cache unittest group: PASS
- News parser tests: 4 passed
- Upcoming corporate event tests: 5 passed

These are local tests on the uploaded ZIP contents. This patch has NOT been applied to GitHub and a live GitHub Actions run has NOT yet verified it.
