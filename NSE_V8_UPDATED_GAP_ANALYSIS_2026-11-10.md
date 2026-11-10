# NSE V8.0 — Updated Gap Analysis
**Date:** 10-Nov-2026  
**EOD baseline date:** 2026-11-09  
**Repository:** digitalmf78-pixel/AI-Trading-Bot  
**Working branch:** audit/implementation-roadmap-2026-11-10  
**Status:** Findings recorded for review; no production code changed.

## 1. Newly reported and inspected gaps

### G1 — `ad_groups` variable in `v8_layers_14_41.py`
- **Reported issue:** runtime path raises an undefined-variable error for `ad_groups`.
- **Current main-branch source inspection:** `run_eod_layers()` currently initializes `ad_groups = {}` from validated `ad_history` before the later ATR fallback reads it. The reported failure is therefore not reproduced by static inspection of the current main branch.
- **Action:** treat as a regression/branch/runtime discrepancy until reproduced. Add a regression test that executes the ATR fallback with complete and incomplete history and verifies no `NameError` / `UnboundLocalError`. Capture the exact failing commit, traceback and workflow artifact before applying a code fix.

### G2 — Stop formula creates wide and inconsistent stops
- **Current formula:** `min(SRSupport, Close - 1.5 * ATR)` over valid positive candidates below price.
- **Reported diagnostic:** median stop distance approximately 8.3%; 47/54 candidates rejected by the stop-distance cap.
- **09-Nov EOD artifact cross-check:** median `StopDistancePct` is 8.18%; the artifact shows 46 `REJECT` and 5 `WAIT_FOR_DATA` under risk controls, with 46 explicit `STOP_DISTANCE_EXCEEDS_LIMIT` reasons. Thus the broad stop-cap problem is corroborated, while the exact 47/54 count differs from this artifact snapshot.
- **Gap:** choosing the lower of support and ATR stop can place the stop far below the relevant setup invalidation point and creates inconsistent risk distances.
- **Action:** evaluate setup-aware structural invalidation stops (breakout level/retest support for breakout; pullback swing/support for pullback), ATR as a volatility buffer, and stop-distance distribution by setup. Do not change formula or cap until historical validation and approval.

### G3 — R:R target selection blocks strong breakouts
- **Current code:** `_structural_resistance_candidate()` chooses the nearest verified overhead high from SR resistance, swing high and 20/50/100/200-session highs. SR resistance itself is derived from nearby prior-day/prior-week/20/50-day levels.
- **Current R:R:** `_calculate_structural_risk_reward()` returns WAIT when there is no verified overhead level above entry; it does not synthesize a 2R target.
- **Reported failure:** at/near 52-week highs, strong breakouts (ICICIBANK cited) can have no overhead historical resistance and are assigned WAIT, blocking the strongest breakout candidates.
- **Gap:** the target model treats a new-high breakout like a range-bound stock and has no approved 52-week-high / price-discovery target method.
- **Action:** compare separate target policies for range-bound, breakout and price-discovery setups. Evaluate measured-move, ATR extension, trailing/partial exits or other explicit methods only as proposals; do not invent a synthetic target or change the mandatory 2R rule without approval.

### G4 — Entry zone is resistance-anchored even for pullbacks
- **Current code in `calculate_support_resistance()`:** when close is at/below resistance, entry zone is `resistance * 0.995` to `resistance * 1.005`; when close is above resistance it is `resistance` to `resistance * 1.01`. This zone is generated without branching on Breakout vs Pullback setup.
- **Artifact evidence:** the 09-Nov EOD report carries `EntryZoneLow/High` into `EntryPricePlan`; the planned zone is therefore inherited by downstream stop and R:R calculations.
- **Gap:** a pullback/retest entry should be referenced to the retest/support/trigger structure, not mechanically to the overhead breakout resistance.
- **Action:** define separate breakout-entry and pullback-entry zone builders and test their setup-specific anchors. Thresholds and buffers remain pending approval.

### G5 — Delivery-first cohort selects relative laggards
- **09-Nov EOD artifact:** among 54 Liquidity-pass stocks, 49 have `RelativeStrengthNifty < 0`; median 20-session relative strength is -11.20 percentage points.
- **Interpretation:** this cohort is strongly tilted toward recent relative underperformers. Delivery strength alone does not distinguish accumulation from distribution or price deterioration.
- **Required sequencing:** add price-response and relative-strength evidence earlier in the research/priority flow, before News/Catalyst prioritization. Evaluate price direction, close location, up-day/down-day Delivery, Delivery Quantity/Value changes, 20D RS vs Nifty and sector-relative strength together.
- **Boundary:** do not silently convert RS into a new hard rejection gate. Preserve Track 1 Delivery A/B and Liquidity eligibility until the user approves whether RS is an informational tag, priority score, or selection gate.

### G6 — Module B has no live intraday data source
- **Current code:** `v8_layers_14_41.py` defines an `intraday_bars.csv` input template with Symbol, Datetime, OHLC and Volume fields; the module reads this local input.
- **Gap:** no integrated intraday data provider/collector was found in the inspected pipeline. The template alone is not an intraday feed.
- **Action:** identify approved data provider, API limits, authentication/secrets handling, timestamps/timezone, interval, retention and failure behaviour. Until connected and validated, intraday-dependent checks must remain WAIT_FOR_DATA; never treat an empty template as live data.

## 2. Execution order correction

**Signal Log + Shadow Run is moved to Step 1**, not left as the final phase.

1. **Signal Log + Shadow Run foundation:** persist every daily candidate, evidence snapshot, stage transition, entry/stop/target proposal, rejection/WAIT reason and subsequent 5/10/20-session outcome. Run in parallel with the existing production scanner without changing live selection. Use point-in-time inputs and prevent look-ahead bias.
2. Canonical data contracts and schema/version compatibility.
3. Delivery/Bhavcopy coverage audit and justified backfill.
4. Full-Mainboard Sideways/Dip Early Accumulation research track.
5. Price-response and RS diagnostics/priority integration before News/Catalyst prioritization.
6. Setup-aware entry zones, stops and targets; validate breakout vs pullback separately.
7. News (7-day), Events (20-day), institutional evidence and Fundamentals enrichment.
8. Intraday data-source integration for Module B.
9. Watchlist lifecycle, Telegram four-section reporting and performance analysis.
10. Regression, workflow validation and release review.

Shadow Run is observational and must not change production gates. Its history should make later stop/target/RS decisions evidence-based.

## 3. Decisions list — explicitly unresolved

1. **Fundamental hard-fail:** Should any fundamental metric/status ever hard-reject a stock, or remain enrichment/risk context? Which exact fields and thresholds, if approved?
2. **Sector treatment:** Is weak sector strength a hard veto, a warning/tag, or a priority-score input?
3. **Core Technical:** Is Core Technical a Trade Entry gate only, or may it reject a stock from all research/watchlists? Preserve early research visibility unless explicitly decided.
4. **Distribution handling:** Does a Distribution classification reject, downgrade priority, trigger a risk alert, or only remain an informational tag? Define required confirmation and lookback.
5. **52-week-high target rule:** How should price-discovery breakouts with no overhead resistance be evaluated while preserving the 2R risk rule?
6. **Stop rules:** Choose setup-aware structural invalidation and ATR buffer logic; define acceptable stop-distance cap and handling of wide but structurally valid stops.
7. **Target rules:** Define target hierarchy for breakout, pullback and range-bound setups; decide how PDH/PWH/20D/50D/100D/200D highs are used, when a measured move/trailing exit is allowed, and how the 2R requirement is assessed.
8. **Entry-zone rules:** Define separate breakout and pullback/retest anchors and tolerances.
9. **RS role:** Informational tag vs ranking/priority score vs hard selection gate; decide index and sector benchmarks and lookback.
10. **Intraday provider:** Approved data vendor/API, interval, coverage, cost/rate limits and fallback status.

No decision above should be silently encoded as a new filter or score.

## 4. Existing EOD baseline — corrected date
The baseline artifact and counts referenced in this audit are for **EOD 2026-11-09**, workflow run `42774048772` (artifact `nse-v8-reports-42774048772`). The audit/document creation date is 2026-11-10; it must not be confused with the EOD data date.

## 5. Change control
- Original Master Specification remains immutable.
- Track 1 Delivery A/B, RVOL, Liquidity and current Fundamentals collection boundary remain unchanged.
- No new hard gate, score weight, stop/target formula or provider integration is implemented by this gap-analysis update.
- All changes remain documentation-only on `audit/implementation-roadmap-2026-11-10`.
