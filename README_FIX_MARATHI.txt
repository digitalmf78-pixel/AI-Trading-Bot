NSE V8.0 — SECTOR ARCHIVE DIAGNOSTICS + PREMARKET NEWS COVERAGE FIX
Date: 20-Oct-2026

WHAT THE LATEST LOG ACTUALLY SHOWED
- Python compilation and the scanner ran successfully.
- 27 V8 regression tests passed, 31 Sector/News/Cache unit tests passed, and 4 parser tests passed.
- Sector archive had exact-date closes for 17/23 tracked indices. The prior log did not enumerate all missing names.
- Official global RSS contained in-window financial filing records, but those records were for unrelated issuers. Candidate-specific NSE announcement API returned successful empty results for some candidates and actual records for others.

CHANGES IN THIS PATCH
1. sector_data.py
   - Adds a diagnostic line for the official NSE daily index archive on the EOD date:
     [SECTOR][ARCHIVE][INDEX_NAME_DIAGNOSTIC]
   - It reports the configured sector names absent from the archive and samples unmatched Nifty index names.
   - This is diagnostic only. It does NOT invent prices, alias unrelated indices, or mark missing sectors as PASS.

2. news_catalyst.py
   - Fixes PREMARKET status classification.
   - Previously, any in-window item in the global NSE RSS could count as coverage for every candidate, even if it was another company's filing.
   - Now a candidate without a matching official item requires a successful issuer-filtered NSE announcement API response before it can be classified NO_NEWS_FOUND or SECONDARY_ONLY_UNVERIFIED. If that API fails, status remains WAIT_FOR_DATA.
   - A successful empty issuer API response is still valid coverage. An official matching item still becomes OFFICIAL_NEWS_FOUND.

3. test_sector_news_final_fix.py
   - Adds regression tests for the candidate-specific PREMARKET coverage rule.

4. .github/workflows/nse-test-scheduled.yml
   - Includes pytest and the existing V8, Sector, News, cache and parser tests before running the scanner.
   - PREMARKET schedule is 08:00 IST weekdays; EOD is 22:10 IST weekdays.

LOCAL TEST RESULTS
- Python compile: PASS
- V8 regression suite: 27/27 PASS
- Unit suite (Sector/News/cache/API): 34/34 PASS (includes the 3 new coverage-status tests)
- pytest parser suite: 4/4 PASS

APPLY
1. Open the MAIN repository: digitalmf78-pixel/AI-Trading-Bot.
2. Replace the full contents of sector_data.py and news_catalyst.py with the files in this ZIP.
3. Replace test_sector_news_final_fix.py with the supplied file.
4. Replace .github/workflows/nse-test-scheduled.yml with the supplied file.
5. Commit and manually run NSE Data Test once with EOD.
6. Send the new log/artifact. The new diagnostic line will name the missing official archive indices so the next change can be evidence-based.

UNCHANGED / SAFETY
- Each of the last five valid distinct trading sessions must individually have Delivery >= 60.00%; exactly 60.00% passes.
- 20-session Average Daily Traded Value must be >= ₹5 crore.
- Volume/RVOL/Top-20 and the other V8 decision logic are not changed.
- Missing sector or news evidence remains missing/WAIT_FOR_DATA; no guessed data is added.
- Do not change the separate Delivery Watchlist project.
