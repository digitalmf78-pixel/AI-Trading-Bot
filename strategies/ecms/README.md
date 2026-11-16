# ECMS — NSE Volume Gainers Research

ECMS is an isolated, research-only workflow for stocks appearing on the NSE Volume Gainers page. It does not place orders and must not change or depend on the production NSE V8 scanner.

## Exact ECMS scope

For each eligible NSE Volume Gainer, publish only these seven information groups:

1. **Fundamentals (the only rejection filter):** Revenue Growth, Profit Growth, ROE, ROCE, Debt/Equity, Interest Coverage and Operating Cash Flow. Apply the configured fundamental thresholds and sector-specific applicability. A stock is included in the fundamental-pass set only when the required applicable fundamental checks pass. Missing or unverified required fundamental data is `WAIT_FOR_DATA`, not a pass.
2. **Last five days' company news:** issuer-matched news/announcements, with official and secondary sources clearly distinguished.
3. **Upcoming company events:** only explicitly announced/confirmed NSE event-calendar entries within the next 90 calendar days, with date and source.
4. **Upcoming result:** next result date only when announced by the company/exchange; otherwise `NOT ANNOUNCED`.
5. **Valuation:** Indicative Cheap / Fair / Expensive from available P/E, PEG, P/B or EV/EBITDA multiples, with source, as-of date and basis shown; otherwise `NOT AVAILABLE`. These fixed multiple bands are not peer-adjusted and share price alone is not valuation.
6. **Bulk deals / Block deals:** NSE exchange-disclosed deals over the latest 30 calendar days, including deal date, client name/side, quantity and price. Show this information for fundamental-PASS stocks; it is informational and never a rejection condition.
7. **RVOL:** current volume relative to the prior 20 completed sessions' average volume. Display the value and data status; RVOL is informational only and never a rejection condition.

**No non-fundamental field may reject, qualify, rank-gate or suppress a stock.** News sentiment, upcoming events/results, valuation, bulk/block deals and RVOL are context only. Missing context is shown as `NOT AVAILABLE` and does not reject a fundamental-PASS stock. Do not add technical, sector, catalyst, volume or research-score rejection gates.

## Daily checkpoints (Asia/Kolkata)

- **EOD:** weekday schedule at **16:45 IST**. Read the completed NSE Volume Gainers page, calculate/display 20-session RVOL, assess fundamentals, and collect the information groups above. Save the EOD symbol/fundamental snapshot in ECMS-owned state.
- **Morning:** weekday schedule at **09:20 IST**. Re-read the current NSE Volume Gainers page and reassess current-page stocks using the same fundamental-only gate.
- **Morning repeat marking:** if a stock that passed fundamentals at EOD appears again on the 09:20 page, mark it explicitly as `EOD_FUNDAMENTAL_PASS_REPEAT` (separate from a new morning entry). Also retain clear labels for new entries, EOD names no longer present, and morning fundamental status. A repeat label is informational, not an extra filter.
- EOD and morning reports/Telegram messages remain separate. The morning run must restore the previous EOD snapshot and ECMS fundamental workspace.

GitHub Actions cron values are UTC: `15 11 * * 1-5` = 16:45 IST and `50 3 * * 1-5` = 09:20 IST. These schedules belong only to `.github/workflows/ecms-volume-gainers-shadow.yml`.

## Fundamental data quality and sources

- Prefer official NSE XBRL / issuer filings; use official BSE filings as an official cross-check where available.
- Free Screener.in observations may be manually captured from publicly visible pages. No Screener Premium, paid API, login automation or scraping.
- Yahoo Finance/yfinance is third-party comparison data, never described as official verification.
- Preserve metric-level source, URL, financial period, publication date, calculation basis and unit. Do not average conflicting sources or silently promote provider/manual observations to official verification.
- For banks/NBFCs/insurers, mark metrics that are not applicable under the approved sector treatment; do not force industrial-company ratios onto financial institutions.
- Missing, stale, conflicting or unverified required fundamental evidence remains `WAIT_FOR_DATA`. Never manufacture a pass.
- For non-fundamental information, distinguish `NOT AVAILABLE`, `NOT ANNOUNCED` and source-unavailable states; these do not change the fundamental result.

## Free-source metric comparison audit (ECMS only)

- On each ECMS fundamental collection attempt, request secondary observations for all seven decision metrics even when Yahoo already has a value. Existing Yahoo values remain unchanged; secondary observations are stored in a separate comparison record.
- Publish `fundamental_source_comparison_ecms.csv` with one row per candidate/metric/source observation, including Yahoo value/source/period/basis and secondary source/value/period/URL.
- Every secondary observation is explicitly `NOT_OFFICIALLY_VERIFIED` and `RECONCILIATION_REQUIRED`. It must not be averaged with Yahoo, overwrite an existing metric, or independently change the fundamental PASS/FAIL/WAIT result.
- Missing secondary observations are recorded as `NO_SECONDARY_OBSERVATION`; no value is inferred from a populated table schema alone.
- This audit is limited to the ECMS workspace. It does not change shared NSE V8 provider settings or production caches.

## ECMS isolation

- Shared NSE inputs and production caches are read-only.
- ECMS-owned state/cache stays under `data/cache/ecms/`; reports stay under `outputs/ecms/`.
- Do not modify `.github/workflows/nse-test-scheduled.yml`, NSE V8, shared provider behavior, shared thresholds, production scanner logic or unrelated workflows.
- No broker integration, order placement, auto-buy or auto-sell.

## Current implementation / delivery status

The EOD and 09:20 workflow jobs and schedules are present in `.github/workflows/ecms-volume-gainers-shadow.yml`. The ECMS branch implementation now uses the fundamental shortlist as the sole decision gate, marks EOD fundamental-PASS repeats in the morning report, and adds informational enrichment for five-day news, the NSE event calendar, result dates, indicative valuation and official NSE bulk/block deal disclosures. Morning RVOL is deliberately shown as unavailable because a partial 09:20 session is not comparable with a full-day 20-session average; the prior EOD RVOL is retained for reference. These changes are under focused CI validation and have not yet been verified by a fresh live EOD/morning run.


## EOD-to-morning snapshot lifecycle (workflow-only)

- The EOD Volume Gainers page universe is written to `data/cache/ecms/volume_gainers_previous_eod.csv` immediately after the eligible Main Board page rows and official completed-session date are known. This first snapshot does not wait for fundamentals, RVOL, news, events, valuation or deal enrichment.
- Snapshot writes are atomic and tagged with `SnapshotType=EOD`, `SnapshotStatus=VALID`, the EOD session date and capture time. A per-run marker records the GitHub run ID and symbol count.
- After assessment, the EOD snapshot may be refreshed with available context, but the EOD symbol universe and session date remain the source of truth.
- The EOD workflow saves the cache only when the marker and CSV prove that a valid snapshot was created by the current run. If page acquisition fails before a new snapshot exists, the previous valid cache is not replaced.
- The 09:20 Morning workflow restores the previous EOD cache, checks that its date matches the latest completed NSE session, and compares the live Main Board Volume Gainers list with it. Morning adds page-presence overlap labels independently of the existing fundamental confirmation fields.
- Morning never writes a new EOD page universe. It may save the unchanged EOD snapshot alongside its ECMS working cache. The next successful EOD run replaces it for the next trading session.
- `PagePresenceConfirmationStatus=DOUBLE_CONFIRMED_EOD_MORNING` means the symbol appeared in both page snapshots. The separate `ConfirmationStatus` retains the existing fundamental-based confirmation meaning; do not conflate the two.
- This is isolated to ECMS files and `.github/workflows/ecms-volume-gainers-shadow.yml`. NSE V8 workflow/configuration and shared production scanner behavior are not changed.
