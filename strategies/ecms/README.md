> **Workflow design:** See [ECMS end-to-end workflow design and P0–P8 implementation plan](WORKFLOW_DESIGN.md) for the full Morning → EOD → next-session lifecycle, Mermaid flow, research-layer rules, acceptance gates and execution checklist.

## Approved ECMS strategy and execution roadmap — 16-Nov-2026

**This section is the current decision record for ECMS. It supersedes older statements elsewhere in this file that describe a permanent fundamental-only rejection gate.** The implementation-status notes below remain historical evidence of what code currently does; they must not be mistaken for completed implementation of this target policy.

### Objective

Find better-quality opportunities from **every eligible NSE Volume Gainers page stock** by identifying whether unusual volume is supported by positive demand/accumulation evidence, negative selling/distribution evidence, a genuine company/event catalyst, or suspicious/high-risk activity. A Volume Gainer is a research candidate, never an automatic buy signal. The objective is to improve decision quality and profit potential; profit is not guaranteed.

### Locked operating decisions

- **No basket strategy and no basket construction.** Evaluate and report individual stocks.
- **No basket strategy or production ECMS scanner backtesting.** A narrowly scoped U-Turn historical event-study is explicitly authorized on the isolated research branch using the already-restored V8 cache only. It must be reviewed before any ECMS implementation; it is not a trading P&L simulation and does not alter P8 live shadow validation.
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
| **P1 — Fundamentals** | Seven-metric coverage, official verification, metric-level source/URL/period/basis/unit, sector applicability, persistent ECMS cache and missing/stale retry behaviour. Also collect consecutive completed-FY diluted EPS as a separate U-Turn research input; it does not silently become an eighth fundamental gate metric. | Per-stock/per-metric evidence and source coverage; annual diluted-EPS provenance with matching period, reporting basis and unit. |
| **P2 — Volume origin** | Price/volume/liquidity and 5/10/20/30-session delivery history where reliable; positive vs negative volume evidence. Preserve validated daily OHLC history needed for the U-Turn pre-result 20-session peak; this is a separate research calculation, not a new scan filter. | Session-aligned, source-attributed stock reports; missing fields explicitly identified; U-Turn OHLC window provenance where available. |
| **P3 — Institutional evidence** | Official quarterly ownership/shareholding changes, promoter/pledge and insider disclosures where source mapping is verified, plus stock-specific bulk/block deals. | Period- and filing-attributed ownership/deal evidence; no inferred institutional identities. |
| **P4 — News and events** | Announcements, results, exact official result-publication date/time, orders, corporate actions, events and Morning-to-EOD incremental updates. Preserve the result announcement timestamp used to anchor the U-Turn window. | Source-linked, date-correct, deduplicated disclosure/event reports with issuer and event-date provenance. |
| **P5 — Trap/surveillance** | Official surveillance lists and multi-signal suspicious/distribution risk assessment. | Evidence-backed risk reasons and separate exclusion ledger; missing data never treated as clean or guilty. |
| **P6 — Market/technical context** | Nifty/sector relative strength, simple trend, breakout/retest/closing-strength and liquidity/exit-readiness observations. | Reproducible, data-complete context fields; no guessed thresholds. |
| **P7 — Balanced decision** | Combine fundamental status, volume origin, company/institutional evidence, catalyst, sector/technical context and trap risk. Add optional two-sided ECMS U-Turn research after P1/P2/P4 inputs and P6 technical context are validated. | Transparent individual-stock classification; separate downside reset/bottom-watch and upside overextension/momentum observations, never a gate or trading signal; no basket or opaque forced score. |
| **P8 — Live shadow validation** | Run the existing Morning/EOD workflow, inspect real reports/logs/cache/Telegram, correct defects and confirm operational consistency. | Live run evidence, coverage/runtime/report checks and user review. **No historical backtesting of the ECMS Volume Gainers scanner;** the separately approved U-Turn research event-study runs only on the isolated research branch. |


### P7 sub-layer — Fundamental U-Turn research (ECMS only)

The U-Turn concept is mapped into **P7 as an optional explanatory research layer**, with required source inputs prepared earlier: P1 supplies comparable annual diluted EPS, P2 supplies validated pre-result daily OHLC, and P4 supplies the exact official result-announcement timestamp. P8 checks the output and operational isolation. This placement does not reorder P0–P8 or change the existing Morning/EOD scan lifecycle.

**Purpose:** estimate a possible valuation reset after an annual EPS decline by applying the pre-result peak valuation multiple to the latest completed FY diluted EPS. Then report whether the latest completed post-result Close is near that estimate. It is not a prediction, confirmed support, reversal confirmation, entry trigger or Buy/Sell recommendation.

**Research formula (same reporting basis and INR/share units required):**
```text
Reference_PE = Pre_Result_Peak_High / Previous_FY_Diluted_EPS
Expected_Correction = (Previous_FY_Diluted_EPS - Current_FY_Diluted_EPS) * Reference_PE
U_Turn_Estimate = Pre_Result_Peak_High - Expected_Correction
              = Pre_Result_Peak_High * Current_FY_Diluted_EPS / Previous_FY_Diluted_EPS
```

- Use the immediately preceding completed FY and latest completed FY; **diluted EPS only**. Both years must use the same consolidated or standalone basis, same INR/share unit and comparable corporate-action/share basis. Never fall back to Basic EPS.
- Pre-result peak = maximum daily High across the **20 completed NSE trading sessions strictly before** the official result-announcement calendar date. Exclude the entire announcement date, even if the filing arrived after market close.
- Compare only with the latest valid completed-session Close strictly after the announcement date. Initial research proximity tolerance is ±3%; it is configurable and not a trading threshold.
- If current diluted EPS is equal to or above prior-year EPS, return `NO_EPS_DECLINE` and no reset estimate. Missing/unverified EPS, mismatched FY/basis/unit, missing official result timestamp, incomplete OHLC window, unadjusted corporate action or missing post-result Close must return an explicit `WAIT_FOR_DATA`, `UNVERIFIED` or review status; never invent a value.
- Loss/profit sign transitions are `NOT_COMPARABLE_FOR_THIS_FORMULA`. The proximity zone is not confirmed support and does not assert accumulation or a reversal.
- U-Turn output is attached to each eligible stock as a separate research observation. It **must not** reject or promote a candidate, alter the seven-metric fundamental gate, override volume-origin/trap evidence, change EOD entry trigger or Morning confirmation, or affect cache/Telegram decisions.
- No production ECMS scanner backtesting, basketting, broker/order action, auto-buy/sell or NSE V8 changes. The approved U-Turn event-study is limited to the existing read-only cache and remains isolated until issuer-level evidence is reviewed.

**Two-sided U-Turn — bottom and overextension context (research only):**

- **Downside / possible-bottom side:** retain the annual diluted-EPS valuation-reset estimate above. The separate OHLCV context may label `RESET_ZONE_ONLY` when Close is near the reset zone, or `BOTTOM_WATCH` only when zone proximity is accompanied by oversold RSI and one-session price/RSI stabilization. Neither confirms a bottom or support.
- **Upside / overextension side:** observe Wilder RSI(14), SMA20/SMA50, Close extension versus SMA20, and Volume versus the preceding 20 completed sessions. Initial research defaults: RSI >= 70 and extension >= 10% together produce `OVEREXTENDED`; one condition alone produces `STRETCHED`. Positive trend alignment can be `MOMENTUM_STRONG`; weakness with elevated volume can be `WEAKENING`. These are contextual labels, not confirmed tops or reversal signals.
- EPS growth is separate fundamental context; do not reverse the downside formula into a guaranteed upside target. Preserve separate valuation-reset and price-context statuses; missing inputs on either side remain `WAIT_FOR_DATA`.
- The two-sided context is placed under **P7**, using fundamentals from P1, OHLCV/delivery from P2, event dates from P4 and technical context from P6; P8 reviews live shadow output. It does not alter P0–P8 execution order or any production scan decision.

Implementation/design references: [U-Turn research design](../../docs/ECMS_FUNDAMENTAL_UTURN_RESEARCH_DESIGN.md), [downside EPS calculator](fundamental_uturn.py), [NSE UDiFF OHLC parser](uturn_nse_ohlc.py), [two-sided price-context module](uturn_two_sided.py).

### Execution discipline

- Work in the order P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8. Finish and evidence each phase before treating it as complete; do not jump ahead or silently change the roadmap.
- Before editing, inspect the current main-branch code, workflow, tests and latest relevant run/artifacts. Make small ECMS-only changes and run relevant tests.
- Never claim a workflow ran, a cache hit occurred, a provider was skipped or a phase completed without logs/artifact evidence.
- If data volume, provider limits or runtime threaten the two-scan workflow, prefer bounded batch retrieval, persistent cache and source coverage reporting over more serial per-stock calls.
- Do not expand the approved U-Turn event-study beyond the existing cache, add production scanner backtesting, basket construction, paid sources or new schedules unless the user explicitly changes these decisions.

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
- The downside research design uses the user-confirmed 20 completed NSE-session pre-announcement peak window, maximum daily High, a pre-result reference P/E and an initial ±3% proximity zone. A separate upside/overextension context checks RSI14, SMA20/SMA50, extension versus SMA20 and volume versus the prior 20-session average.
- The module is isolated research only and is mapped as an optional P7 explanatory sub-layer, using inputs prepared in P1/P2/P4 and reviewed in P8. It does not change phase order, EOD/Morning behavior, fundamental gating, production caches, Telegram decision messages or NSE V8. No production scanner backtesting, basketting, order or buy/sell signal; the isolated research event-study is not a trading P&L backtest.


## Fundamental U-Turn research implementation — 17-Nov-2026

- User-confirmed research settings: annual diluted EPS only; pre-result peak is the maximum daily High from the 20 completed NSE sessions strictly before the result announcement calendar date; initial validation universe is 3–5 NSE Main Board issuers.
- Research-only downside calculator: `strategies/ecms/fundamental_uturn.py`; official NSE UDiFF parser: `strategies/ecms/uturn_nse_ohlc.py`; two-sided price-context module: `strategies/ecms/uturn_two_sided.py`; tests: `tests/test_ecms_fundamental_uturn.py`, `tests/test_ecms_uturn_nse_ohlc.py` and `tests/test_ecms_uturn_two_sided.py`.
- The module requires separate previous/current diluted-EPS and reporting-basis fields, INR/share units, HTTPS source URLs for both EPS years, result announcement and both price observations, verified EPS/OHLC flags, consecutive FYs, positive EPS, post-result completed Close and corporate-action comparability. Missing or mismatched data fails closed.
- It computes a valuation reset estimate and ±3% proximity zone; this is not confirmed support, a reversal signal, entry trigger, Buy/Sell recommendation or guaranteed price.
- A dedicated branch-scoped CI workflow runs only the U-Turn unit tests: `.github/workflows/ecms-uturn-research-tests.yml`. First CI runs exposed one assertion-text mismatch (16 passed, 1 failed); the test expectation was corrected in commit `1a89516d4de86bca640daf09eebeb22b39b6f41d`. Initial calculator CI passed in [Run #7](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44026004284) with 17 tests. Expanded CI passed in [Run #13](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44026400503) and was reconfirmed in [Run #14](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44026505041): Python compile succeeded and all 23 calculator + NSE UDiFF parser tests passed. This is fixture/unit-test validation only, not issuer-level price-data or live workflow validation.
- The UDiFF parser accepts already-downloaded official daily NSE CM bhavcopy tables, checks `CM/STK/EQ`, symbol, session date, ISIN and HTTPS archive URL, and requires exactly 20 caller-supplied NSE trading sessions before the announcement date. It does not download files or infer holidays. The selected peak row carries its source URL. A 60-row date/source manifest is at `research/ecms_uturn/nse_ohlc_download_manifest.csv`; its dates are calendar-derived and still marked pending raw-bhavcopy verification.
- No provider fetching, scheduled workflow, Telegram, cache, EOD/Morning or NSE V8 integration. Do not merge to main or enable in ECMS runtime until expanded CI passes and 3–5 issuer-level official filing/OHLC/corporate-action reconciliations are reviewed.
- Official filing discovery reference: [NSE Corporate Filings — Financial Results](https://www.nseindia.com/companies-listing/corporate-filings-financial-results). NSE's filing records distinguish audited status, cumulative/non-cumulative, consolidated/non-consolidated basis and reporting period; these fields must be retained during issuer validation. See also [NSE integrated filing XBRL example](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_210520_05112026183448_iXBRL_WEB.html).
- Full design and remaining gates: [ECMS Fundamental U-Turn Research Design](../../docs/ECMS_FUNDAMENTAL_UTURN_RESEARCH_DESIGN.md).

- Sample intake template (5 blank issuer rows): [U-Turn sample universe intake CSV](../../research/ecms_uturn/sample_universe_intake_template.csv). No issuer data is prefilled or fabricated. Candidate admission requires NSE Main Board proof, audited annual diluted EPS for both consecutive FYs on the same reporting basis, official result-announcement date/time, 20 valid pre-result daily High observations, post-result completed Close and corporate-action reconciliation.

- Initial source-verified sample: [FY2026 sample universe and evidence](../../research/ecms_uturn/SAMPLE_UNIVERSE_FY2026.md) — INFY, ACI and AARTIIND; FY2025/FY2026 consolidated diluted EPS and event date/time verified against NSE filings/annual reports. OHLC peak, post-result close and corporate-action verification remain pending.

- The initial 20-session date windows are recorded for INFY (20-Mar–22-Apr), AARTIIND (01-Apr–30-Apr) and ACI (09-Apr–08-May), each excluding its entire result announcement date. The dates use NSE's published 2026 equity holiday calendar; the raw daily archive files still need to be downloaded and checked before any peak calculation. The latest completed post-result close as of 17-Nov-2026 is expected to be 16-Nov-2026; source URLs are listed in `research/ecms_uturn/post_result_close_manifest.csv`, with actual closes pending verification.


### P2/P7 research evidence — official NSE U-Turn sample OHLC

- The 3-stock U-Turn sample has a 60-row, 20-session-per-stock pre-result manifest plus a separate 16-Nov-2026 latest completed post-result close manifest.
- `research/ecms_uturn/download_verify_nse_bhavcopy.py` fetches only the official NSE UDiFF archive URLs, validates symbol/date/CM/STK/EQ/ISIN/High/Close, records archive SHA-256 and emits an evidence artifact. The isolated `ECMS U-Turn NSE Sample Data Audit` workflow is scoped to the research branch and these files only.
- The fetcher intentionally does not certify corporate-action comparability and does not calculate valuation targets. A successful download/parse is only raw price-row verification; corporate-action and diluted-EPS share-basis checks remain a separate gate.


#### NSE sample downloader execution correction — 17-Nov-2026

- The first session-warmed downloader revision completed its GitHub Actions step with exit code 0 but produced no output directory or artifact. Log inspection found the Python file defined download helpers but had no executable `main()` entry point; therefore the workflow had not attempted any archive downloads. This was a false-green workflow step, not evidence of NSE access.
- Corrected in commit `ac6fc37e0d9ced68993eafe1ef55bf064873ef03`: added the manifest-driven runner, bounded two-worker downloads, per-archive SHA-256/schema audit, per-symbol exact 20-session parser validation, post-result close extraction, CSV/JSON evidence outputs, and a non-zero exit whenever archives, any 20-session window, or post-result closes are incomplete.
- The corrected commit should trigger the research-only workflow through the existing path filter. Do not treat this correction as a successful fetch until the new run has a non-empty artifact and the summary/CSV rows have been inspected. Corporate-action review and EPS/share-basis reconciliation remain pending; no U-Turn targets are calculated.


#### NSE official portal fallback — 17-Nov-2026

- Run #6 (44041181335, commit bff231576e3d01774ead2489e373c5c7cfdc1ea7) failed closed: the GitHub runner timed out reading https://www.nseindia.com/ during session warm-up; 0/32 archives and 0 OHLC rows were downloaded or verified. No stock was marked ready and no target was calculated.
- NSE's official All Reports page is also published at https://www.nseindia.in/all-reports; it lists CM-UDiFF Common Bhavcopy Final (zip). The older CM Bhavcopy formats are explicitly marked discontinued from 08-Jul-2024.
- Downloader commit 01a40149a2d66f9c4c1f075d733a457a7b4784f8 now tries the alternate official reports portal first with bounded warm-up timeouts, then the original NSE host, and finally permits the official archive request without website cookies if both warm-ups fail. This is a connectivity fallback only; archive host, ZIP/schema checks, exact session checks, and fail-closed behavior are unchanged.
- Pending CI evidence: successful retrieval of all manifest archives, 60 exact pre-result OHLC rows, and 3 post-result closes. Until verified, all sample symbols remain WAIT_FOR_DATA. Corporate-action and diluted-EPS basis review remain separate mandatory gates.

#### Read-only V8 cache reuse for issuer sample audit — 17-Nov-2026

- The isolated workflow `.github/workflows/ecms-v8-cache-readonly-audit.yml` restores the existing shared NSE V8 cache using `actions/cache/restore@v5` and the `nse-bhavcopy-${{ runner.os }}-main-` restore prefix. It does not save or mutate the shared cache and has no V8 workflow/code changes.
- `research/ecms_uturn/audit_v8_cache_samples.py` indexes cached Bhavcopy and delivery files by their filename session date, then independently validates row-level `TradDt`/`DATE1`, CM/STK/EQ, symbol, ISIN, High/Close, and exact manifest session coverage for INFY, ACI and AARTIIND.
- Delivery is audited as separate date/symbol coverage evidence only; it is not an input to the EPS valuation-reset formula.
- EPS cache/XBRL matches are emitted as discovery-only evidence. An ordinary EPS column or keyword match is not annual diluted EPS verification. The official annual diluted-EPS and corporate-action gates remain pending until the actual filing facts, FY, consolidated basis and INR/share unit are reconciled.
- Outputs are `v8_cache_audit/cached_ohlc_verified_rows.csv`, `cached_ohlc_window_summary.csv`, `cached_post_result_close.csv`, `cached_delivery_coverage.csv`, `diluted_eps_discovery_only.csv` and `symbol_audit_summary.json`.
- A successful workflow only proves that the audit completed; each issuer's row-level status controls readiness. No U-Turn target is calculated, and no production integration is permitted.

#### Complete-fundamentals-only two-sided observations — 17-Nov-2026

- `research/ecms_uturn/audit_complete_fundamentals_twosided.py` screens the full restored `data/inputs/fundamental_metrics.csv` universe, not only the three EPS research examples.
- Eligibility requires exactly one row per symbol, all seven numeric core metrics (`RevenueGrowthPct`, `ProfitGrowthPct`, `ROEPercent`, `ROCEPercent`, `DebtToEquity`, `InterestCoverage`, `OperatingCashFlowINR`), per-metric source/URL/period/calculation-basis/currency provenance, verified period alignment and publication date, and one exact official NSE filing-register match.
- A complete cache row is **not** automatically an official metric-value verification. Output explicitly says that XBRL fact-level value verification remains separate; third-party provider values are not promoted to `OFFICIAL_XBRL_VERIFIED` by URL or populated fields alone.
- Only symbols passing this completeness/provenance gate are sent to `assess_two_sided_price_context` using validated cached NSE UDiFF CM/STK/EQ OHLCV sessions. All others receive `WAIT_FOR_DATA`.
- Because an independently verified annual diluted-EPS valuation zone and corporate-action-adjusted pre-result peak are not yet supplied for this broad universe, the bottom-side valuation-zone condition is deliberately inactive. This run can report technical bottom-side/overextension context only where the module supports it, but does not claim a valuation reset or confirmed bottom.
- Outputs: `v8_cache_audit/fundamental_completeness_all_symbols.csv`, `two_sided_complete_fundamentals_only.csv`, `bhavcopy_file_validation_errors.csv`, and `complete_fundamentals_two_sided_summary.json`.
- Research-only, shared V8 cache restore-only, no cache save, no production integration, no trading signals/orders.

#### First complete-fundamentals-only V8 cache run — 17-Nov-2026

- Audit run #13: [GitHub Actions run](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44051940288), commit `c0c538c46f846c1c8f7502103754781917add1de`; successful. Cache restore matched `nse-bhavcopy-Linux-main-43988025626`; 202 dated Bhavcopy sessions restored and validated, with zero file/schema/session-date errors.
- Universe checked: 906 symbols from the cached fundamental metrics file.
- Complete-field/provenance gate: 237 symbols passed; 669 were held at `WAIT_FOR_DATA`. The gate requires all seven numeric metrics, per-metric source/URL/period/currency, explicit accepted calculation basis, verified period alignment/publication date, and one exact official NSE XBRL filing-register match. Where metric-level basis JSON is absent, an explicit non-legacy row-level basis is used.
- Two-sided technical observations on the 237 passing symbols: `NEUTRAL=180`, `MOMENTUM_STRONG=22`, `STRETCHED=19`, `WEAKENING=13`, `OVEREXTENDED=3`.
- The three `OVEREXTENDED` observations were NAVKARURB, NDGL and SPECTRUM. These are technical research flags only, not sell/avoid calls or recommendations.
- This pass does not certify every metric value as `OFFICIAL_XBRL_VERIFIED`; source/provenance completeness is distinct from metric-level XBRL fact verification. The bottom-side valuation zone was not run because annual diluted EPS and corporate-action-adjusted pre-result peaks were not independently verified for this broad symbol set. No `BOTTOM_WATCH` or valuation reset is claimed.
- Artifact: `ecms-v8-cache-readonly-audit-44051940288` (12 output files; includes full 906-symbol eligibility/rejection table and 237-symbol technical output). Shared cache remains restore-only; no V8 production files or workflows were changed.


---

### Latest U-Turn research validation addendum — 17-Nov-2026

This addendum supersedes earlier pending-status notes in the historical U-Turn implementation log below. It does **not** authorize production integration.

- Detailed P0–P8 research design and locked acceptance rules: [isolated U-Turn research README](../../research/ecms_uturn/README.md).
- Latest successful same-run event-study / parser consistency run: [#44077735477](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44077735477). Latest successful read-only cache audit: [#44077339832](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44077339832). A subsequent CI pass adds official calendar/corporate-action and dividend-inclusive checks; see the current research branch Actions runs before treating those additions as accepted.
- Three pilot stocks each have 20/20 strict pre-result OHLC sessions, matching ISIN, peak date/High agreement between parsers, and 20/20 delivery rows. Official NSE 2026 holiday-calendar comparison matches all three windows.
- Post-result close rows are 3/3 READY. No bonus/split/rights/demerger adjustment was found in reviewed event windows; cash dividends are separately recorded.
- ACI is the only EPS-decline pilot. Its target zone was touched on eight sessions, but no zone-touch session met both delivery >=60% and RVOL >=1.5x. INFY and AARTIIND are no-decline controls and receive no downside target.
- A fixed-seed five-stock source-verification draw remains separate and unchanged; it produced no verified EPS-decline case. The three-stock event-study pilot is not randomized or statistically representative.
- Research only: no Volume Gainers integration, no buy/sell signal, no orders, no P&L simulation, and no production ECMS/V8 changes.
