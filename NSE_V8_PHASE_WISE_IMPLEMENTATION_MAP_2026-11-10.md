# NSE V8.0 — Phase-wise Implementation Map
**Date:** 10-Nov-2026  
**Repository:** digitalmf78-pixel/AI-Trading-Bot  
**Base:** main  
**Working branch:** audit/implementation-roadmap-2026-11-10

## Change-control rules
- The original `Pasted text(20261009-143842).txt` Master Specification remains immutable.
- This map is an execution plan; it does not authorize changes to existing production thresholds or gates.
- Preserve current Delivery A/B, RVOL, Liquidity, Fundamentals collection boundary, RSI, technical confirmations and risk controls.
- New observations must remain observational until a specific numeric gate is explicitly approved.
- Missing, stale, ambiguous or incomplete evidence must be represented as WAIT_FOR_DATA; never infer missing facts.
- Do not commit secrets, tokens, user data or live credentials.
- Implement and validate on this branch; do not merge to main automatically.

## Verified current code baseline
- `delivery_quantity_analysis.py`: 5/10/20 report-session quantity totals/averages, first/last, percentage change and OLS slope; also available Delivery %, volume and price observations.
- `potential_accumulation_analysis.py`: rolling 20/50/100/200-session price-range observations; not yet a fixed-range base classifier.
- `vcp_observation_analysis.py`: three sequential 20-session blocks (60 sessions) and contraction/volume observations; observational only.
- `breakout_retest_observation.py` and `hybrid_watchlists.py`: breakout/retest observations and separate early, breakout-ready and confirmed-entry watchlist outputs.
- `news_catalyst.py`: NSE official RSS plus secondary coverage; news window currently logs 5 calendar days. It also extracts explicit future event dates from issuer-filtered official announcements and writes `outputs/v8_upcoming_corporate_events.csv`; the event report records a 90-day announcement lookback.
- `volume_gainer.py`: integrates the observation modules into the EOD scanner and sends the Marathi Telegram digest.
- `test_upcoming_corporate_events.py`: tests explicit future-date parsing, past-date handling, irrelevant announcement exclusion and one status row per candidate.
- `NSE_V8_HYBRID_STRATEGY_MASTER_PARAMETERS_2026-11-09.md` and README are the working implementation references. The original master spec remains authoritative.

## Phase 0 — Baseline and evidence lock
**Status: IN PROGRESS**
1. Record the current main commit and workflow state.
2. Preserve the last known-good EOD output counts as a comparison baseline (not as permanent expected values).
3. Map every requested item in the implementation-log TXT to current source files, tests, outputs and status.
4. Confirm no production code or main-branch files are modified during the mapping stage.

**Exit criteria:** traceable requirement-to-code/test/output matrix.

## Phase 1 — Delivery and accumulation evidence
**Status: PARTLY IMPLEMENTED; audit and improve**
1. Reuse the existing 30-calendar-day NSE Delivery data already fetched by the scanner; do not add duplicate report downloads.
2. Audit quantity, Delivery %, traded volume and price-response calculations for date integrity, units, missing sessions and symbol uniqueness.
3. Add explicit evidence views for sideways/range behaviour and dip/pullback behaviour, while preserving existing Potential Accumulation output.
4. Keep all classifications observational. Do not create a numeric BUY/rejection gate without approved parameters.
5. Test high Delivery % without quantity expansion, quantity expansion with falling price, stable-price high-delivery sessions, duplicate dates, missing data and insufficient history.

**Exit criteria:** auditable per-symbol evidence with source dates, raw values, calculation windows, status and reason.

## Phase 2 — Base and VCP
**Status: PARTLY IMPLEMENTED; audit and improve**
1. Preserve current three-block 20-session observation model.
2. Map fixed-range Base High/Low/width/duration separately from rolling range observations.
3. Record contraction sequence, range narrowing, volume dry-up and pivot proximity.
4. Keep the <0.5x volume dry-up ratio observational only.
5. Do not invent contraction depth/count, base-width/duration or VCP pass thresholds.
6. Add tests for incomplete windows, duplicate dates, price gaps, non-contracting ranges and missing volume.

**Exit criteria:** separate Base and VCP observation records with WAIT_FOR_DATA handling; no unapproved hard gate.

## Phase 3 — News and Upcoming Events
**Status: PARTLY IMPLEMENTED; verify against user-provided implementation log**
1. Preserve NSE official sources as primary evidence and secondary sources as corroboration only.
2. Align the news lookback to the specified 7 calendar days if confirmed by the supplied implementation log; do not change issuer matching or official-verification rules.
3. Keep the event-announcement discovery lookback distinct from the upcoming-event horizon.
4. Implement/validate the specified next-20-calendar-day event horizon if supported by the supplied log, using only explicit official event dates.
5. Preserve separate statuses for confirmed official event, no matching event found, and WAIT_FOR_DATA.
6. Add boundary tests at day 0, day 7, day 20, past dates, missing event dates, issuer mismatch and failed official-source coverage.

**Exit criteria:** reproducible news and event reports with separate announcement and event-date windows; no guessed dates.

## Phase 4 — Institutional and fundamental evidence enrichment
**Status: PLANNED**
1. Map available official bulk/block deal, shareholding, promoter pledge and insider disclosures.
2. Preserve source, publication date, reporting period, exact issuer/symbol match and verification status.
3. Keep secondary provider values explicitly unverified until reconciled with official filings.
4. Do not move fundamental collection ahead of the approved Liquidity boundary.
5. Do not infer a named institutional buyer from Delivery data alone.

**Exit criteria:** source-attributed evidence and explicit verified/unverified/WAIT statuses.

## Phase 5 — Daily lifecycle and Telegram reporting
**Status: PLANNED**
1. Audit existing four independent watchlists: Potential Accumulation, Base/VCP Forming, Breakout Ready and Confirmed Entry.
2. Persist daily status transitions and reasons without deleting earlier-stage observations when later stages are absent.
3. Add the requested report sections to Marathi Telegram digest without exceeding Telegram message limits.
4. Preserve Telegram acknowledgement checks and retries.
5. Test empty data, partial data, multi-message delivery and stable ordering.

**Exit criteria:** four distinct watchlist outputs and a complete, auditable Marathi report.

## Phase 6 — Historical validation and performance
**Status: PLANNED**
1. Validate against the available ~200 complete distinct NSE sessions; do not redownload valid cache.
2. Evaluate Largecap, Midcap and Smallcap coverage, data gaps and survivorship/selection bias.
3. Calculate forward 5/10/20-session MFE/MAE using only future data after each signal date.
4. Report conversion rates between watchlist stages, win rate, average R, drawdown, fees and slippage assumptions.
5. Separate descriptive results from statistically supported conclusions.
6. Run full unit, regression, data-integrity and EOD workflow tests.

**Exit criteria:** reproducible historical report with assumptions, coverage and limitations.

## Decisions that must not be guessed
- Numeric weights/scores and thresholds for sideways/dip accumulation.
- Exact fixed-base width/duration and VCP contraction count/depth.
- Pocket Pivot formula and lookback.
- False-breakout buffer and retest window.
- Event materiality ranking and catalyst priority weights.
- Any change to the existing EMA44 gate, Liquidity minimum, Delivery A/B, RVOL, Fundamentals boundary, 3+1 confirmation or risk controls.

## Working protocol
For each phase: **Requirements → Code Mapping → Implementation → Unit Tests → Historical/Data Tests → Workflow Validation → Evidence Log**.
Only claim a task complete when the code, tests and produced artifacts demonstrate it. Keep changes isolated on this branch and review the diff before proposing a PR.
