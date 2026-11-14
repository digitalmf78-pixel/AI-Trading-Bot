# ECMS workflow contract

## Workflow A — ECMS EOD
- Trigger: weekday after the market close; use the official NSE trading calendar to skip holidays/non-sessions.
- Restore the same shared-cache contract used by the main scanner, with matching cache key/version semantics.
- Read Bhavcopy and history without modifying them.
- Select unusual-volume Main Board candidates (initial research threshold RVOL > 1.5 against 20 prior complete sessions; retain raw values and do not truncate the universe before fundamental/catalyst checks).
- Enrich with dated fundamentals and issuer-matched official filings; include credible secondary news only as corroboration.
- Check the trailing five calendar days and clearly mark no-news versus source-unavailable.
- Write only ECMS reports/state.

## Workflow B — ECMS Morning
- Trigger on market days beginning at 09:15 IST.
- Restore the same shared-cache contract and load the latest successful EOD candidate file.
- Obtain live market data from a verified provider/endpoint. The provider adapter is a blocking implementation dependency; do not assume a web page's Volume Gainers table is a stable API.
- Track candidates whether or not they appear in the live Volume Gainers ranking.
- Capture timestamp, LTP, open, previous close, volume, traded value, relative volume, VWAP (if reliable), opening range and data freshness.
- Do not label an entry candidate before the 09:25–09:30 confirmation window.
- Write only ECMS morning reports/state. No order placement.

## Shared cache contract
The two workflows must use exactly the same ordered cache path list as the production scanner. They must use a compatible cache key and restore prefix. A successful cache restore must be logged and checked for required files and freshness. Never create an empty replacement cache and call it a valid shared-data restore.

## Operational safety
- Both workflows initially run manually/shadow-only until tests pass.
- A feed failure, empty response, HTML challenge, stale quote, symbol mismatch or missing EOD shortlist must result in WAIT_FOR_DATA.
- EOD and morning output files are separate.
- Never alter .github/workflows/nse-test-scheduled.yml, existing production scanner logic or shared cache contents.