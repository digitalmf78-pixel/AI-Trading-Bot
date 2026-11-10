# NSE V8.0 — Phase-wise Implementation Map
**Date:** 10-Nov-2026  
**Source plan:** `NSE_V8_Master_Implementation_Log_News_Events_2026-11-09.txt` (Version 1.1)  
**Repository:** digitalmf78-pixel/AI-Trading-Bot  
**Base:** main  
**Working branch:** audit/implementation-roadmap-2026-11-10

## Change-control rules
- The original `Pasted text(20261009-143842).txt` Master Specification remains immutable.
- The 09-Nov implementation log defines the approved high-level direction and phase order; this map translates it into code/test work.
- Preserve Track 1 Delivery A/B, RVOL, Liquidity, approved Fundamentals boundary, RSI, technical confirmations and risk controls.
- Track 2 is an independent full-Mainboard early research track; it must not bypass or modify Track 1 eligibility.
- Early Accumulation and news/events are research/context, not BUY signals.
- Numeric scores/weights and pending thresholds require backtest and explicit user approval.
- Missing, stale, ambiguous or incomplete evidence must be represented explicitly; never infer missing facts.
- Do not commit secrets, tokens, user data or live credentials.
- Implement and validate on this branch; do not merge to main automatically.

## Verified current code baseline
- `delivery_quantity_analysis.py`: 5/10/20 report-session quantity totals/averages, first/last, percentage change and OLS slope; also records Delivery %, traded-volume and price observations where available.
- `potential_accumulation_analysis.py`: rolling 20/50/100/200-session price-range observations; not yet a distinct Sideways/Dip classification engine.
- `vcp_observation_analysis.py`: three sequential 20-session blocks (60 sessions) and contraction/volume observations; observational only.
- `breakout_retest_observation.py` and `hybrid_watchlists.py`: breakout/retest observations and separate early, breakout-ready and confirmed-entry watchlist outputs.
- `news_catalyst.py`: NSE official RSS plus secondary coverage; news window currently logs 5 calendar days, while requested window is 7. It extracts explicit future event dates from issuer-filtered official announcements and writes `outputs/v8_upcoming_corporate_events.csv`; current report records a 90-day announcement lookback, not a 20-day event horizon.
- `volume_gainer.py`: integrates observation modules into EOD scanner and sends Marathi Telegram digest.
- `test_upcoming_corporate_events.py`: tests explicit future-date parsing, past-date handling, irrelevant announcement exclusion and one status row per candidate.
- Current README and hybrid register are implementation references. Original master spec remains authoritative.

## Phase 0 — Live repository baseline audit
**Status: COMPLETED FOR INITIAL AUDIT; evidence matrix still being finalized**
- Main branch and relevant source modules inspected; baseline EOD figures retained as comparison values, not fixed expectations.
- Working branch created: `audit/implementation-roadmap-2026-11-10`.
- This roadmap was committed on the working branch only. No production source or main-branch file was changed.
- Remaining audit evidence: current workflows, cache coverage by 5/10/20/30/90/200 sessions, Telegram actual-send path, latest artifacts and full Track 1 regression baseline.

## Phase 1 — Data contracts and canonical schemas
**Status: IN PROGRESS**
1. Map current symbol/company mapping and canonical symbol identity.
2. Define compatible records for Delivery, price/volume, Fundamentals, institutional evidence, news and events.
3. Ensure every record carries as-of date/time, source, publication/reporting period, fetch/first-seen/last-checked time, freshness, verification, coverage and missing-data status as applicable.
4. Use IST for exchange-facing timestamps; preserve source timestamp and timezone.
5. Define duplicate identity and revision/cancellation handling for news/events.
6. Keep existing CSV outputs backward-compatible unless a separately versioned output is introduced.
**Exit criteria:** schema/data-contract matrix and tests for timezone, source provenance, duplicate identity and missing values.

## Phase 2 — Historical Delivery data audit
**Status: PLANNED**
1. Preserve 30-day Delivery A/B eligibility unchanged.
2. Measure actual per-symbol and archive coverage for 5/10/20/30/90/200 distinct sessions.
3. Separate exchange report availability from Bhavcopy session coverage.
4. Verify date uniqueness, symbol mapping, session calendar, cache freshness and source completeness.
5. Propose a separate backfill only if actual coverage proves it necessary; do not fabricate or substitute values.
**Exit criteria:** dated coverage report and a safe backfill proposal, if required.

## Phase 3 — Early Accumulation Research Engine
**Status: PARTLY IMPLEMENTED; SIDEWAYS/DIP ENGINE NOT YET COMPLETE**
1. Run independently across the full eligible NSE Mainboard research universe, subject to verified source coverage.
2. Build two independent observational types: SIDEWAYS_ACCUMULATION and DIP_ACCUMULATION.
3. Use 5/10/20/30-session windows; use 90/200 only where actual history exists.
4. Combine Delivered Quantity, Delivered Value, Delivery %, total traded volume, volume baseline, return/range/close location, up-day/down-day delivery and price response.
5. Distinguish accumulation evidence from distribution/forced selling; a one-day spike or high Delivery % alone is insufficient.
6. Delivered Value must use a reliable price and quantity; label estimates ESTIMATED.
7. Keep this track independent from Track 1 A/B selection; no A/B bypass and no new rejection gate.
8. Test one-day spikes, falling price, thin volume, stale data, missing sessions, corporate actions and false positives.
**Exit criteria:** separate Sideways and Dip reports with raw evidence, dates, coverage, source and reasons.

## Phase 4 — Fundamental Enrichment
**Status: PARTLY IMPLEMENTED; AUDIT REQUIRED**
1. Audit provider coverage, cache reuse, quarterly/TTM period alignment and stale-data handling.
2. Preserve per-field source, reporting period, fetch date and official/secondary/verified/unverified/partial/missing status.
3. Do not interpret missing values as zero or drop candidates because data is missing.
4. Preserve the currently approved collection boundary after Liquidity; do not change fetch order without explicit user approval.
5. Keep valuation metrics as context, not unsupported hard gates.
**Exit criteria:** field-level diagnostics and cache/period-integrity tests.

## Phase 5 — Institutional Evidence
**Status: PLANNED**
1. Audit sources for Bulk Deals, Block Deals, shareholding pattern, MF/FII/FPI holding changes, promoter holding/pledge and insider/PIT/SAST disclosures.
2. Preserve stock-specific disclosures separately from market-wide FII/DII context.
3. Handle revisions, duplicate filings, exact symbol matching, publication dates and reporting periods.
4. Do not infer stock-specific institutional activity from aggregate FII/DII flows or Delivery alone.
**Exit criteria:** source-attributed stock-level evidence with explicit coverage and verification states.

## Phase 6 — News Engine
**Status: PARTLY IMPLEMENTED; 7-DAY WINDOW GAP IDENTIFIED**
1. Fetch relevant news from the preceding 7 calendar days on each daily run.
2. Preserve official filings as primary and media/secondary reports as corroboration.
3. Add/verify symbol mapping, duplicate/syndicated-copy detection and first-seen vs published-time handling.
4. Classify POSITIVE, NEGATIVE, NEUTRAL, MIXED or UNVERIFIED with source and short impact rationale.
5. Track post-news price, volume and Delivery reaction without claiming causation.
6. Ensure a republished old story is not treated as a new catalyst.
**Exit criteria:** 7-day point-in-time news set with tested boundaries and issuer/source integrity.

## Phase 7 — Upcoming Events Engine
**Status: PARTLY IMPLEMENTED; 20-DAY HORIZON GAP IDENTIFIED**
1. Report events occurring in the next 20 calendar days.
2. Cover results, board meetings/purpose, dividend/record/ex-date, bonus, split, buyback, AGM/EGM, investor/analyst meetings, orders/contracts, fundraising, M&A, approvals, expansion/capex and other material announcements.
3. Store event type, announcement date, event date, purpose, source, days remaining and status.
4. Track changed, cancelled and postponed dates as history; never overwrite the previous event state.
5. Unknown dates remain DATE_NOT_CONFIRMED; do not infer.
6. Keep the announcement discovery lookback distinct from the upcoming-event horizon.
7. Add event proximity risk labels; materiality taxonomy remains pending approval.
**Exit criteria:** next-20-day event report with source-backed dates, history and boundary tests.

## Phase 8 — Catalyst Priority and Watchlist Lifecycle
**Status: PLANNED; NUMERIC SCORING PENDING**
1. Present catalyst, accumulation, fundamentals and institutional evidence together without conflating their verification states.
2. Use the proposed P1–P6 buckets only as a display proposal until criteria are approved.
3. Do not implement numeric weights before historical backtest and user approval.
4. Persist daily status transitions and historical snapshots.
5. Keep Early Opportunity distinct from Trade Ready; news/events cannot promote a stock automatically.
**Exit criteria:** auditable state transitions and user-approved display/priority rules.

## Phase 9 — Telegram Reporting
**Status: EXISTING DIGEST; REQUIRED FOUR-SECTION LAYOUT NOT COMPLETE**
1. Section 1: Upcoming Catalyst Opportunities.
2. Section 2: Early Accumulation (Sideways and Dip).
3. Section 3: Trade Ready.
4. Section 4: Negative/Risk Alerts.
5. Include source/date, event/news status, Delivery/quantity/value context, fundamentals period/status, institutional evidence and missing-data/risk notes.
6. Use compact summaries plus paginated detail when message limits require it.
7. Verify actual Telegram delivery and message content; code payload alone is not proof.
**Exit criteria:** actual Telegram messages show all four sections with correct order and data provenance.

## Phase 10 — Backtest / Shadow Run
**Status: PLANNED**
1. Use point-in-time historical inputs; prevent look-ahead bias.
2. Record survivorship bias, fees, slippage, corporate actions, event timing and data gaps.
3. Evaluate early watchlist progression and 5/10/20-session MFE/MAE.
4. Do not describe scanner output as a profit guarantee.
**Exit criteria:** reproducible historical and shadow reports with assumptions and limitations.

## Phase 11 — Release and Verification
**Status: PLANNED**
- Track 1 regression tests pass and outputs match baseline within explained data changes.
- Track 2/3/4 tests pass.
- GitHub Actions succeeds.
- Actual EOD artifact and Telegram output reviewed.
- Cache persistence and secret safety verified.
- Only then prepare a PR for user review; no automatic merge.

## Decisions that must not be guessed
- Numeric weights/scores and P1–P6 priority thresholds.
- Sideways/Dip numeric thresholds and minimum evidence requirements beyond those already in the source plan.
- Exact fixed-base width/duration and VCP contraction count/depth.
- Pocket Pivot formula/lookback, false-breakout buffer and retest window.
- Event materiality ranking and source/provider quotas.
- Any change to Delivery A/B, RVOL, Liquidity, Fundamentals boundary, EMA44 gate, 3+1 confirmation or risk controls.

## Working protocol
For each phase: **Requirements → Code Mapping → Implementation → Unit Tests → Historical/Data Tests → Workflow Validation → Evidence Log**.
Only claim a task complete when code, tests and produced artifacts demonstrate it. Keep changes isolated on this branch and review the diff before proposing a PR.
