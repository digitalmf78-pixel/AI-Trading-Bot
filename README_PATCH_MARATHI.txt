NSE V8 — 5-Day News + Upcoming Corporate Events Patch
Date: 2026-10-20

This patch was rebuilt against the newly uploaded AI-Trading-Bot-main (1)(4).zip.

Files included:
1. news_catalyst.py — complete replacement
2. test_upcoming_corporate_events.py — new tests
3. .github/workflows/nse-test-scheduled.yml — updated workflow to run the new tests
4. README_PATCH_MARATHI.txt — Marathi instructions

Behavior:
- Existing historical News/Catalyst window remains five calendar dates:
  * EOD: 00:00 IST on EOD date minus 4 days through 22:00 IST on EOD date.
  * PREMARKET: today and previous four calendar dates through 09:15 IST.
- The official NSE issuer announcement API is queried with a 90-day publication lookback for upcoming-event discovery.
- Normal historical news rows still pass the existing five-calendar-day cutoff. The wider 90-day lookback does not widen historical News/Catalyst evidence.
- Upcoming event extraction accepts only an explicit future date written in the official filing text; it never substitutes the announcement date for the event date.
- Event output is written to outputs/v8_upcoming_corporate_events.csv, with one or more rows/statuses per shortlisted symbol only.
- If official coverage is unavailable, the event status is WAIT_FOR_DATA.
- If an official relevant announcement is found but no explicit future date is parsed, status is DATE_NOT_FOUND_OR_NO_FUTURE_DATE. This is not marked as a confirmed upcoming event.
- A successful API response with no relevant upcoming event is marked NO_MATCHING_UPCOMING_EVENT_FOUND.
- Existing Delivery, Liquidity, Main Board, Sector, Technical, 3+1, Risk/Reward and Final EOD gates are not changed.
- The separate Delivery Watchlist project is not changed.

Apply:
1. Replace repository news_catalyst.py with the included full file.
2. Add test_upcoming_corporate_events.py at repository root.
3. Replace .github/workflows/nse-test-scheduled.yml with the included workflow file.
4. Commit/push, then run NSE Data Test. Inspect artifact outputs/v8_upcoming_corporate_events.csv and logs.
5. Do not treat local mock tests as proof that live NSE coverage is available.

Local verification against this uploaded repository:
- Python compile checks: PASS
- Main Board tests: 3 PASS
- V8 regression tests: 27 PASS
- Existing Sector/News/Cache unittest modules: 39 PASS
- News parser + upcoming-event tests: 9 PASS
- New upcoming-event tests: 5 PASS
- Total across the workflow checks above: all passed (overlapping modules are counted in their individual commands; do not sum across overlapping test commands).
