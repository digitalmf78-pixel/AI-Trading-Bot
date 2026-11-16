# ECMS Research Roadmap — Audit First

**Status:** Planning baseline; implementation is blocked until the repository/data audit is complete.  
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

## 7. Immediate next action

Complete Phase 0 first. Inspect the full repository implementation, tests, workflow history and available run artifacts. Then revise this roadmap using measured findings and source research. Only after the revised audit-backed roadmap is reviewed should implementation proceed phase by phase.

**This document records the agreed direction; it is not authorization to change live selection logic or merge new strategy code.**
