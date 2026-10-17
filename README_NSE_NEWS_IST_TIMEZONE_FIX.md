# NSE V8 — Official News Timestamp Timezone Fix

## Root cause found in the latest GitHub Actions log
The NSE Financial Filings RSS feed returned 20 records with timestamp strings such as `16-Oct-2026 21:49:19`. The current `_published()` parser treated timezone-naive timestamps as UTC. For NSE exchange timestamps, that incorrectly shifts the time by 5 hours 30 minutes and can classify an in-window filing as after the approved EOD window. The log therefore showed all 20 records as `after_window=20`.

## Files to replace
- `news_catalyst.py`
- `test_v8_regression.py`

Both are full replacement files. Keep all other project files unchanged.

## Fix
- Interpret timezone-naive NSE-style timestamps as Asia/Kolkata local time.
- Normalize the resulting timestamp to UTC before comparisons.
- Add a regression test asserting `16-Oct-2026 21:49:19` IST becomes `2026-10-16T16:19:19+00:00`, which is before the approved 22:00 IST EOD news-window cutoff.
- Preserve the official-source gate, issuer matching, and `WAIT_FOR_DATA` behavior when evidence is missing.

## Local validation
- Python compile: PASS
- V8 regression tests: 22/22 PASS

## Important limitation
This fixes a verified timestamp-parsing bug. It does not guarantee any specific candidate will receive an official catalyst. After replacing the files in GitHub, rerun the workflow and inspect `OFFICIAL_FEED_SUMMARY`, `OFFICIAL_ISSUER_MATCH`, and `FINAL_SUMMARY`. Secondary sources must remain `UNVERIFIED`; no BUY signal should be inferred from this patch alone.
