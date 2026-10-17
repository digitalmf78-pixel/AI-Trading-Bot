# NSE V8 — Five-Calendar-Day News + Premarket Check Patch

## Goal

Add the approved news window without changing the delivery, volume, sector, technical, or 3+1 rules:

- **EOD scan:** five calendar dates inclusive, from 00:00 IST on EOD date minus four days through 22:00 IST on the EOD date.
- **Premarket scan:** rolling five calendar dates inclusive (today plus the previous four dates), through 09:15 IST on the scan date. This includes weekend announcements before Monday's session.
- **Schedule:** keep the existing weekday EOD run at 22:10 IST and add a weekday premarket run at 09:05 IST.
- **Evidence:** official NSE/company evidence remains primary; secondary stories remain unverified. `NO_NEWS_FOUND` is used only when official feeds are available and no matching items are found. If official feed coverage is unavailable/partial and no official match exists, status is `WAIT_FOR_DATA`.
- **No orders:** premarket run is a news refresh/review, not an automatic order or guaranteed entry.

## Files to replace

1. `news_catalyst.py` — full replacement.
2. `test_v8_regression.py` — full replacement.
3. `.github/workflows/nse-test-scheduled.yml` — full replacement, to add the 09:05 IST weekday scan and allow manual EOD/PREMARKET mode selection.

Do not replace other modules. The workflow runs the existing scanner using the most recent available EOD data and labels the premarket report accordingly.

## Output

The premarket run adds `outputs/v8_premarket_news_check.csv`, one row per shortlisted symbol with the exact IST window, official/secondary counts, status, headline, timestamp and URL. The log also prints a `[NEWS-DIAG] NEWS_WINDOW` line.

## Local tests

- Python compile check.
- V8 regression suite includes two new window-boundary tests (EOD five calendar dates; premarket includes weekend and ends at 09:15 IST).

Local/mock tests do not prove that NSE will return historical or overnight records. Verify the next GitHub Actions artifact/log. Keep `WAIT_FOR_DATA` when official coverage is incomplete and do not treat secondary-only news as verified catalyst.
