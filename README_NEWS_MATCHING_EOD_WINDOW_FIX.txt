NSE V8 NEWS MATCHING + 10 PM IST WINDOW FIX

Files to replace in the GitHub repository:
1. news_catalyst.py                 (complete replacement)
2. test_news_catalyst_matching.py   (complete replacement; adds focused tests)
3. test_news_rss_diagnostics.py     (include/replace so RSS helper tests match the module)

What this patch fixes:
- Secondary Google News discovery no longer requires both the registered company name and ticker to appear together in the same search query. It runs separate queries, then applies strict issuer matching to the returned article text.
- Secondary matching checks headline + description, while still requiring a distinctive registered company name or explicit ticker form. A broad query alone never creates evidence.
- Bounded diagnostics show each query and up to five unmatched headlines, so logs distinguish missing coverage from matching failure.
- Enforces the approved news-window end: no evidence later than 22:00 IST on the EOD date is accepted.
- Adds namespace-safe, bounded _rss_debug_fields helper required by the existing RSS diagnostics tests.
- Keeps official NSE evidence as primary and Google News as secondary; it does not invent news or promote secondary coverage to primary.

Rules preserved:
- AvgDelivery5D >= 60.00% passes; below 60.00% rejects; insufficient valid sessions stays WAIT_FOR_DATA.
- No Sector mapping is changed.
- No 3+1 confirmation, Risk/Reward, or BUY rules are changed.
- Missing news remains NO_DATA / WAIT_FOR_DATA.

Validation completed locally:
- Focused news + V8 regression tests: 41 passed.
- Full repository test set: 60 passed, 5 failed in existing unrelated sector tests (old API/function expectation and AMJLAND mapping). Do not change those as part of this news patch.
- `pytest` without selecting test_*.py also tries to import nifty500_api_test.py, which performs a live NSE network request and fails in this offline environment. That is not a news-module failure.

GitHub steps:
1. Open news_catalyst.py and replace the entire file.
2. Replace test_news_catalyst_matching.py and test_news_rss_diagnostics.py with the ZIP copies.
3. Commit the three files.
4. Run Actions workflows: News Matching and Parser Tests; NSE V8 News RSS Field Diagnostics; then the main NSE Data Test.
5. Upload the new logs ZIP for review. GitHub Actions has not yet verified this patch.
