# ECMS — NSE Volume Gainers Research

ECMS is an isolated, research-only workflow for stocks appearing on the NSE Volume Gainers page. It does not place orders and must not change or depend on the production NSE V8 scanner.

## Exact ECMS scope
## Eligible stock universe — NSE Main Board only

- Read the NSE Volume Gainers page, then keep only symbols present in the official NSE Main Board equity list.
- Explicitly subtract the official NSE SME list before assessment. SME stocks, ETFs/ETNs, indices, debt securities and other non-Main-Board instruments are excluded from ECMS candidates.
- The Main Board membership list is the authority for eligibility; a page row or an equity-like symbol/series by itself is not enough.
- Only eligible NSE Main Board stocks receive the existing fundamental assessment and appear as ECMS stock suggestions. Do not add SME or ETF recommendations.


For each eligible NSE Volume Gainer, publish only these seven information groups:

1. **Fundamentals (the only rejection filter):** Revenue Growth, Profit Growth, ROE, ROCE, Debt/Equity, Interest Coverage and Operating Cash Flow. Apply the configured fundamental thresholds and sector-specific applicability. A stock is included in the fundamental-pass set only when the required applicable fundamental checks pass. Missing or unverified required fundamental data is `WAIT_FOR_DATA`, not a pass.
2. **Last five days' company news:** issuer-matched news/announcements, with official and secondary sources clearly distinguished.
3. **Upcoming company events:** only explicitly announced/confirmed NSE event-calendar entries within the next 90 calendar days, with date and source.
4. **Upcoming result:** next result date only when announced by the company/exchange; otherwise `NOT ANNOUNCED`.
5. **Valuation:** Indicative Cheap / Fair / Expensive from available P/E, PEG, P/B or EV/EBITDA multiples, with source, as-of date and basis shown; otherwise `NOT AVAILABLE`. These fixed multiple bands are not peer-adjusted and share price alone is not valuation.
6. **Bulk deals / Block deals:** NSE exchange-disclosed deals over the latest 30 calendar days, including deal date, client name/side, quantity and price. Show this information for fundamental-PASS stocks; it is informational and never a rejection condition.
7. **RVOL:** current volume relative to the prior 20 completed sessions' average volume. Display the value and data status; RVOL is informational only and never a rejection condition.

**No non-fundamental field may reject, qualify, rank-gate or suppress a stock.** News sentiment, upcoming events/results, valuation, bulk/block deals and RVOL are context only. Missing context is shown as `NOT AVAILABLE` and does not reject a fundamental-PASS stock. Do not add technical, sector, catalyst, volume or research-score rejection gates.

## Daily operating rule — exactly two scans per NSE trading day (Asia/Kolkata)

ECMS runs **only two scheduled scans per official NSE cash-market trading day**. There is no third/extra scan.

1. **Morning — 09:20 IST:** scan the live NSE Volume Gainers page, assess every eligible page stock using the existing ECMS fundamental-only rejection rule, and save a separate same-day Morning snapshot.
2. **Evening / EOD — 17:00 IST:** scan the completed day's NSE Volume Gainers page, assess stocks with the same existing ECMS rules, restore the same-day Morning snapshot, and mark page overlap separately.

### The repeating comparison cycle

- Previous trading day's EOD snapshot → today's 09:20 Morning scan.
- Today's Morning snapshot → today's 17:00 EOD scan.
- Today's valid EOD snapshot → next official trading day's Morning scan.
- Repeat this cycle on every NSE trading day. Keep Morning and EOD reports/Telegram messages separate.

### Same-stock labels and result handling

- A symbol present in both today's Morning and EOD page lists is marked `MORNING_AND_EOD_REPEAT`.
- A symbol present only in today's EOD page list is marked `EOD_NEW_ENTRY`.
- A symbol present only in the Morning list remains identifiable as Morning-only / not present at EOD.
- The previous EOD → current Morning comparison is also shown separately; do not confuse it with the same-day Morning → EOD comparison.
- These are **page-presence labels only**. They apply regardless of whether the stock's fundamental result is PASS, FAIL or WAIT_FOR_DATA.
- Show each stock's actual existing fundamental result alongside its repeat/new label. Do not create a new rejection, ranking, scoring, confirmation or selection rule from repeat status.
- All seven existing fundamental metrics, thresholds, sector applicability, PASS/FAIL/WAIT_FOR_DATA treatment, and information-only fields remain unchanged.

### Schedule, holidays and runtime

- Morning GitHub Actions cron: `50 3 * * 1-5` = **09:20 IST**.
- EOD GitHub Actions cron: `30 11 * * 1-5` = **17:00 IST**.
- Only these two ECMS schedules are permitted. Manual runs are for testing and do not create an additional daily schedule.
- On an official NSE trading holiday, the corresponding scan must finish as **SKIPPED**; it must not process a stale Volume Gainers page as a new scan or overwrite a valid snapshot. Weekday cron alone is not a holiday calendar, so holiday detection must use the official NSE session date.
- Each scheduled Morning/EOD scan has a **10-minute maximum runtime target** so the Morning result is available before 09:30 IST. A timeout/failure must be reported clearly and must not corrupt the previous valid snapshot. Validate actual end-to-end runtime with Actions evidence; a configured timeout alone is not proof of successful completion within 10 minutes.

These schedules belong only to `.github/workflows/ecms-volume-gainers-shadow.yml`.

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

The ECMS workflow has exactly two scheduled jobs: Morning at 09:20 IST and EOD at 17:00 IST. Both scan jobs are capped at 10 minutes; end-to-end completion within that budget still requires successful Actions runtime evidence. The scanner checks the official NSE trading-session calendar before either mode and emits `SKIPPED` on a non-trading date, without reading the page as a new scan or replacing a valid snapshot. Same-day Morning/EOD page overlap is informational and independent of the fundamental PASS/FAIL/WAIT_FOR_DATA result. Morning RVOL is deliberately shown as unavailable because a partial 09:20 session is not comparable with a full-day 20-session average; the prior EOD RVOL is retained for reference. A fresh live EOD → Morning → EOD cycle is still required before calling the loop production-verified.



## Same-day Morning-to-EOD cache loop

- The 09:20 Morning run saves a separate, validated same-day snapshot at `data/cache/ecms/volume_gainers_same_day_morning.csv`. It contains the Morning page universe plus the Morning fundamental assessment and available news, event, result and deal observations.
- The after-session EOD run restores this Morning snapshot and marks EOD names as `MORNING_AND_EOD_REPEAT` or `EOD_NEW_ENTRY`. These labels are informational page-persistence evidence only; they do not alter the fundamental-only rejection gate.
- EOD reports retain Morning context fields separately from freshly collected EOD context. EOD still checks for newer news, announcements, results and deal disclosures rather than assuming Morning information is current.
- The same-day Morning snapshot is separate from `volume_gainers_previous_eod.csv`; EOD updates the previous-EOD reference only after its own valid page capture. The next trading day's Morning run therefore compares against the latest completed EOD snapshot.
- The Morning snapshot is included in the ECMS-only Actions cache paths for the Morning-to-EOD handoff. No shared NSE V8 workflow or production cache is changed.

## EOD-to-morning snapshot lifecycle (workflow-only)

- The EOD Volume Gainers page universe is written to `data/cache/ecms/volume_gainers_previous_eod.csv` immediately after the eligible Main Board page rows and official completed-session date are known. This first snapshot does not wait for fundamentals, RVOL, news, events, valuation or deal enrichment.
- Snapshot writes are atomic and tagged with `SnapshotType=EOD`, `SnapshotStatus=VALID`, the EOD session date and capture time. A per-run marker records the GitHub run ID and symbol count.
- After assessment, the EOD snapshot may be refreshed with available context, but the EOD symbol universe and session date remain the source of truth.
- The EOD workflow saves the cache only when the marker and CSV prove that a valid snapshot was created by the current run. If page acquisition fails before a new snapshot exists, the previous valid cache is not replaced.
- The 09:20 Morning workflow restores the previous EOD cache, checks that its date matches the latest completed NSE session, and compares the live Main Board Volume Gainers list with it. Morning adds page-presence overlap labels independently of the existing fundamental confirmation fields.
- Morning never writes a new EOD page universe. It may save the unchanged EOD snapshot alongside its ECMS working cache. The next successful EOD run replaces it for the next trading session.
- `PagePresenceConfirmationStatus=DOUBLE_CONFIRMED_EOD_MORNING` means the symbol appeared in both page snapshots. The separate `ConfirmationStatus` retains the existing fundamental-based confirmation meaning; do not conflate the two.
- This is isolated to ECMS files and `.github/workflows/ecms-volume-gainers-shadow.yml`. NSE V8 workflow/configuration and shared production scanner behavior are not changed.
