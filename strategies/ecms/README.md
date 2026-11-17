> **Workflow design:** See [ECMS end-to-end workflow design and P0–P8 implementation plan](WORKFLOW_DESIGN.md) for the full Morning → EOD → next-session lifecycle, Mermaid flow, research-layer rules, acceptance gates and execution checklist.

## Approved ECMS strategy and execution roadmap — 16-Nov-2026

**This section is the current decision record for ECMS. It supersedes older statements elsewhere in this file that describe a permanent fundamental-only rejection gate.** The implementation-status notes below remain historical evidence of what code currently does; they must not be mistaken for completed implementation of this target policy.

### Objective

Find better-quality opportunities from **every eligible NSE Volume Gainers page stock** by identifying whether unusual volume is supported by positive demand/accumulation evidence, negative selling/distribution evidence, a genuine company/event catalyst, or suspicious/high-risk activity. A Volume Gainer is a research candidate, never an automatic buy signal. The objective is to improve decision quality and profit potential; profit is not guaranteed.

### Locked operating decisions

- **No basket strategy and no basket construction.** Evaluate and report individual stocks.
- **No historical backtesting.** P8 is live shadow-output and operational validation only. Do not add historical backtesting jobs, datasets or requirements.
- Keep exactly the existing two ECMS scans: Morning and EOD. Preserve the previous-EOD → next-Morning and same-day-Morning → EOD comparison cycle, official NSE holiday/session handling and separate reports.
- Research every eligible Main Board company stock returned by the NSE Volume Gainers page. Do not impose a Top-20/Top-25 cap on the returned eligible rows.
- Keep ECMS isolated from NSE V8 production workflows, providers, thresholds, caches and selection logic.
- No broker integration, order placement, auto-buy or auto-sell.
- Keep research collection separate from final classification. Do not reject a stock merely because an optional source is missing or unavailable.

### Fundamental decision policy

The seven core metrics remain Revenue Growth, Profit Growth, ROE, ROCE, Debt/Equity, Interest Coverage and Operating Cash Flow.

- When all applicable required metrics are present, current, period/basis aligned and sufficiently verified against official filings, the approved fundamental rules may act as a rejection gate. Sector-specific treatment is mandatory for banks, NBFCs and insurers.
- When fundamentals are partial, missing, stale, conflicting or unverified, retain the explicit PARTIAL_DATA, WAIT_FOR_DATA, STALE, CONFLICT or equivalent status. **Do not reject solely for incomplete fundamental coverage.** Continue evaluating the stock using the other available evidence, while never describing it as fundamentally strong or as a verified fundamental PASS.
- Third-party values remain provider evidence until reconciled with an official filing. Never invent values, silently average conflicts, or overwrite source/period/basis evidence.
- Fundamental collection and the fundamental decision gate are separate stages. Collect for every eligible page stock, preserve missing/rejected rows and provenance, and do not narrow collection to a preliminary shortlist.

### Positive/negative volume-origin research

For every eligible page stock, combine the evidence below; no single field proves accumulation or distribution:

1. **Price and volume:** current/previous-session OHLCV, volume versus 5/10/20-session context where reliable, traded value, price progress, close location, candle body/wicks, gaps and reversals.
2. **Delivery:** delivery quantity, delivery percentage and delivered value across available completed sessions; compare up-days and down-days. High delivery alone does not prove accumulation.
3. **Follow-through:** Morning/EOD persistence and subsequent completed trading-session behaviour. Never compare partial Morning volume directly with full-day averages.
4. **Company evidence:** official announcements, financial results, orders, material events, corporate actions, news, bulk/block deals and filing changes, with event/publication dates and sources.
5. **Institutional/ownership evidence:** stock-specific bulk/block disclosures and quarterly promoter/FII/DII/shareholding changes where official data is available. Do not infer an institutional buyer from delivery percentage or market-wide flows.
6. **Risk evidence:** official ASM/GSM/ESM, Trade-to-Trade, Periodic Call Auction, price-band and exchange surveillance status; combine with multi-session price/volume behaviour.
7. **Context:** Nifty and sector strength plus simple technical confirmation/readiness. Keep this proportionate; avoid heavy or duplicative data collection.

Use transparent classifications such as POSITIVE_EVIDENCE, NEGATIVE_EVIDENCE, EVENT_DRIVEN, MIXED_SIGNALS, SUSPICIOUS_HIGH_RISK and INSUFFICIENT_DATA, with confidence and source-backed reasons. These labels describe evidence, not certainty about buyer identity or future returns. Missing data is not a negative signal and is not proof of a trap.

**Trap handling = EXCLUDE only when severe risk is supported by a validated rule or corroborated evidence.** Preserve every exclusion in a separate ledger with symbol, date, evidence, source, severity and reason. A single weak signal, upper wick, volume spike or missing field is not enough.

### Simple implementation roadmap (P0–P8)

| Phase | Scope | Completion evidence |
|---|---|---|
| **P0 — Workflow protection** | Morning/EOD lifecycle, date/session and holiday handling, snapshot/cache restore-save, Telegram/report integrity, ECMS/V8 isolation and regression protection. | Actual Morning/EOD runtime evidence for both comparison legs; no stale snapshot overwrite; cache lifecycle verified. |
| **P1 — Fundamentals** | Seven-metric coverage, official verification, metric-level source/URL/period/basis/unit, sector applicability, persistent ECMS cache and missing/stale retry behaviour. | Per-stock/per-metric evidence and source coverage; actual cache reuse/provider-skip logs. |
| **P2 — Volume origin** | Price/volume/liquidity and 5/10/20/30-session delivery history where reliable; positive vs negative volume evidence. | Session-aligned, source-attributed stock reports; missing fields explicitly identified. |
| **P3 — Institutional evidence** | Official quarterly ownership/shareholding changes, promoter/pledge and insider disclosures where source mapping is verified, plus stock-specific bulk/block deals. | Period- and filing-attributed ownership/deal evidence; no inferred institutional identities. |
| **P4 — News and events** | Announcements, results, result dates, orders, corporate actions, events and Morning-to-EOD incremental updates. | Source-linked, date-correct, deduplicated disclosure/event reports. |
| **P5 — Trap/surveillance** | Official surveillance lists and multi-signal suspicious/distribution risk assessment. | Evidence-backed risk reasons and separate exclusion ledger; missing data never treated as clean or guilty. |
| **P6 — Market/technical context** | Nifty/sector relative strength, simple trend, breakout/retest/closing-strength and liquidity/exit-readiness observations. | Reproducible, data-complete context fields; no guessed thresholds. |
| **P7 — Balanced decision** | Combine fundamental status, volume origin, company/institutional evidence, catalyst, sector/technical context and trap risk. | Transparent individual-stock classification and inclusion/exclusion reasons; no basket or opaque forced score. |
| **P8 — Live shadow validation** | Run the existing Morning/EOD workflow, inspect real reports/logs/cache/Telegram, correct defects and confirm operational consistency. | Live run evidence, coverage/runtime/report checks and user review. **No historical backtesting.** |

### Execution discipline

- Work in the order P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8. Finish and evidence each phase before treating it as complete; do not jump ahead or silently change the roadmap.
- Before editing, inspect the current main-branch code, workflow, tests and latest relevant run/artifacts. Make small ECMS-only changes and run relevant tests.
- Never claim a workflow ran, a cache hit occurred, a provider was skipped or a phase completed without logs/artifact evidence.
- If data volume, provider limits or runtime threaten the two-scan workflow, prefer bounded batch retrieval, persistent cache and source coverage reporting over more serial per-stock calls.
- Do not add backtesting, basket construction, paid sources or new schedules unless the user explicitly changes these decisions.

---

# ECMS — NSE Volume Gainers Research

ECMS is an isolated, research-only workflow for stocks appearing on the NSE Volume Gainers page. It does not place orders and must not change or depend on the production NSE V8 scanner.

## Exact ECMS scope
## Eligible stock universe — NSE Main Board only

- Read the NSE Volume Gainers page, then keep only symbols present in the official NSE Main Board equity list.
- Explicitly subtract the official NSE SME list before assessment. SME stocks, ETFs/ETNs, indices, debt securities and other non-Main-Board instruments are excluded from ECMS candidates.
- The Main Board membership list is the authority for eligibility; a page row or an equity-like symbol/series by itself is not enough.
- ECMS applies an isolated check to the official Main Board CSV: only verified `INE` company-equity ISIN rows are eligible. `INF` ETF/fund-unit ISINs are excluded, and missing ISIN data fails closed rather than allowing an unverified instrument. This stricter gate is in ECMS code; the shared production NSE V8 Main Board filter is unchanged.
- Subtract the official NSE SME list. Index names and other instruments that are not in the official Main Board equity list are excluded.
- Only eligible NSE Main Board company stocks receive the existing fundamental assessment and appear as ECMS stock suggestions. Do not add SME, ETF/fund-unit or index recommendations.


For each eligible NSE Volume Gainer, publish the seven existing information groups plus the positive/negative volume-origin evidence defined in the approved strategy section above. Fundamental data is a conditional gate only when all applicable required metrics are sufficiently complete, current and verified. Incomplete, stale, conflicting or unverified fundamentals remain explicitly pending and do not by themselves reject a stock; continue the other research layers. The historical implementation notes below must be read as current-code status, not as a reason to override this approved target policy.
2. **Last five days' company news:** issuer-matched news/announcements, with official and secondary sources clearly distinguished.
3. **Upcoming company events:** only explicitly announced/confirmed NSE event-calendar entries within the next 90 calendar days, with date and source.
4. **Upcoming result:** next result date only when announced by the company/exchange; otherwise `NOT ANNOUNCED`.
5. **Valuation:** Indicative Cheap / Fair / Expensive from available P/E, PEG, P/B or EV/EBITDA multiples, with source, as-of date and basis shown; otherwise `NOT AVAILABLE`. These fixed multiple bands are not peer-adjusted and share price alone is not valuation.
6. **Bulk deals / Block deals:** NSE exchange-disclosed deals over the latest 30 calendar days, including deal date, client name/side, quantity and price. Show this information for every eligible page stock where source data is available; preserve source status and missing-data reasons.
7. **RVOL:** current volume relative to the prior 20 completed sessions' average volume. Display the value and data status; RVOL is informational only and never a rejection condition.

This older seven-group list describes the earlier information-only implementation. The approved target strategy above adds price/volume/delivery origin, sector/technical context and evidence-backed P5 trap exclusion. These layers must be implemented in their roadmap phase; until then, do not claim they are active gates. Missing/unavailable data is never itself a rejection reason.

## Daily operating rule — exactly two scans per NSE trading day (Asia/Kolkata)

ECMS runs **only two scheduled scans per official NSE cash-market trading day**. There is no third/extra scan.

1. **Morning — 09:20 IST:** scan the live NSE Volume Gainers page, assess every eligible page stock using the conditional fundamental policy and preserve WAIT/PARTIAL candidates for the other research layers, and save a separate same-day Morning snapshot.
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
- Fundamental PASS/FAIL/WAIT_FOR_DATA remains a separate evidence layer: verified PASS continues to balanced research; verified FAIL may trigger the approved fundamental rejection gate; WAIT/PARTIAL continues through all other research and is never marked fundamentally strong. The code now records `FundamentalDecisionRole` and `ResearchContinuationStatus` explicitly.

### Schedule, holidays and runtime

- Morning GitHub Actions cron: `50 3 * * 1-5` = **09:20 IST**.
- EOD GitHub Actions cron: `30 11 * * 1-5` = **17:00 IST**.
- Only these two ECMS schedules are permitted. Manual runs are for testing and do not create an additional daily schedule.
- On an official NSE trading holiday, the corresponding scan must finish as **SKIPPED**; it must not process a stale Volume Gainers page as a new scan or overwrite a valid snapshot. Weekday cron alone is not a holiday calendar, so holiday detection must use the official NSE session date.
- Calendar coverage is official-notice-only. As of 16-Nov-2026, NSE's official holiday page lists 2026 equity holidays but has not published the 2027 equity holiday list. Keep 2027 unconfigured and fail closed for unknown-year dates until the official NSE Capital Market - Equities circular is available; do not estimate or infer festival holidays. [Official NSE holiday page](https://www.nseindia.com/resources/exchange-communication-holidays).
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

- The 09:20 Morning run saves a separate, validated same-day snapshot at `data/cache/ecms/volume_gainers_same_day_morning.csv`. It contains the Morning page universe plus the Morning fundamental assessment and available news, event, result and deal observations. `MorningPageCapturedAtIST` records when the page was captured (before enrichment); `MorningSnapshotSavedAtIST` records when the completed snapshot was written.
- The after-session EOD run restores this Morning snapshot and marks EOD names as `MORNING_AND_EOD_REPEAT` or `EOD_NEW_ENTRY`. These labels are informational page-persistence evidence only; they do not independently alter the fundamental status or the conditional rejection policy.
- EOD reports retain Morning context fields separately from freshly collected EOD context. EOD still checks for newer news, announcements, results and deal disclosures rather than assuming Morning information is current.
- The same-day Morning snapshot is separate from `volume_gainers_previous_eod.csv`; EOD updates the previous-EOD reference only after its own valid page capture. The next trading day's Morning run therefore compares against the latest completed EOD snapshot.
- The Morning snapshot is included in the ECMS-only Actions cache paths for the Morning-to-EOD handoff. No shared NSE V8 workflow or production cache is changed.
- The Morning cache is saved only after a current-run snapshot passes date, uniqueness, status and GitHub run-ID checks. A failed/holiday Morning run cannot publish stale Morning state as a fresh snapshot.
- ECMS uses the provider's existing retry cooldown (`force_retry_incomplete=False`) so restoring the workspace cache does not force daily refetches of incomplete fundamentals. Fundamental thresholds and missing-data decisions remain unchanged.
- The full test suite runs in the validation job; scheduled scan jobs install dependencies and run the scan without repeating the test suite, preserving more of the 10-minute scan budget.

## EOD-to-morning snapshot lifecycle (workflow-only)

- The EOD Volume Gainers page universe is written to `data/cache/ecms/volume_gainers_previous_eod.csv` immediately after the eligible Main Board page rows and official completed-session date are known. This first snapshot does not wait for fundamentals, RVOL, news, events, valuation or deal enrichment.
- Snapshot writes are atomic and tagged with `SnapshotType=EOD`, `SnapshotStatus=VALID`, the EOD session date and capture time. A per-run marker records the GitHub run ID and symbol count.
- After assessment, the EOD snapshot may be refreshed with available context, but the EOD symbol universe and session date remain the source of truth.
- The EOD workflow saves the cache only when the marker and CSV prove that a valid snapshot was created by the current run. If page acquisition fails before a new snapshot exists, the previous valid cache is not replaced.
- The 09:20 Morning workflow restores the previous EOD cache, checks that its date matches the latest completed NSE session, and compares the live Main Board Volume Gainers list with it. Morning adds page-presence overlap labels independently of the existing fundamental confirmation fields.
- Morning never writes a new EOD page universe. It may save the unchanged EOD snapshot alongside its ECMS working cache. The next successful EOD run replaces it for the next trading session.
- `PagePresenceConfirmationStatus=DOUBLE_CONFIRMED_EOD_MORNING` means the symbol appeared in both page snapshots. The separate `ConfirmationStatus` retains the existing fundamental-based confirmation meaning; do not conflate the two.
- This is isolated to ECMS files and `.github/workflows/ecms-volume-gainers-shadow.yml`. NSE V8 workflow/configuration and shared production scanner behavior are not changed.

## Manual NSE Volume Gainers page files

Until the scanner is fully validated, every successful Morning and EOD scan also creates a downloadable CSV of the complete row set returned by the official NSE Volume Gainers page and sends it to the configured Telegram chat as a document:

- EOD: `outputs/ecms/volume_gainers_eod_nse_page.csv`
- Morning: `outputs/ecms/volume_gainers_morning_nse_page.csv`

The CSV preserves every returned page row, including rows outside the official Main Board universe, and explicitly labels `MainBoardEligible` and `PageUniverseStatus`. It also records scan mode/date, page capture time and NSE page source. The scanner's research universe remains the eligible Main Board subset; the downloadable page CSV is a manual comparison aid and does not change stock selection. The page currently labels its table Top 25, so “complete” means all rows returned by that NSE page response, not the entire NSE-listed universe.


## Fundamental U-Turn research module (not production)

- Design document: [ECMS Fundamental U-Turn Research Design](../../docs/ECMS_FUNDAMENTAL_UTURN_RESEARCH_DESIGN.md).
- User-confirmed basis: consecutive completed annual EPS values; pre-result price peak.
- The research design uses the user-confirmed 20 completed NSE-session pre-announcement peak window, maximum daily High, a pre-result reference P/E and an initial ±3% proximity zone.
- The module is isolated research only. It must not change P0–P8, EOD/Morning behavior, fundamental gating, production caches, Telegram decision messages or NSE V8. No backtesting, basketting, order or buy/sell signal.


## Fundamental U-Turn research implementation — 17-Nov-2026

- User-confirmed research settings: annual diluted EPS only; pre-result peak is the maximum daily High from the 20 completed NSE sessions strictly before the result announcement calendar date; initial validation universe is 3–5 NSE Main Board issuers.
- Research-only calculator: `strategies/ecms/fundamental_uturn.py`; unit tests: `tests/test_ecms_fundamental_uturn.py`.
- The module requires separate previous/current diluted-EPS and reporting-basis fields, INR/share units, HTTPS source URLs for both EPS years, result announcement and both price observations, verified EPS/OHLC flags, consecutive FYs, positive EPS, post-result completed Close and corporate-action comparability. Missing or mismatched data fails closed.
- It computes a valuation reset estimate and ±3% proximity zone; this is not confirmed support, a reversal signal, entry trigger, Buy/Sell recommendation or guaranteed price.
- A dedicated branch-scoped CI workflow runs only the U-Turn unit tests: `.github/workflows/ecms-uturn-research-tests.yml`. First CI runs exposed one assertion-text mismatch (16 passed, 1 failed); the test expectation was corrected in commit `1a89516d4de86bca640daf09eebeb22b39b6f41d`. Post-fix CI passed in [Run #7](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44026004284): Python compile succeeded and all 17 U-Turn unit tests passed. This is unit-test validation only, not issuer-level price-data or live workflow validation.
- No provider fetching, scheduled workflow, Telegram, cache, EOD/Morning or NSE V8 integration. Do not merge to main or enable in ECMS runtime until CI passes and 3–5 issuer-level official filing/OHLC reconciliations are reviewed.
- Official filing discovery reference: [NSE Corporate Filings — Financial Results](https://www.nseindia.com/companies-listing/corporate-filings-financial-results). NSE's filing records distinguish audited status, cumulative/non-cumulative, consolidated/non-consolidated basis and reporting period; these fields must be retained during issuer validation. See also [NSE integrated filing XBRL example](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_210520_05112026183448_iXBRL_WEB.html).
- Full design and remaining gates: [ECMS Fundamental U-Turn Research Design](../../docs/ECMS_FUNDAMENTAL_UTURN_RESEARCH_DESIGN.md).

- Sample intake template (5 blank issuer rows): [U-Turn sample universe intake CSV](../../research/ecms_uturn/sample_universe_intake_template.csv). No issuer data is prefilled or fabricated. Candidate admission requires NSE Main Board proof, audited annual diluted EPS for both consecutive FYs on the same reporting basis, official result-announcement date/time, 20 valid pre-result daily High observations, post-result completed Close and corporate-action reconciliation.

- Initial source-verified sample: [FY2026 sample universe and evidence](../../research/ecms_uturn/SAMPLE_UNIVERSE_FY2026.md) — INFY, ACI and AARTIIND; FY2025/FY2026 consolidated diluted EPS and event date/time verified against NSE filings/annual reports. OHLC peak, post-result close and corporate-action verification remain pending.
