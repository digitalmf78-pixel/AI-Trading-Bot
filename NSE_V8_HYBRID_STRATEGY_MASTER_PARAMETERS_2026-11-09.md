# NSE Swing Trading System V8.0 — Hybrid Strategy Working Parameter Register

**Updated:** 09 November 2026  
**Repository:** `digitalmf78-pixel/AI-Trading-Bot`  
**Branch:** `main`  
**Purpose:** Persistent working reference for the approved Smart-Money Footprint + Accumulation + VCP + Breakout hybrid work. Read this file and the original Master Specification before every future project task so the user does not need to repeat decisions.

> **Authority and change control**
> - The original `Pasted text(20261009-143842).txt` / `NSE SWING TRADING SYSTEM V8.0` remains the immutable source of truth. Do not rewrite or replace it.
> - This register records the hybrid strategy decisions, implementation sequence, audit findings and unresolved parameters. It supplements, and does not silently override, the original Master Specification or existing production gates.
> - Existing thresholds and filters must remain unchanged unless the user explicitly approves a change.
> - Distinguish **CONFIRMED/KEEP**, **OBSERVATIONAL ONLY**, and **PENDING DECISION**. Never turn an observational metric or pending proposal into a rejection gate.
> - Missing/invalid evidence is `WAIT_FOR_DATA`, never PASS. Do not invent values or claim institutional buyer identity from NSE Delivery data.

## 1. Current priority and scope

Build and validate the **Accumulation + VCP + Breakout Hybrid** first, in phases. The aim is to detect evidence consistent with potential large-buyer activity, price-base formation, volatility contraction, breakout and retest/pullback.

The four separate outputs are:
1. **Potential Accumulation** — delivery quantity/percentage, traded volume and price-stability evidence. This is not a buy signal.
2. **Base / VCP Forming** — fixed-range consolidation, contraction and volume dry-up.
3. **Breakout Ready** — predefined resistance, breakout/pivot and confirmation observations.
4. **Confirmed Entry** — only after the applicable existing entry confirmations, structural stop, reward/risk and risk controls pass.

**Do not work on or change Sector Strength, News/Catalyst, or mandatory 3+1 confirmation during the initial Accumulation/VCP/Breakout phases.** Preserve those existing modules and their current rules. Their integration belongs to the later confirmation/risk phase; do not remove or weaken them.

## 2. Existing production rules — KEEP UNCHANGED

### Universe and historical data
- Include eligible NSE Mainboard Largecap, Midcap and Smallcap stocks. Do not exclude a stock merely because it is Midcap or Smallcap.
- Exclude SME stocks, ETFs and Mutual Funds.
- Reuse the available approximately 200 complete NSE trading-session Bhavcopy history/cache; do not redownload valid cached sessions unnecessarily.
- No Top-20 or Top-50 shortlist cap.
- Use the official NSE trading calendar, including notified special sessions. Missing data on an actual session is `WAIT_FOR_DATA`.

### Delivery A/B — current authoritative eligibility rule
- Lookback: the 30 calendar days ending on and including the EOD as-of date.
- Count only distinct, valid NSE Delivery report dates not later than the as-of date.
- Require at least 5 valid distinct reports; otherwise `WAIT_FOR_DATA`.
- **Category A:** arithmetic average Delivery % across all valid reports in that 30-calendar-day window is **>=60.00%**. Exactly 60.00% passes.
- **Category B:** every valid report's Delivery % in that same window is **>=60.00%**. Exactly 60.00% passes.
- Evaluate A and B independently. Eligibility is **A OR B**. Preserve A_ONLY and A_AND_B membership/status and avoid duplicate symbols.
- Keep the existing 5D/10D/20D consistency fields observational; they must not silently replace the 30-calendar-day A/B rule.

### RVOL
- RVOL = current EOD total traded volume / average volume of the previous 20 complete trading sessions. Exclude the current session from the baseline.
- `RVOL > 1.5` = `HIGH_RVOL_GT_1_5`; `RVOL <= 1.5` = `LOW_RVOL_LE_1_5`; missing/invalid = `WAIT_FOR_DATA`.
- RVOL threshold is classification/information, **not an eligibility rejection gate**. Do not drop Delivery-qualified stocks because RVOL is <=1.5 or unavailable.

### Liquidity
- Existing hard minimum: 20-session average daily traded value **>=₹1.5 crore**.
- Tiers: **STRONG >=₹5 crore/day**; **MEDIUM ₹2 crore to <₹5 crore/day**; **LOW ₹1.5 crore to <₹2 crore/day**.
- ₹5 crore is not the hard minimum. Do not raise the existing ₹1.5 crore threshold without approval.
- A separate below-₹1.5 crore shadow list is a pending decision, not an active production path.

### Fundamentals and cache
- Fundamentals are enrichment/classification/priority/risk context, not an early rejection gate.
- Do not apply a Strong Fundamental gate before data collection. Missing metrics must remain visible with explicit statuses; do not silently drop candidates.
- Fundamental cache must persist inside this GitHub repository, be reused across runs, retain historical snapshots and official verification status, and refresh when a new quarterly reporting period becomes available.
- Use official filing verification with exact symbol, exact period-end and valid publication/as-of timing. Unresolved values remain unverified/WAIT.
- **Pending boundary decision:** whether to collect fundamentals for every unique Delivery A/B stock before liquidity, or retain the current Liquidity-first collection boundary. Do not change this boundary until explicitly resolved.

### RSI
- RSI is informational only. It must not reject stocks or apply an eligibility/score penalty.

## 3. Hybrid accumulation evidence

For each symbol, build a dated, auditable observation set using:
- Absolute **Delivery Quantity** trend.
- Total traded volume.
- Delivery Percentage.
- Joint interpretation of all three; never infer accumulation from Delivery % alone.
- Price stability/price response on high-delivery sessions (e.g. whether price holds a range/support despite high delivered quantity; record the actual measurements rather than asserting a buyer identity).
- Fixed-range base: **Base High, Base Low, base width and base duration**.
- Repeated tests/rejections/holds at support and resistance.
- Higher Low and Double Bottom structures.
- Selling-pressure trend and subsequent price response.
- Preserve per-session source dates, raw values, calculation windows, status and reason.

Use the label **Potential Accumulation Evidence**. Do not label it “Institutional Accumulation Confirmed”; NSE Delivery data does not identify the buyer.

## 4. VCP and consolidation

Observe independently:
- Successive contraction depth/price-range sequence.
- Narrowing trading range.
- Declining volume / volume dry-up.
- Price proximity to the predefined resistance/base pivot.
- Fixed-range base and VCP are separate observations; neither is a substitute for the other.

Statuses:
- `VCP_CONFIRMED`
- `VCP_FORMING`
- `NO_VCP`
- `WAIT_FOR_DATA`

A stock without VCP must **not** be rejected from Potential Accumulation Watch.

A volume dry-up ratio may be reported as current/period volume divided by the previous 20-session average. A value below **0.5x** may be shown as an **observational flag only**; it is not an approved hard gate and must not reject a candidate by itself.

Exact contraction count/depth, base width and duration thresholds remain pending (see Section 10).

## 5. Trend and moving-average observations

- **EMA20:** short-term support and low-supply/pullback context.
- **EMA44:** existing V8 technical trend context; preserve current logic.
- **EMA50:** medium-term trend observation.
- **EMA200:** long-term trend observation.
- Do not automatically reject an accumulation candidate merely because price is below EMA44, EMA50 or EMA200.
- Distinguish:
  - **Early Accumulation:** may form below EMA200.
  - **Strong Trend Consolidation:** close above EMA50 and EMA200.
- Stronger trend requirements may apply to later entry-ready outputs, but must not become an unnecessary gate for early accumulation observation.
- Any change to the existing EMA44 production gate requires explicit approval.

## 6. Breakout, retest and Pocket Pivot

- Define and persist the resistance/pivot level before evaluating breakout.
- Measure closing price relative to that level, volume expansion, and a separately specified false-breakout buffer.
- After breakout, detect whether a retest/pullback occurs; assess whether selling volume contracts during the retest.
- Pocket Pivot is a separate signal, not a synonym for a generic volume surge.
- Proposed Pocket Pivot concept: compare an up-day's volume with the maximum volume of recent down-days. Exact lookback, candle conditions, adjustment/edge cases and formula are **not yet approved**; do not code an arbitrary formula as final.
- False-breakout buffer and retest window remain pending decisions.

## 7. Watchlists and statuses

Maintain four separate watchlists; do not collapse them into one final-entry list:
1. `Potential Accumulation`
2. `Base / VCP Forming`
3. `Breakout Ready`
4. `Confirmed Entry`

Persist clear reason codes and audit fields. Recognized statuses:
- `ACCUMULATION_WATCH`
- `BASE_FORMING`
- `BREAKOUT_CONFIRMED`
- `PULLBACK_CONFIRMED`
- `ENTRY_CANDIDATE`
- `WAIT_FOR_DATA`
- `NO_SETUP`
- `CHASED`

An accumulation/base watch is not a BUY signal. A stock may legitimately appear in an earlier-stage watchlist while failing later entry gates.

## 8. Later V8 confirmation and risk integration — preserve, do not change now

At the later integration phase, preserve existing:
- Sector confirmation and exact-date sector history.
- Verified news/catalyst evidence; unverified news is not confirmed.
- Mandatory 3+1 confirmation logic from the Master Specification.
- Structural stop-loss, minimum 2R risk/reward, Chase filter, Risk Control and position-sizing inputs.
- Calculate 2R from real structural levels. Never synthesize a target/default 2R value when no verified resistance exists.
- Missing evidence remains `WAIT_FOR_DATA`.

These modules are out of scope for the initial hybrid build; do not refactor or weaken them while implementing accumulation, base/VCP, EMA observations or breakout detection.

## 9. Current code-audit findings (09-Nov-2026)

Read-only mapping against GitHub `main`:
- Mainboard classification, 200-session Bhavcopy reuse, 30-calendar-day Delivery A/B, RVOL classification, ₹1.5 crore liquidity, persistent fundamental cache and existing EMA20/EMA44 context are present.
- Existing Bottom Detection includes support proximity, confirmed pivot lows, Higher Low, Double Bottom, bullish candle, volume confirmation, post-pivot breakout and EMA44 confirmation.
- Existing Support/Resistance and Breakout/Pullback logic is partial; it is not a complete hybrid engine.
- The following dedicated capabilities were not found in the audited paths and require implementation/audit: absolute Delivery Quantity trend + price-stability model; fixed-range base metrics; repeated S/R test counts; VCP contraction engine; EMA50/EMA200 observation; post-breakout retest; reproducible Pocket Pivot; four independent watchlist outputs.
- The current scanner's later core technical/confirmation flow can exclude non-Breakout/Pullback candidates. The hybrid implementation must preserve early-stage accumulation/base candidates in their own watchlists instead of treating lack of breakout as a final rejection.
- Current fundamentals are collected after Liquidity. The boundary decision remains open as noted above.
- Audit is a code-to-rule finding, not a claim that the missing features have already been implemented or tested.

## 10. Explicitly unresolved — do not ask repeatedly; keep recorded until decision is needed

These are pending, not approved thresholds:
1. Whether the proposed count of **6–8 sessions with Delivery >=60% among 20 sessions** should remain informational or become a separate rule. Until approved, informational only; it does not replace Delivery A/B.
2. Whether to create a shadow/watchlist for stocks below ₹1.5 crore traded value.
3. Fundamental collection boundary: all Delivery A/B stocks before Liquidity vs current Liquidity-first flow.
4. VCP contraction count, contraction-depth sequence and exact base width/duration thresholds.
5. Pocket Pivot exact formula, lookback and candle conditions.
6. False-breakout buffer and retest window length.
7. How relaxed EMA trend observations should be for Early Accumulation (no automatic rejection below EMA200).
8. Any new threshold or change to an existing production gate not explicitly recorded as confirmed above.

Do not stop unrelated approved work to ask about every pending item. Implement only the parts whose definitions are sufficiently clear; isolate undecided measurements as descriptive/WAIT fields and bring a concise decision request only when a pending choice blocks the next implementation step.

## 11. Implementation order and required validation

1. **Phase 1 — Audit:** map Master Spec to main-branch code/workflows; verify calendar and 200-session cache; map each rule to code/tests/reports. Read-only unless user asks for implementation.
2. **Phase 2 — Universe & Delivery:** preserve Mainboard Large/Mid/Small, exclusions, 30D A/B and minimum five valid reports; specify Delivery Quantity data and trend calculations.
3. **Phase 3 — Liquidity & Fundamentals:** preserve ₹1.5 crore and tiers; improve classification/cache; resolve collection boundary before changing its stage.
4. **Phase 4 — Potential Accumulation:** quantity, delivery %, traded volume, price stability, base metrics, repeated S/R tests, Higher Low/Double Bottom, selling pressure.
5. **Phase 5 — VCP / Consolidation:** contraction, narrowing range, volume dry-up and statuses.
6. **Phase 6 — Trend:** EMA20/44/50/200 observations; distinguish Early Accumulation and Strong Trend Consolidation.
7. **Phase 7 — Breakout / Retest / Pocket Pivot:** predefined resistance, close/volume expansion, false-breakout buffer, retest quality, exact Pocket Pivot formula after definition.
8. **Phase 8 — Existing V8 confirmations and risk:** only after earlier hybrid phases; preserve sector/news/3+1 and all existing risk gates.
9. **Phase 9 — Four independent watchlists:** reasons, dates, raw evidence, data statuses and audit trails.
10. **Phase 10 — Tests/backtest:** unit/regression tests; 200-session history; Large/Mid/Small coverage; missing-data cases; false accumulation/breakout; VCP/Pocket Pivot; liquidity impact; fees/slippage; MFE/MAE at 5/10/20 sessions; conversion rates, win rate, average R and drawdown.

For each phase use: **Rules → Code Mapping → Implementation → Unit Tests → Historical Tests → User Review → Next Phase**. Never report PASS without actual evidence. Never remove existing filters or change unrelated modules silently.

## 12. Project continuity rule for future assistant sessions

Before taking action on this repository:
1. Read this file and the original Master Specification (unchanged).
2. Read the current README and relevant current code/workflows.
3. Check the latest main commit and workflow state; do not rely on stale chat summaries.
4. Use the confirmed rules above without asking the user to repeat them.
5. Ask only when an explicitly pending decision blocks a specific implementation choice.
6. Update this register and README whenever the user approves a new parameter or a phase changes status. Keep confirmed rules separate from pending proposals.

## 13. Phase 2 progress — Delivery Quantity evidence (09-Nov-2026)

**Implemented on main (observational only):**
- Added `delivery_quantity_analysis.py` and `test_delivery_quantity_analysis.py`.
- Integrated the observation builder into the main EOD scanner using the already-fetched 30-calendar-day NSE Delivery report set. It does not perform extra report downloads.
- Captures 5/10/20 report-session Delivery Quantity totals, averages, first/last values, percentage change and per-session OLS slope.
- Where the source report also contains them, captures Delivery % average, traded-volume average, closing-price first/last/change/range and dated per-session raw observations.
- Missing quantity columns, missing candidate rows, duplicate symbol/series rows, insufficient sessions or future dates are handled as `WAIT_FOR_DATA` / excluded from the as-of window. The candidate row is retained in the audit.
- No accumulation score, buyer identity, PASS gate, rejection threshold or ranking change was introduced. These fields are evidence for the next Accumulation phase only.
- Output: `outputs/v8_delivery_quantity_observations_YYYYMMDD.csv`.

**Compatibility hygiene:**
- The legacy `delivery_categories.py` adapter previously implemented a separate five-session-only rule. It has been aligned to the authoritative 30-calendar-day A/B rule to prevent accidental use of stale semantics. Its tests now cover six valid reports, A-only, A+B, below-threshold and fewer-than-five candidate observations.

**Validation status:** Phase 2 code and regression validation passed on GitHub Actions run `42584832086` (commit `b209f431dd066736a581260948b78af40b1ef44f`): compile passed, 211 unit/data-audit tests passed, all 31 V8 regression tests passed, and the sector/news/official-index test step passed. The direct live NSE archive download was not available during this session; the NSE All Reports page confirms the Full Bhavcopy and Security Deliverable report and its displayed deliverable-quantity/price/volume fields. Exact legacy CSV header names are supported by the analyzer. Production behavior remains fail-closed if the downloaded header or any symbol observation is missing. Mark Phase 2 code/CI complete; live run artifact/header verification remains an operational follow-up.

**Next:** inspect CI and actual workflow artifact/header evidence; then add dedicated tests against the real report schema. Proceed to price-stability/base metrics only after confirming the actual raw fields and without introducing unapproved thresholds.

- Additional data-integrity hardening: `delivery_filter.py` now validates the internal NSE `DATE1` field against the requested/cache session date before accepting a downloaded or cached report. A mismatched, mixed-date, missing-date or unparseable report is rejected and cannot be relabelled as the requested session. Tests are in `test_delivery_report_date_integrity.py` and included in the V8 CI workflow.
- Source schema check: NSE's official All Reports page lists the “Full Bhavcopy and Security Deliverable data” report; its displayed security table includes deliverable quantity, close, traded quantity and delivery percentage. The legacy CSV header uses `DELIV_QTY`, `CLOSE_PRICE`, `TTL_TRD_QNTY`, and `DELIV_PER`. The new analyzer supports these headers. 

- Phase 2 status: **CODE + CI COMPLETE / LIVE DATA ARTIFACT CHECK PENDING**. Do not treat the quantity observations as a buy signal or alter any existing gate.

## 14. Phase 4 progress — Potential Accumulation observations (09-Nov-2026)

**Implemented on main:**
- Added `potential_accumulation_analysis.py` and `test_potential_accumulation_analysis.py`.
- The scanner runs it on the unique Delivery A OR B candidate union immediately after RVOL classification and **before Liquidity and all later technical/confirmation gates**.
- This is a separate observation report; it never filters, ranks, scores, labels a stock as institutionally accumulated, or changes the main candidate dataframe.
- Rolling price-range observations for 20/50/100/200 actual market sessions: high, low, range width %, sessions since the latest high/low and exact-equality high/low touch counts. These are **not yet a fixed-range base classification**.
- Confirmed 3-left/3-right pivot high/low counts, latest/previous pivot low and Higher-Low observation. Pivot structure is WAIT_FOR_DATA unless the full available session history and OHLC rows are complete.
- Raw separation between the last two confirmed pivot lows: absolute distance, percentage distance and ATR14 multiple. No Double Bottom pass/fail threshold is applied.
- On sessions with Delivery % >=60.00%, reports count, total/average Delivery Quantity, average/median absolute close-to-previous-close change, average intraday range, up/down session counts and a separate price-response data status.
- Last 20-session down-day/up-day counts, average volume on down/up days and down-vs-up volume ratio, with explicit missing-data status.
- Uses point-in-time session alignment: future rows are excluded; candidate price windows require one valid symbol observation on every selected market session. Missing symbol rows or missing OHLC data produce WAIT_FOR_DATA rather than silently extending the window backward.
- Output: `outputs/v8_potential_accumulation_observations_YYYYMMDD.csv`.

**Not implemented yet / still pending:**
- A fixed-range base start/end and base duration classification.
- Support/resistance zone clustering tolerance and repeated *zone* test counts. Current exact-extreme touch counts are only raw observations, not clustered tests.
- VCP contraction sequence and its user-approved thresholds.
- EMA50/EMA200 observations.
- Breakout/retest/Pocket Pivot logic and the four independent watchlist outputs.
- No threshold was invented for pivot-low separation or a double-bottom classification.

**Validation:** GitHub Actions run `42585559322`, commit `6f27bd6b71be686fa9a158dc71498dea16cd963a`, completed SUCCESS: compile passed, 217 unit/data-audit tests passed, all 31 V8 regression tests passed, and sector/news/official-index tests passed. The report is still observational and not a BUY signal.

**Next implementation:** fixed-range base measurements and repeated support/resistance zones require a documented, non-arbitrary definition. Until the open tolerance/base-duration decisions are approved, keep the raw range/extreme observations only and continue with VCP descriptive metrics without converting them into hard gates.

## 15. Phase 6 progress — Early trend / EMA observations (09-Nov-2026)

**Implemented on main:**
- The pre-Liquidity Potential Accumulation report now computes independent EMA20, EMA44, EMA50 and EMA200 values for the unique Delivery A/B candidate union.
- Includes each EMA's distance from current close, above/below/at position and a separate per-period data status.
- EMA values are calculated over the full available point-in-time history, not only the final N rows. Each EMA requires complete candidate observations across the supplied market-session history; EMA200 remains WAIT_FOR_DATA until at least 200 complete sessions are available.
- TrendObservationStatus distinguishes COMPLETE, PARTIAL_DATA and WAIT_FOR_DATA.
- These are informational only. Below EMA200 does not reject Early Accumulation; no EMA20/44/50/200 condition was added as an eligibility, ranking or BUY gate. Existing production EMA44 logic is unchanged.

**Validation:** GitHub Actions run `42585764820`, commit `6f1e98593857b8acbd7cee39a80f279281cc1229`, completed SUCCESS: compile passed, 218 unit/data-audit tests passed, all 31 V8 regression tests passed, and sector/news/official-index tests passed.

**Still pending:** EMA trend interpretation thresholds/slopes are not defined as gates; no new trend gate is approved. VCP contraction sequence and fixed-range base definitions remain separate pending work.

## 16. Phase 5 progress — VCP contraction observations (09-Nov-2026)

**Implemented on main:**
- Added `vcp_observation_analysis.py` and `test_vcp_observation_analysis.py`.
- The scanner runs the report on the unique Delivery A OR B candidate union after the other early observations and **before Liquidity**. It does not change candidate membership or rank.
- Measures three consecutive 20-session blocks (60 actual market sessions): each block's high/low range width %, ratios between consecutive block widths, and number of observed contraction transitions.
- Records average traded volume for each block, consecutive block volume ratios and the latest-block/prior-block volume dry-up ratio.
- The existing <0.5x volume dry-up marker is **observational only**; it is not a filter or score.
- The exact latest 60 market sessions are aligned per symbol. A missing symbol session, missing OHLCV field or insufficient history produces WAIT_FOR_DATA; it never reaches backward to substitute an older session. Future rows are excluded.
- Complete measurements remain `VCPStatus=NOT_CLASSIFIED` because the final VCP classification thresholds are not yet approved. Incomplete measurements remain `VCPStatus=WAIT_FOR_DATA`. No `VCP_CONFIRMED` or `VCP_FORMING` label is emitted yet.
- Output: `outputs/v8_vcp_contraction_observations_YYYYMMDD.csv`.

**Still pending:** fixed-range base start/end/duration, contraction count/depth thresholds, and the final VCP_CONFIRMED/VCP_FORMING/NO_VCP classification. These observations are not a BUY signal and are not an entry gate.

**Validation:** GitHub Actions run `42586036668`, commit `c3885e40cb66b1a5fa5a4afaa31f076bc299f5a4`, completed SUCCESS: compile passed, 221 unit/data-audit tests passed, all 31 V8 regression tests passed, and sector/news/official-index tests passed.

## 17. Phase 7 progress — Existing trend, breakout, support/resistance and liquidity data integrity (09-Nov-2026)

**Implemented on main without changing existing signal thresholds:**
- Breakout and Pullback now use exact prior market-session windows. 20D resistance and volume baselines require 20 complete prior sessions; 50D resistance requires 50 complete prior sessions. A missing symbol session is not replaced by an older row.
- Zero/missing 20D volume baseline no longer becomes synthetic RVOL=0. A flat/invalid candle no longer receives synthetic CLV=0.5. Missing prerequisites produce WAIT_FOR_DATA.
- Existing breakout thresholds remain unchanged: 20D breakout RVOL >=2.0 and CLV >0.75; 50D breakout RVOL >=1.5 and CLV >0.75; Near Breakout remains within the existing 2% 20D resistance proximity and RVOL >=1.2.
- Existing Pullback thresholds remain unchanged: 1–15% correction, within 3% of EMA20/EMA44, RVOL <=1.5, at least 3 low-volume days and bullish reversal candle. Missing inputs now return WAIT_FOR_DATA rather than a misleading no-setup/pullback status.
- Support/Resistance now validates exact prior 20/50/100/200 market-session windows and previous-day data. Missing symbol sessions are not backfilled; explicit SR window/data statuses are emitted. Existing 2% near-resistance, 3% near-support and entry-zone calculations are unchanged.
- Trend EMA20/EMA44, RSI and ADX calculations now require complete point-in-time symbol history from the symbol's first available session through the current EOD and a complete latest 50-session OHLC window. Missing/current-session gaps return WAIT_FOR_DATA. Existing EMA44 trend interpretation is unchanged.
- Liquidity continues to use 20 prior session frames and the existing ₹1.5 crore minimum / ₹2 crore and ₹5 crore tiers. Duplicate symbol rows in a session are now ambiguous WAIT_FOR_DATA; when Date is supplied, duplicate or mixed/invalid session dates also produce WAIT_FOR_DATA. Date-less legacy callers retain the documented ordered-session-list contract.
- Empty candidate frames preserve the expected output schema.

**Still pending:** post-breakout retest window, false-breakout buffer, Pocket Pivot formula/lookback/candle conditions, support/resistance zone clustering tolerance and four independent watchlist outputs. No new entry gate was introduced.

**Validation:** GitHub Actions run `42587194568`, commit `cfb3260bdfb78f5ba91e8ebe569d6373a37797e4`, completed SUCCESS: 239 unit/data-audit tests passed, all 31 V8 regression tests passed, and sector/news/official-index tests passed.

## 18. Phase 3 audit — Liquidity and Fundamental cache boundary (09-Nov-2026)

**Current code verified:**
- Liquidity is a hard gate using 20 prior sessions of NSE Bhavcopy TtlTrfVal; average daily traded value >=₹1.5 crore passes. Tiers remain LOW ₹1.5–<₹2 crore, MEDIUM ₹2–<₹5 crore and STRONG >=₹5 crore.
- Fundamental collection is currently called **after Liquidity** and receives the liquidity-qualified candidate frame. This is the existing implementation; whether collection should instead cover the entire Delivery A/B union before Liquidity remains an unresolved boundary decision. Do not change until explicitly resolved.
- Fundamental collection never removes candidate rows. Manual metric values remain authoritative; provider failures and missing metrics remain visible as MISSING_DATA/PARTIAL_DATA/WAIT statuses.
- The current metrics cache is `data/inputs/fundamental_metrics.csv`; dated snapshots are written under `data/cache/fundamental_history/`. The scheduled GitHub workflow stages and commits the current cache and dated history snapshots into the repository.
- Yahoo Finance via yfinance is a secondary provider; official NSE filing metadata supplies publication-date verification and period-alignment statuses. Direct XBRL metric-value verification is run as a separate audit sidecar using hash-verified official XML evidence; it is not currently a candidate gate and is not merged into the FundamentalScore calculation.
- FundamentalScore is informational only. The current score requires six numeric score metrics plus verified publication date, period end and metric-period alignment; the direct XBRL metric-value verification sidecar remains separately visible. Do not turn Strong Fundamental or score >=65 into an eligibility gate.

**Open boundary decisions remain:** collect fundamentals for all Delivery A/B before Liquidity versus current Liquidity-first collection; and whether direct XBRL metric-value verification should become a score prerequisite or remain a non-gating evidence sidecar. No change made.
