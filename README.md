# NSE Swing Trading Bot V8.0

Automated NSE EOD research and swing-trading analysis pipeline. The scanner produces candidate lists, evidence reports, watchlists, and risk/confirmation status; it does not place orders.

## Project source-of-truth hierarchy

1. **Master Specification:** [Pasted text(20261009-143842).txt](Pasted%20text%2820261009-143842%29.txt), including its dated authoritative update at the top. The historical specification body is retained below that update.
2. **Current working parameters and implementation register:** [NSE V8 Hybrid Strategy Master Parameters](NSE_V8_HYBRID_STRATEGY_MASTER_PARAMETERS_2026-11-09.md). This records current approved parameters, code status, unresolved decisions, and validation evidence; it supplements but does not replace the Master Specification.
3. **README:** navigation and concise operational status only.

## Current production selection order

- Eligible NSE Mainboard universe (Largecap, Midcap, Smallcap; existing SME/ETF/MF exclusions).
- Prior 20 complete sessions are loaded to prepare the average-volume baseline.
- Delivery Category A and B are calculated independently over **all** valid distinct reports in the full 30-calendar-day window (not just the latest five); minimum five valid reports. A = average >=60.00%; B = every available valid day >=60.00%. Reports show actual valid-session count, dates, average/min/max Delivery %, A/B status and WAIT_FOR_DATA when fewer than five reports exist.
- Form the complete de-duplicated A OR B union and preserve A_ONLY / B_ONLY / A_AND_B.
- Calculate RVOL only for this union: >1.5 HIGH, <=1.5 LOW, invalid/missing WAIT_FOR_DATA. RVOL is classification only and never rejects a Delivery-qualified candidate.
- All A/B candidates continue to the 20-session liquidity check; hard minimum average traded value ₹1.5 crore.
- Approved sequence (confirmed 06-Nov-2026): the complete Delivery A OR B union, including HIGH/LOW/WAIT RVOL bands, proceeds to Liquidity; Fundamentals are collected for every Liquidity-qualified candidate. Fundamental scoring remains enrichment/priority context, not a rejection gate.

## Hybrid watchlists

Four independent reports are maintained: Potential Accumulation, Base/VCP Forming, Breakout Ready, and Confirmed Entry. Early-stage watchlists are observational and are not BUY signals. Unapproved VCP, Pocket Pivot, retest, or false-breakout thresholds must not be invented.

## Latest audited run

GitHub Actions run [42774048772](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/42774048772) completed successfully on the 2026-11-10 main-branch fix. It reported 3,037 universe rows (2,588 Mainboard PASS; 449 SME excluded), 758 Delivery A-qualified rows, 102 B-qualified rows (included within A), and 758 unique A/B candidates. RVOL classification: HIGH=105, LOW=610, WAIT=43. RVOL is informational and did not reject any A/B candidate.

The 758 candidates then reached the 20-session liquidity filter: 54 PASS, 661 below the minimum, and 43 WAIT_FOR_DATA. Among the 54 liquidity-qualified candidates, fundamentals were COMPLETE=31 and PARTIAL_DATA=23; no fundamental score/data status was used as a rejection gate. The core technical screen evaluated those 54: 3 PASS and 51 REJECT. The final EOD shortlist was empty; this is not a claim that the 54 liquidity candidates all became final trade setups.

Stage-level audit rows can repeat symbols because the same stock appears at different gates. Read counts per stage, not as a sum of unique stocks. The old `DELIVERY_5D` audit label has been corrected to `DELIVERY_30D_AB`; it refers to the production 30-calendar-day A/B screen, not the separate five-session watchlist.

The correctly named pre-news cohort export is `outputs/v8_liquidity_qualified_pre_news_candidates.csv`. The former `v8_pre_news_rvol_gt_1_5_candidates.csv` filename remains temporarily as a compatibility alias; despite its legacy name, it contains all 54 liquidity-qualified candidates, including LOW RVOL stocks.
---

## Free-source fundamentals policy

- Official NSE integrated financial filings and XBRL are the primary verification source. A value is treated as officially verified only after it is reconciled with a dated filing and matching period/basis.
- Yahoo Finance accessed through `yfinance` is a secondary, no-token provider for candidate metrics and valuation snapshots. It can be delayed, incomplete, revised, or inconsistent; provider values remain unverified until the NSE filing audit confirms them.
- No paid provider token or paid data API is required by the scanner. Missing, stale, or conflicting figures remain visible as `WAIT_FOR_DATA` or a mismatch instead of being guessed or promoted.
- No shortlist threshold is weakened to compensate for missing source data. Review NSE XBRL and provider diagnostics when coverage is incomplete.

---

## Current authoritative rule addendum

The active 30-calendar-day NSE Delivery A/B screening rules, clarified on 2026-11-10 to use every valid report in the window after a minimum of five, are documented in [`NSE_V8_DELIVERY_AB_RULES_ADDENDUM_2026-11-07.md`](NSE_V8_DELIVERY_AB_RULES_ADDENDUM_2026-11-07.md). The strict five-session Delivery-only watchlist remains a separate artifact. This addendum supplements the Master Specification; it does not replace or rewrite it.

## Current authoritative RSI rule addendum

The RSI informational-only / no-stock-rejection policy agreed on 2026-11-07 is documented in [NSE_V8_RSI_INFORMATIONAL_ONLY_RULES_ADDENDUM_2026-11-07.md](NSE_V8_RSI_INFORMATIONAL_ONLY_RULES_ADDENDUM_2026-11-07.md). RSI is reported to Telegram but cannot affect stock eligibility or any existing non-RSI filter.


## Authoritative selection order — Delivery A/B before RVOL (09-Nov-2026)

The previous wording that RVOL is calculated for the full Mainboard universe is **obsolete and superseded**. The production order is:

1. Load the latest verified NSE EOD Bhavcopy and prepare the eligible NSE Mainboard universe (Largecap, Midcap and Smallcap; existing SME/ETF/MF exclusions remain).
2. Load/reuse the prior 20 complete trading-session Bhavcopy history and prepare the average-volume baseline only. **Do not calculate RVOL for the Mainboard universe at this stage.**
3. Apply the existing 30-calendar-day Delivery Category A rule (average Delivery >=60.00%; minimum five valid distinct reports).
4. Apply the existing 30-calendar-day Delivery Category B rule (every valid report >=60.00%; minimum five valid distinct reports).
5. Build the complete **A OR B** union; preserve `A_ONLY`, `B_ONLY`, and `A_AND_B` membership and de-duplicate by symbol.
6. **Only now calculate RVOL** for every unique stock in the A/B union, using current EOD volume divided by the average volume of the previous 20 complete trading sessions (current session excluded).
7. Classify RVOL: strictly >1.5 = `HIGH_RVOL_GT_1_5`; <=1.5 = `LOW_RVOL_LE_1_5`; missing/invalid baseline or current volume = `WAIT_FOR_DATA`.
8. **Do not reject or drop any A/B-qualified stock because RVOL is low or unavailable.** All unique A/B stocks, including HIGH, LOW and WAIT_FOR_DATA RVOL groups, continue to the existing Liquidity stage.
9. Preserve RVOL and its verified 20-session baseline for downstream observations/technical calculations; do not recalculate RVOL for the full universe or apply a Top-20/Top-50 RVOL cap.

The EOD artifacts separately expose the complete Delivery A list, complete Delivery B list, the de-duplicated A/B union with RVOL classification, high-RVOL candidates, low-RVOL Delivery candidates, and RVOL-WAIT candidates. Exactly 1.50 belongs to LOW; only values strictly greater than 1.50 belong to HIGH.

This sequence supersedes any older README wording, comments or notes that place RVOL calculation before Delivery A/B. The original Master Specification remains unchanged; this is the current approved implementation order and does not alter Delivery thresholds, liquidity thresholds, or unrelated downstream filters.


---

## Hybrid Strategy — persistent working parameters (09-Nov-2026)

The current project scope, confirmed parameters, implementation order, Phase 1 code-audit findings, four independent watchlists, unresolved decisions and continuity instructions are recorded in:

**[NSE V8 Hybrid Strategy Master Parameters](NSE_V8_HYBRID_STRATEGY_MASTER_PARAMETERS_2026-11-09.md)**

Read this register before continuing project work. It is the persistent working reference for the Smart-Money Footprint + Accumulation + VCP + Breakout hybrid so the user does not need to repeat previously agreed decisions.

### Working priority
- Build **Potential Accumulation → Base/VCP Forming → Breakout Ready → Confirmed Entry** as four separate watchlists.
- Preserve the current Mainboard universe, 30-calendar-day Delivery A/B rules, RVOL informational classification, ₹1.5 crore liquidity minimum, fundamental enrichment/cache, RSI informational-only policy and all existing risk gates.
- Do not reject an early accumulation/base candidate solely because VCP or breakout is not yet present.
- Do not change Sector Strength, News/Catalyst or mandatory 3+1 during the initial hybrid phases. Preserve them for later integration.
- Pending thresholds (VCP contraction/base width/duration, Pocket Pivot formula, false-breakout buffer, retest window and other recorded open decisions) must not be guessed or silently turned into hard filters.
- The original `Pasted text(20261009-143842).txt` / `NSE SWING TRADING SYSTEM V8.0` Master Specification remains unchanged and authoritative. The hybrid register supplements it; it does not replace it.



## Hybrid strategy implementation status

The working decisions, confirmed thresholds, pending parameters and phase-by-phase implementation status are maintained in [NSE V8 Hybrid Strategy Master Parameters](NSE_V8_HYBRID_STRATEGY_MASTER_PARAMETERS_2026-11-09.md). The original Master Specification remains unchanged. Delivery Quantity observations are informational only and do not alter Delivery A/B eligibility.

- Delivery report integrity: the internal NSE report date is checked against the requested session before cached/downloaded data is accepted.

- Phase 2 Delivery Quantity observations: code integrated and validated by GitHub Actions (211 unit/data-audit tests + 31 V8 regression tests passed). Live NSE artifact/header verification remains a follow-up; missing data fails closed and never affects Delivery A/B eligibility.


- Phase 4 Potential Accumulation observations: a separate report now runs on the full Delivery A/B union before Liquidity. It records rolling price ranges, pivot/Higher-Low observations, Delivery >=60% price response and down/up-day volume context. It does not filter or score candidates. GitHub Actions validated 217 unit/data-audit tests and 31 V8 regression tests. Fixed-range base/VCP thresholds and watchlists remain pending.

- Phase 6 Early Trend observations: EMA20/44/50/200 values, distance and position now appear in the pre-Liquidity accumulation observation report. They are informational only and do not reject stocks below EMA200. Latest validation: 218 unit/data-audit tests and 31 V8 regression tests passed.

- Phase 5 VCP observations: three consecutive 20-session range/volume blocks and contraction/dry-up ratios now run before Liquidity on the Delivery A/B union. The <0.5x volume flag is observational only; VCP is not classified and does not gate candidates. Latest validation: 221 unit/data-audit tests and 31 V8 regression tests passed.

- Phase 7 integrity work: breakout/pullback, support/resistance and trend indicators now fail closed on missing or incomplete market sessions; original signal thresholds are unchanged. Liquidity duplicate rows/dates now WAIT_FOR_DATA. Latest CI: 239 unit/data-audit tests and 31 V8 regression tests passed.
- Phase 3 audit: fundamental cache and dated snapshots are persisted in-repo by the scheduled workflow. Collection occurs after Liquidity for every liquidity-qualified candidate, as confirmed on 06-Nov-2026; XBRL value verification remains a separate non-gating sidecar.

- Four independent Hybrid watchlists are now emitted: Potential Accumulation and Base/VCP before Liquidity; Breakout Ready and Confirmed Entry after existing EOD gates. They are reporting-only and never feed back into candidate selection. Final EOD missing prerequisites now WAIT_FOR_DATA. Latest CI: 253 unit/data-audit tests and 31 V8 regression tests passed.

- Final EOD AD and ATR fallback now require complete 20-session data; mandatory 3+1 thresholds and portfolio risk controls were audited and preserved. Missing account/risk inputs remain WAIT_FOR_DATA. Latest CI: 257 unit/data-audit tests and 31 V8 regression tests passed.

- RVOL baseline now requires exactly 20 distinct prior sessions per symbol; duplicate/missing rows and invalid current volume return WAIT_FOR_DATA. Strict >1.5 classification is preserved and never rejects Delivery A/B candidates. Latest CI: 264 unit/data-audit tests and 31 V8 regression tests passed.

- Delivery Quantity, Accumulation and VCP source history now fail closed on duplicate report dates/rows, invalid quantities, missing price sessions and duplicate EOD rows. Current EOD values are reconciled without hiding duplicates. Latest CI: 273 unit/data-audit tests and 31 V8 regression tests passed.

- Accumulation ATR now requires complete OHLC input; selling-pressure volume averages require 20 valid non-negative volumes. Latest CI: 275 unit/data-audit tests and 31 V8 regression tests passed.

- Early Potential Accumulation watchlist now preserves the unique Delivery A/B union with explicit WAIT_FOR_DATA if its optional evidence engine fails. Latest CI: 276 unit/data-audit tests and 31 V8 regression tests passed.

- Breakout/Pullback and Support/Resistance now fail closed on invalid OHLCV candles, malformed history windows, duplicate candidates and missing required price columns. No unapproved retest or Pocket Pivot thresholds were added. Latest CI: 284 unit/data-audit tests and 31 V8 regression tests passed.

- Added a descriptive post-breakout retest observation report using existing V8 breakout definitions. It measures exact reference-level touches and post-breakout price/volume response without inventing a retest window or buffer; it is not an entry gate. Pocket Pivot remains pending exact approved formula. Latest CI: 291 unit/data-audit tests and 31 V8 regression tests passed.

- Pocket Pivot / repeated Support-Resistance audit: no Pocket Pivot detector or tolerance-clustered S/R zone-test counter currently exists. Existing 20/50/100/200-session exact extreme touch counts and confirmed pivots remain raw observations only; they are not zone confirmations. Formula/lookback/candle rules and zone/touch definitions remain unapproved, so no guessed signal or gate was added. See parameter register section 27.

- Base/VCP audit: retained the observational three-block (3×20-session) contraction and volume report; fixed-range base duration and final VCP thresholds remain unresolved. Hardened data integrity so non-finite prices/volume, invalid OHLC structure and duplicate candidate identities return WAIT_FOR_DATA. No scanner or entry gates changed. Latest CI: 295 unit/data-audit tests + 31 V8 regression tests passed.

- Base/VCP observations enhanced: rolling 20/50/100/200-session windows now include start/end dates, exact session count, average daily range and latest-close position; VCP reports contraction depth and whether price and volume contract together. These remain descriptive, not fixed-base/VCP classifications. False-VCP outcomes remain unevaluated until a forward horizon/failure definition is approved. Latest CI: 297 unit/data-audit tests + 31 V8 regression tests passed.

- Breakout follow-through reporting now includes post-event highest/lowest price excursions and counts of closes above/below/at the breakout reference. This is descriptive only; false-breakout horizon and failure definition remain unapproved. CI validation is pending.

- The post-breakout observation report now uses the user-approved first 10 trading sessions after a qualifying breakout. It reports horizon progress/completion and measures only that fixed window; false-breakout failure/re-entry definitions remain unapproved, and no entry gate is added.

- Ten-session breakout observation implementation validated successfully: 300 unit/data-audit tests + all 31 V8 regression tests passed; sector/news/official-index and issuer/RSS workflows passed. False-breakout failure and re-entry definitions remain pending approval.

- Runtime optimization (09-Nov-2026): Potential Accumulation and VCP now build a one-pass symbol/series index over the existing Bhavcopy history and reuse it for candidate lookups, preserving duplicate-session and WAIT_FOR_DATA integrity. Sector-history fallback now stops retrying all remaining Nifty indices after a confirmed service-wide HTML ReturnUrl redirect; no synthetic sector values are introduced. PR #33 merged after NSE V8 CI, sector mapping cache tests, and news parser tests all passed. Trading gates and the Master Specification remain unchanged. Live end-to-end runtime benchmark is pending the next scanner execution.


## Track 2 Full Mainboard Accumulation (10-Nov-2026)
- Added a standalone, non-gating Track 2 builder in `track2_full_mainboard.py`. It takes the official Mainboard-filtered cohort before Delivery A/B and runs the existing Delivery Quantity, Potential Accumulation and VCP observers over all unique Mainboard symbols.
- Track 2 writes to `outputs/track2_full_mainboard/`; optional observer output paths keep its files separate from Track 1 artifacts. It does not change Track 1 eligibility, ranking, watchlists or scanner flow.
- Duplicate/invalid identities and observer failures are retained as explicit WAIT_FOR_DATA states; the report does not silently drop the rest of the cohort.
- SIDEWAYS_ACCUMULATION and DIP_ACCUMULATION are still research requests, not classified patterns. Exact rules and thresholds require approval; none were invented.
- CI validated: 397 pytest tests, 33 V8 regression tests, and 43 sector/news/official-index unittests passed (workflow run 42800483179).
- This builder is not wired into the scheduled EOD workflow and has not been validated on a live NSE EOD run. Audit branch only; Master Specification and production scanner remain unchanged.
