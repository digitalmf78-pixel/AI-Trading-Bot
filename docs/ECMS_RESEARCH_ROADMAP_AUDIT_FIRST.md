# ECMS Research Roadmap — Audit First

**Status:** P0 implementation is in an isolated draft PR for CI/review; no production merge or live behaviour change.  
**Base:** `main` at `9e4b722c2be223ffa8ec78df4a1c5aeb84e28794` (verified before this planning branch was created).  
**Scope:** ECMS only. Research and shadow testing only. No broker/order execution.

## 1. Decisions locked by the user

1. Keep exactly the existing two ECMS scans and their current Morning/EOD responsibilities.
2. Preserve the existing comparison lifecycle without behavioural changes:
   - previous valid EOD snapshot -> next trading-session Morning;
   - same-session Morning -> same-session EOD;
   - valid EOD snapshot -> next trading-session Morning.
3. Keep Main Board NSE company equities only; exclude SME, ETFs/funds, indices and non-equity instruments.
4. Balanced candidate quality: fundamentals + institutional-footprint evidence + technical entry readiness + low trap risk. Do not let one indicator dominate.
5. **Trap handling = EXCLUDE:** high-risk candidates are excluded from the normal research/entry shortlist, while a separate audit/rejection ledger preserves the symbol, date, evidence, source, severity and reason. A single weak signal must not automatically establish a trap.
6. Missing/unavailable/unverified data is not proof of a trap and is not a negative fundamental result. Keep it in a verification-pending status, not entry-ready.
7. Do not let footprint evidence override Fundamental FAIL. Fundamental WAIT remains WAIT.
8. Keep production NSE V8, its workflow, shared providers, shared thresholds and production caches untouched.
9. No automatic orders, buy/sell calls or broker integration.

## 2. Purpose

ECMS should turn NSE Volume Gainers into a carefully verified research universe, not simply rank the largest volume spikes. The priority is **more reliable data collection, source verification, historical context and stock-specific research** before writing new selection logic.

The roadmap is intentionally audit-first. Proposed indicators, thresholds and source choices below are research questions, not approved production rules. They must be validated against actual data coverage and historical outcomes before implementation.

## 3. Work sequence

### Phase 0 — Repository and workflow baseline audit (first)

- Map the complete ECMS entry points, modules, imports, configuration, tests, workflow jobs, cache paths, artifacts, Telegram output and README/contract documentation.
- Record current branch/head, schedules, timezone conversions, actual timeout settings and scan command.
- Trace every data field from source fetch -> normalization -> cache -> assessment -> CSV/JSON -> Telegram.
- Identify duplicated fetches, per-symbol API loops, missing pagination, retry/cooldown behaviour, rate limits and cache invalidation.
- Compare documented behaviour against executable code and recent successful/failed Actions runs.
- Explicitly audit the current conflict between fundamental-only rejection documentation and the newly approved trap-risk exclusion policy.
- Confirm Morning/EOD comparison logic, date anchoring, snapshot validation and holiday behaviour through code and regression tests.
- Establish baseline runtime and source coverage. A configured timeout is not evidence of actual runtime.
- Deliver a file-by-file findings register: verified, partially verified, missing, contradictory, broken, risky, and not yet testable.

**Exit condition:** a written, evidence-backed audit report and regression tests that lock existing Morning/EOD behaviour. No strategy changes in this phase.

### Phase 1 — Data inventory and source reliability research

Build a field-level data catalogue for every existing and proposed field:

- field name and definition;
- source/provider and official/secondary classification;
- source endpoint/page/document and retrieval method;
- symbol/ISIN mapping method;
- event date, publication date, financial period and as-of date;
- units, currency, calculation basis and corporate-action adjustment;
- freshness/latency, history depth, pagination and rate limits;
- coverage by symbol and by scan;
- null/missing/error states;
- duplicate/revision handling;
- independent validation method;
- cache key, cache TTL and invalidation rules.

Research sources in priority order: official NSE/issuer/BSE/SEBI disclosures where applicable; then clearly labelled secondary providers for comparison and discovery. Do not assume a source is reliable merely because it returns a value. Verify actual schema, period alignment, completeness and repeatability.

**Exit condition:** source matrix with measured coverage, accuracy limitations, cost/runtime impact and fallback policy. No new score or rejection thresholds yet.

### Phase 2 — Price, volume, delivery and liquidity research

Audit and collect historical evidence for:
- daily OHLCV and traded quantity/value;
- delivery quantity, delivery percentage and delivered value;
- 5/10/20/30-session volume baselines (mean and median);
- relative volume and volume persistence;
- gap, intraday range, close location, wick/body structure;
- price response on high-volume and high-delivery sessions;
- up-day/down-day delivery behaviour;
- average traded value, spread/impact proxies and exit liquidity;
- sector/index-relative strength;
- corporate-action adjusted history.

Do not mix partial Morning session volume with completed-day averages. Keep the Morning page-presence comparison separate from intraday signal interpretation.

**Exit condition:** reproducible historical dataset with exact session dates, units, adjustment status and coverage report.

### Phase 3 — Fundamental data quality research

Continue the seven existing metric families:
Revenue Growth, Profit Growth, ROE, ROCE, Debt/Equity, Interest Coverage and Operating Cash Flow.

For every stock/metric/source observation, validate:
- official filing/XBRL concept and issuer mapping;
- consolidated vs standalone;
- quarterly vs annual/TTM period;
- period end and publication date;
- unit scaling, sign and denominator;
- sector applicability (banks, NBFCs, insurers and other financials);
- restatements, revised filings and duplicate disclosures;
- source conflicts and reconciliation tolerance.

Statuses must distinguish PASS, FAIL, WAIT_FOR_DATA, NOT_APPLICABLE, SOURCE_UNAVAILABLE, STALE and CONFLICT as appropriate. Do not promote third-party or manually captured values to official verification.

**Exit condition:** stock-by-stock metric coverage and evidence-quality report, including failed/rejected and WAIT stocks.

### Phase 4 — Institutional footprint / accumulation research

Investigate evidence independently; never infer an institutional buyer from delivery percentage alone.

Research:
- 5/10/20-session delivered quantity, delivered value and delivery percentage;
- price stability/advance/decline while delivery changes;
- up-session vs down-session delivery;
- volume persistence vs one-session spike;
- stock-specific bulk/block deals with disclosed client, side, quantity, price and date;
- quarterly FII/FPI and mutual-fund shareholding changes;
- promoter holding and pledge changes;
- insider/PIT/SAST disclosures;
- exact source attribution, reporting period, filing/publication date and revisions.

Keep market-wide FII/DII flows separate from stock-specific institutional evidence. Distinguish direct verified evidence, indirect accumulation-like behaviour and unavailable data.

**Exit condition:** source-attributed evidence model and historical examples. No label of “institutional accumulation confirmed” without direct stock-specific proof.

### Phase 5 — Operator/trap and surveillance-risk research

Research candidate signals such as:
- extreme one-day volume vs rolling mean and median;
- high effort with little/no price progress;
- repeated upper-wick rejection and weak closes;
- gap-up reversal and failed breakout;
- high delivery with multi-session price deterioration;
- delivery/price divergence;
- thin liquidity and exit-risk proxies;
- repeated upper circuits or price-band constraints;
- distribution-like patterns across multiple sessions.

Cross-check official exchange surveillance and trading restrictions where available (ASM, GSM, ESM, Trade-to-Trade, Periodic Call Auction, price bands and relevant exchange notices). Verify current lists and effective dates from official sources.

**Exclusion policy:** only a validated severe-risk rule or corroborated combination of signals can trigger `TRAP_RISK_HIGH` and exclude from the normal shortlist. Preserve all exclusions in a separate audit ledger. A single upper wick, isolated spike, missing field or unavailable source is not sufficient by itself. Unknown status must remain UNKNOWN/NOT_VERIFIED, not LOW_RISK.

**Exit condition:** historical false-positive/false-negative analysis, documented evidence thresholds and explicit reason codes approved before enabling exclusion.

### Phase 6 — Technical entry-readiness research

Research:
- 20/50-session trend and market regime;
- Nifty and sector relative strength;
- breakout level and resistance quality;
- breakout volume vs historical baseline;
- retest/hold behaviour;
- closing strength and supply pressure;
- support/invalidation and gap risk;
- liquidity and practical exit feasibility;
- risk/reward and setup freshness.

Possible statuses: ENTRY_SETUP_READY, BREAKOUT_CONFIRMATION_PENDING, WAIT_FOR_RETEST, EXTENDED_DO_NOT_CHASE, TECHNICAL_SETUP_WEAK. These are research states, not orders.

**Exit condition:** reproducible setup definitions and historical forward-outcome tests, including failed breakouts.

### Phase 7 — Balanced research decision model

Only after Phases 0–6 are evidenced:
- define transparent independent assessments for fundamentals, footprint, trap risk and technical readiness;
- preserve fundamental PASS/FAIL/WAIT without overrides;
- exclude validated high-trap-risk candidates from the normal shortlist;
- keep unverified candidates in a separate verification-pending list;
- avoid a single opaque weighted score;
- document every inclusion/exclusion reason and supporting source;
- test sector and liquidity biases, survivorship bias and look-ahead bias.

### Phase 8 — Shadow deployment and acceptance

- Run in ECMS-only shadow mode and keep the existing Morning/EOD page comparison untouched.
- Compare outputs with historical forward returns and manually reviewed examples.
- Measure coverage, false exclusions, missed traps, failed-breakout rate, data freshness and end-to-end runtime.
- Verify Telegram/report completeness and cache continuity.
- Enable any new exclusion rule only after tests and user review.
- Do not merge to main or alter production NSE V8 without explicit approval.

## 4. Required data status vocabulary

Use distinct states, as applicable:
- `DATA_FOUND`
- `NO_DATA_FOUND` (source checked successfully, no matching disclosure)
- `SOURCE_UNAVAILABLE`
- `NOT_VERIFIED`
- `STALE_DATA`
- `CONFLICT`
- `NOT_APPLICABLE`

No data, unavailable data and conflicting data must never be silently treated as a negative event, a clean bill of health or a trap confirmation.

## 5. Required outputs

1. Repository/workflow audit report.
2. Data-source catalogue and field dictionary.
3. Per-source and per-field coverage report.
4. Historical price/volume/delivery research dataset.
5. Per-stock seven-metric fundamental evidence report.
6. Institutional-footprint evidence report.
7. Trap-risk assessment and separate exclusion ledger.
8. Technical entry-readiness report.
9. Balanced final shortlist with traceable reasons.
10. Morning/EOD regression-test evidence and runtime/Telegram audit.

## 6. Hard boundaries

- Do not change the current two-scan schedule or existing Morning/EOD comparison semantics.
- Do not edit `.github/workflows/nse-test-scheduled.yml`, NSE V8 strategy files, shared thresholds/providers or production cache behaviour.
- Keep ECMS-owned cache and output isolated under `data/cache/ecms/` and `outputs/ecms/`.
- Do not add per-symbol network-fetch loops where a batch source is available.
- Do not add unverified data, invented values or inferred institutional identities.
- No broker connection, order placement or automated execution.

## 7. Audit outcome and evidence boundary

The initial ECMS repository/workflow/data audit has been recorded in:

- `docs/ECMS_REPOSITORY_DATA_AUDIT_2026-11-16.md`

The audit found that the existing scanner foundation and date-comparison logic are useful, but the current active Volume Gainers path does not yet provide delivery-history accumulation, multi-quarter institutional ownership trends, promoter pledge trend, official surveillance risk, operator-trap assessment or technical entry readiness.

The latest detailed live EOD artifact available during the audit was Run #335, head `012bd9e79eaee71a385f4cbcae2c77949faa855b`, which predates PR #139. It showed 23 eligible Main Board stocks, missing page volume for 23/23, 20/23 with all seven metric values populated, 17 officially verified metric observations, 25 mismatch observations and 23 WAIT_FOR_DATA assessments. News was found for 19, events for 7, bulk/block deals for 3, and the dedicated corporate-actions feed returned no rows. This is a historical baseline, not proof of current post-PR-#139 live behaviour.

PR #139's scan-date and source-schema changes passed CI (121 tests), but the audit did not find a post-merge live Morning/EOD run. The next live evidence must verify the current merged code before any new module is enabled.

## 8. Audit-based implementation order

The original conceptual phases remain, but the actual implementation order is now data-first and adjusted to the measured gaps:

1. **P0 — Protect and reconcile the existing ECMS baseline.**
   - Add/lock regression tests for both comparison legs, session dates, holiday skip, cache restoration and separate Morning/EOD reports.
   - Route ECMS Main Board/SME list caching into an ECMS-owned directory; the current shared helper writes under `data/cache/universe/`, contrary to the read-only contract.
   - Reconcile `WORKFLOW_CONTRACT.md` EOD time (16:45) with the active 17:00 workflow.
   - Record the current fundamental-only tests that must change only when the approved trap exclusion is implemented.
   - Keep comparison semantics and all production NSE V8 files untouched.

2. **P1 — Repair data provenance and coverage reporting.**
   - Make the per-stock/per-metric report show the actual value source, URL, period, basis and unit separately from the official verification source/status.
   - Resolve provenance from metric-level maps, not one stock-level period/basis.
   - Separate primary fundamental provider refresh from secondary-source research cooldown.
   - Add source-wise coverage, attempt counts, cache age, last successful fetch, last failed fetch and reason codes.
   - Include the two currently omitted ECMS test files in CI validation.

3. **P2 — Build the price/volume/delivery historical dataset.**
   - Validate current NSE page volume aliases using a post-PR-#139 artifact.
   - Resolve a trustworthy source for traded quantity/value when the page does not expose it.
   - Collect 5/10/20/30-session OHLCV, delivery quantity, delivery percentage, delivered value, volume mean/median, RVOL and average traded value.
   - Preserve session dates, adjusted/unadjusted status, units, symbol mapping and source coverage.
   - Do not compare partial Morning volume directly with completed-day baselines.

4. **P3 — Activate stock-specific ownership and institutional research.**
   - Reuse and audit the existing NSE SHP XBRL parser.
   - Store quarterly promoter, FII, DII and public holding history with exact filing and reporting-period identity.
   - Research promoter pledge through a separately validated official disclosure source; current SHP parser does not map pledge.
   - Add stock-specific insider/PIT/SAST disclosures and bulk/block deal context.
   - Do not infer institutional identity from delivery or market-wide FII/DII flows.

5. **P4 — Improve company-event and disclosure research.**
   - Preserve the five-session announcement/news, 90-day event/board-meeting, 30-day deal and corporate-action windows.
   - Keep batch endpoints batch-based.
   - Add a bounded EOD incremental refresh after Morning for news and corporate actions so newly published disclosures are not missed when a complete Morning cache is reused.
   - Add fetched-at/TTL and source-coverage metadata to exact-window caches.
   - Deduplicate revisions and disclosures without losing the original filing identity.

6. **P5 — Build surveillance and trap-risk research.**
   - Collect current official ASM/GSM/ESM, Trade-to-Trade, Periodic Call Auction and price-band status with effective dates.
   - Combine abnormal volume, effort-without-result, upper-wick rejection, gap reversal, failed breakout, delivery/price divergence, multi-session distribution and liquidity evidence.
   - First run shadow-only; validate historical false positives and missed traps.
   - Apply the user-approved exclusion only for a validated severe-risk rule or corroborated multi-signal rule. Keep a separate exclusion ledger.

7. **P6 — Build technical entry-readiness research.**
   - Add 20/50-session trend, Nifty/sector relative strength, breakout/retest/hold, closing quality, supply pressure, support/invalidation, gap risk, liquidity and risk/reward.
   - Keep entry readiness separate from fundamental status and institutional evidence.
   - No automated order or buy instruction.

8. **P7 — Balanced candidate decision model.**
   - Combine fundamentals, verified footprint, low trap risk and technical readiness as separate evidence dimensions.
   - Fundamental FAIL cannot be overridden. Fundamental WAIT remains WAIT.
   - High trap risk is excluded from the normal shortlist with reason and evidence preserved.
   - NOT_VERIFIED/SOURCE_UNAVAILABLE stays verification-pending, never low-risk.
   - Avoid one opaque weighted score; document all reasons.

9. **P8 — Shadow validation and operational sign-off.**
   - Validate historical forward outcomes, false exclusions, failed-breakout rate, data freshness, cache continuity, Telegram completeness and actual runtime.
   - Complete a live post-PR-#139 EOD -> next-session Morning -> same-day EOD cycle.
   - Enable exclusion/priority rules only after evidence review and explicit user approval.

## 9. Next action

Start with **P0 and P1 only**, on this isolated branch, one small reviewed PR at a time. First complete the exact code/test/source-lineage audit and baseline regression tests. Then correct cache isolation and metric-level provenance. Do not begin footprint scoring, trap exclusion or entry-readiness scoring until the relevant historical data and source coverage have been collected and verified.

**P0 implementation update (16 Nov 2026):** draft PR [#140](https://github.com/digitalmf78-pixel/AI-Trading-Bot/pull/140) adds an optional cache-directory argument to the shared Main Board helper while preserving its production default, routes ECMS to `data/cache/ecms/universe/`, persists that ECMS cache in the two ECMS state-cache handoffs, adds the omitted ECMS tests to CI, adds a cache-isolation regression test, and aligns the workflow contract with the active 17:00 IST cron. A separate Friday/Monday/holiday date regression test is being added. The first PR validation run passed **128 tests** before that additional date test. Morning/EOD comparison code was not changed. PR #140 remains draft/unmerged; no live schedule or production NSE V8 behaviour has changed.
