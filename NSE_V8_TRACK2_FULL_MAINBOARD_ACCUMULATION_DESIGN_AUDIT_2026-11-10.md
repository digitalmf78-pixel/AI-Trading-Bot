# NSE V8 Track 2 — Full Mainboard Accumulation Design & Data Contract Audit

**Date:** 10-Nov-2026  
**Working branch:** `audit/implementation-roadmap-2026-11-10`  
**Baseline commit inspected:** `bd7b347a34497745de3b705275880277eca0272b`  
**Scope:** Design/data-contract audit only. No scanner, filter, workflow, Telegram, ranking, or Master Specification changes.

## 1. Objective and hard boundary

Track 2 is an independent early-research track over the complete eligible NSE Mainboard universe. It must be capable of observing potential accumulation before a symbol passes Track 1's Delivery A/B rule.

Track 2 must never:
- add, remove, qualify, reject, or reorder Track 1 candidates;
- change the 30-calendar-day Delivery A/B rule, RVOL, Liquidity, Fundamentals, or downstream gates;
- treat high Delivery % alone as accumulation or infer institutional buyer identity;
- convert descriptive observations into a BUY/entry signal;
- use future price/session data relative to the EOD as-of date.

Track 1 remains authoritative and unchanged.

## 2. Canonical cohort and row-coverage contract

Use the official Mainboard-filtered `current` frame immediately after `apply_official_main_board_filter`, before Delivery A/B narrows the candidate set.

For the audited 09-Nov-2026 report artifact:
- `outputs/v8_main_board_universe_audit.csv`: 3,037 unique symbols; 2,588 PASS_MAIN_BOARD and 449 EXCLUDED_SME.
- `outputs/v8_delivery_dual_category_audit.csv`: 2,588 unique rows, exactly matching the PASS_MAIN_BOARD symbol set; 2,385 EQ and 203 BE.
- Track 1 A/B union: 758 rows (656 A_ONLY, 102 A_AND_B, 0 B_ONLY); 1,830 full-cohort rows are outside the union.
- Therefore, Track 2's expected base is **2,588**, not 758 and not any later liquidity/fundamental/technical shortlist.

These are counts from artifact `nse-v8-reports-42774048772.zip` for EOD 2026-11-09, not a promise that every future EOD will have the same count. Each run must calculate and record its own cohort count and exact set reconciliation.

Required invariants per EOD:
1. One row per normalized `TckrSymb`; duplicates fail closed as `WAIT_FOR_DATA`.
2. Track 2 output symbol set equals the official PASS_MAIN_BOARD input set exactly.
3. No SME, ETF, Mutual Fund, or unknown-board symbol may enter the cohort.
4. Every expected symbol receives a row even if one or more evidence modules fail; missing evidence is represented with explicit status/reason, never by dropping the symbol.
5. Preserve the existing identity contract (normalized symbol); do not silently change to symbol+series. If series exists on both sides of a join, mismatches fail closed.
6. Preserve the full source cohort and raw source fields; downstream joins are left joins and cannot change membership.

## 3. Existing modules and what they already provide

### 3.1 Delivery Quantity — already full-Mainboard capable

`delivery_quantity_analysis.py` currently calculates 5/10/20 report-session observations:
- Delivery Quantity total, average, first, last, percentage change and OLS slope;
- Delivery % average;
- traded-volume average;
- close first/last/change/range;
- dated quantity, Delivery %, traded volume and close fields;
- source dates, as-of date, per-window status and reason.

The scanner calls it with the full Delivery audit frame before the A/B candidate union. This is the correct cohort scope for Track 2.

Limitations to retain in the design:
- windows are 5/10/20 supplied Delivery report dates, not 30/90/200 Delivery sessions;
- completeness is strict for selected report dates, but the module's `DeliveryQuantitySourceDates` is a list of dates supplied to it, not proof that every expected NSE session was fetched;
- the module does not produce Delivered Value. Do not invent or silently derive an official delivered-value field;
- the current module does not define a SIDEWAYS or DIP classification.

### 3.2 Potential Accumulation — useful observer, wrong current cohort for Track 2

`potential_accumulation_analysis.py` currently provides:
- rolling 20/50/100/200 actual market-session price-range high/low/width, last high/low touch positions/counts, dates, session count, average daily range and latest-close position;
- 3-left/3-right confirmed pivot counts and pivot-low observations;
- Higher-Low observation and raw separation between the latest two confirmed pivot lows (absolute, percentage and ATR14 multiple);
- Delivery Quantity / Delivery % / traded-volume and price response on high-Delivery sessions;
- selling-pressure context from up/down-day volume;
- EMA20/44/50/200 observations;
- explicit WAIT/observation statuses.

Its current function contract and scanner call are A/B-union scoped. The function drops duplicate candidate symbols with keep-first, so Track 2 must validate the canonical cohort identity before calling it; it must not silently rely on keep-first to hide duplicates.

The observer does not define a fixed-range base, SIDEWAYS_ACCUMULATION, or DIP_ACCUMULATION decision rule. Rolling range windows are observations, not a fixed-base classification.

### 3.3 VCP — existing 60-session descriptive observer

`vcp_observation_analysis.py` measures three sequential 20-session blocks:
- each block's price range width;
- contraction ratios/depth between blocks;
- average volume and volume ratios;
- price/volume contraction relationship;
- a <0.5x volume dry-up observation flag.

It deliberately does not declare VCP_CONFIRMED and uses no approved acceptance threshold. Its current scanner cohort is A/B candidates. Track 2 may produce a separate full-Mainboard research copy of these observations, but must not change existing Track 1 watchlist semantics.

### 3.4 Shared price-history index

`history_index.py` builds a one-pass symbol/series history index, preserves duplicate rows, excludes rows after as-of date and exposes a candidate history helper. It is suitable for reuse, subject to validating:
- exact NSE session calendar coverage;
- duplicate symbol-session rows;
- missing sessions for a symbol;
- valid OHLCV values and as-of cut-off.

A global set of dates alone does not prove a given symbol has a complete price history.

## 4. Proposed Track 2 architecture (design only)

1. Capture `mainboard_universe` immediately after official Mainboard classification and before Delivery A/B filtering.
2. Keep the existing Track 1 flow unchanged: Delivery audit → A/B union → RVOL → Liquidity → Fundamentals → later stages.
3. Reuse the already-produced full-cohort Delivery audit and the same as-of-bounded Delivery sessions/Bhavcopy history for Track 2. Do not trigger duplicate NSE downloads when valid cache entries exist.
4. Run Track 2 observers independently on a validated copy of the 2,588-row-equivalent full Mainboard frame:
   - Delivery Quantity observations;
   - Potential Accumulation price/quantity/selling-pressure observations;
   - rolling price ranges and pivot/EMA observations;
   - three-block VCP/contraction observations.
5. Left-join each observer onto the Track 2 base using the existing normalized symbol identity and as-of date. Validate one-to-one cardinality before writing.
6. Write a distinct Track 2 report/watchlist namespace. Do not reuse the existing 758-row Track 1 early-watchlist CSV paths.
7. Keep Track 2 outputs observational and separate from the Track 1 A/B, liquidity, fundamental, technical and entry pipeline.
8. Persist a per-run manifest with EOD date, strategy commit SHA, source filenames/URLs, fetched/cache dates, expected/observed Mainboard count, observer row counts, missing/duplicate counts and run status.

Suggested separate artifacts (names are proposals, not yet implemented):
- `outputs/v8_track2_full_mainboard_cohort_YYYYMMDD.csv`
- `outputs/v8_track2_delivery_quantity_observations_YYYYMMDD.csv`
- `outputs/v8_track2_potential_accumulation_observations_YYYYMMDD.csv`
- `outputs/v8_track2_vcp_observations_YYYYMMDD.csv`
- `outputs/v8_track2_coverage_manifest_YYYYMMDD.json`

## 5. SIDEWAYS_ACCUMULATION and DIP_ACCUMULATION — classification contract

These are requested research categories, but their numerical/structural definitions are not approved in the audited source material. Do not invent price-range width, duration, slope, support-touch tolerance, drawdown, retracement, or volatility thresholds.

Until those definitions are approved, the output should expose:
- `ResearchPatternRequested`: `SIDEWAYS_ACCUMULATION`, `DIP_ACCUMULATION`, or `BOTH` as a research target/configuration label only;
- `ResearchPatternStatus`: `NOT_CLASSIFIED_PENDING_APPROVED_RULES`, `WAIT_FOR_DATA`, or a future approved classification status;
- raw observations required to support a future rule;
- `Reason` and data-quality status.

No stock should be called SIDEWAYS_ACCUMULATION or DIP_ACCUMULATION as a measured result until the user approves the actual classification rules and tests prove their point-in-time behaviour.

### Evidence required before a future classification rule

**Sideways research evidence**
- exact window start/end and actual session count;
- range high/low/width and latest-close position;
- average daily range and price drift/close-to-close change;
- repeated support/resistance observations with explicit price levels and dates;
- volume and Delivery Quantity/Delivery % context;
- selling-pressure and subsequent price response;
- complete/missing/duplicate OHLCV and Delivery session coverage.

**Dip research evidence**
- exact reference swing/pivot high and date;
- subsequent low and date, with drawdown magnitude and percentage;
- pivot confirmation availability (3-left/3-right means a pivot is only confirmed after right-side sessions have elapsed);
- recovery/price-response observations, volume and delivery context;
- current price relative to observed EMA20/44/50/200;
- complete as-of history and explicit WAIT status where required.

These are fields to report, not pass/fail gates. A future rule must define the reference high/low selection, lookback, confirmation delay, allowed tolerances and missing-data policy before implementation.

## 6. No-lookahead and completeness rules

- All data rows must be on or before the EOD as-of date.
- A pivot requiring three right-hand sessions cannot be marked confirmed before those three sessions exist by the as-of date.
- The current EOD candle may be included once only; if the cached history already contains exactly one current row, merge candidate values into it; if there are duplicate current rows, preserve ambiguity and return WAIT.
- Expected NSE sessions must come from the official calendar, including notified special sessions. Do not infer completeness from business days or the dates that happened to download successfully.
- For every symbol/window, compare expected dates with actual symbol-specific dates. Missing actual-session data means WAIT_FOR_DATA; do not reach farther back to replace it.
- Non-finite, negative where invalid, structurally inconsistent OHLC, duplicate rows, wrong series, stale source or future-dated rows must be surfaced as explicit quality failures.
- Missing Delivery report row is not zero Delivery Quantity and not proof of low Delivery activity.
- Delivery Quantity, Delivery %, traded volume and price response must be presented together. High Delivery % alone is not proof of accumulation or buyer identity.

## 7. Output data contract (proposed)

### Identity and provenance
- `EODDate`, `TckrSymb`, `SctySrs`, `BoardClassification`, `MainBoardStatus`
- `StrategyGitSHA`, `RunID`, `RunMode`
- source artifact/file, source URL/name, source as-of date, fetched timestamp, cache hit/miss and source-date list where available

### Cohort/coverage
- `Track2CohortStatus`, `ExpectedMainboardCount`, `ObservedMainboardCount`
- `DeliveryQuantityStatus`, `PotentialAccumulationEvidenceStatus`, `PriceHistoryStatus`, `VCPObservationStatus`
- `MissingSessionCount`, `DuplicateSessionCount`, `InvalidOHLCVCount`, `CoverageReason`

### Evidence
- preserve native 5/10/20 Delivery Quantity fields;
- preserve 20/50/100/200 price-range and pivot/EMA fields;
- preserve high-Delivery price-response and selling-pressure fields;
- preserve three-block VCP range/volume observations;
- never overwrite raw source fields with normalized or derived values; use separate names for derived values and disclose formula/window.

### Classification
- `ResearchPatternRequested`
- `ResearchPatternStatus`
- `ResearchPatternReason`
- future category-specific fields only after approved rules exist.

## 8. Test plan before any Track 2 scanner wiring

1. **Cohort parity:** input/output symbol sets equal the official Mainboard PASS set; includes A/B PASS, A/B FAIL and A/B WAIT symbols; excludes SME/ETF/MF.
2. **No Track 1 mutation:** run Track 1 with and without Track 2 observer enabled and assert byte-equivalent Track 1 candidate membership, stage statuses and production output files.
3. **Row preservation:** all input symbols remain even if each observer raises/fails; failed observer columns become WAIT with reason, not dropped rows.
4. **Identity:** duplicate symbol, series mismatch, duplicate observer key, null/invalid symbol and duplicate EOD row fail closed.
5. **As-of/no-lookahead:** future rows excluded; pivot right-side confirmation timing verified; current EOD merged once; duplicate current EOD returns WAIT.
6. **Calendar coverage:** special session, missing expected session, duplicate session, holiday/weekend and partial cache cases.
7. **Delivery semantics:** missing report is not zero; invalid quantity and missing Delivery %/volume/close are independently represented; do not assume all metrics share one completeness status.
8. **Price integrity:** invalid OHLC, non-finite values, missing columns, wrong series and per-symbol missing session return WAIT.
9. **Category safety:** until definitions are approved, all category result statuses remain NOT_CLASSIFIED_PENDING_APPROVED_RULES; no numeric threshold appears in code.
10. **Artifact/manifest:** exact row counts, unique keys, source dates, commit SHA, and run status reconcile.
11. **Performance:** full 2,588-row execution reuses one history index and cached inputs; no per-symbol network requests or duplicate full-history scans.
12. **Regression:** run full repository pytest, V8 regression script, sector/news/index unittests and GitHub Actions CI; report exact commit/run ID.

## 9. Open decisions required before category implementation

No decisions are silently assumed. The following must be specified before classifying results:
- Sideways base lookback and minimum/maximum duration;
- range-width/volatility definition and any threshold;
- support/resistance touch/rejection tolerance and minimum observation count;
- price-drift or slope interpretation;
- Dip reference pivot/high selection and lookback;
- drawdown/retracement measurement and permitted range;
- whether a dip needs a recovery/confirmation condition;
- whether Delivery evidence is descriptive only or contributes to any future category score;
- category overlap policy (a symbol may satisfy both if future approved definitions allow it);
- status behaviour when Delivery history is incomplete but price history is complete, and vice versa.

## 10. Audit conclusion and next safe action

Track 2 has a viable foundation: full Mainboard Delivery Quantity observations already exist, and the price-range/pivot/EMA, selling-pressure and VCP observers can be reused. The principal gap is orchestration and independent artifact coverage: the Potential Accumulation and VCP observers are currently called on the Track 1 A/B union, not the full Mainboard cohort.

The next safe implementation step—after design review—is a standalone, non-gating Track 2 report builder and tests using the full Mainboard frame, with category fields explicitly left NOT_CLASSIFIED_PENDING_APPROVED_RULES. Only after parity, no-lookahead and failure-isolation tests pass should it be considered for scheduled workflow wiring. Production integration remains a separate approval step.

**No code or workflow was changed in this audit. The original Master Specification, Track 1 logic, main branch and production behaviour remain untouched.**

## Track 2 full-cohort CI and 09-Nov artifact coverage review (10-Nov-2026)

### Latest Track 2 CI
- Commit with the 2,588-symbol synthetic full-cohort test: `5d3db64c4b643b80122d089c60da0972d25bf3a4`.
- GitHub Actions run: `42801601368` — **SUCCESS**.
- Python compilation: PASS.
- Configured unit/data-audit suite: **398 passed in 7.52s**.
- V8 regression script: **33 tests PASS**.
- Sector/news/official-index unittest suite: **43 tests PASS**.
- The added synthetic cohort test verifies 2,588 unique symbols are preserved, all three observer inputs receive the complete synthetic cohort, output coverage is exact, and the source DataFrame is not mutated.
- This is synthetic orchestration/CI validation; it is not a real-data Track 2 run.

### Actual 09-Nov-2026 EOD artifact inspected
Source: GitHub Actions run `42634890331`, artifact `nse-v8-reports-42634890331` (downloaded and inspected read-only).

- Mainboard universe audit: **3,037** unique rows — **2,588 PASS_MAIN_BOARD**, **449 EXCLUDED_SME**.
- Mainboard PASS series composition: **2,385 EQ**, **203 BE**.
- Delivery dual-category audit: **2,588** unique rows, exactly matching the Mainboard PASS symbol set.
- Track 1 A/B union: **758** unique rows (656 A_ONLY, 102 A_AND_B, 0 B_ONLY); 1,830 Mainboard symbols are outside that union.
- Existing Delivery Quantity report already covers all **2,588** Mainboard symbols: **2,253 COMPLETE_5_10_20D**, **335 WAIT_FOR_DATA**. Individual window counts: 5D 2,352 COMPLETE / 236 WAIT; 10D 2,302 / 286; 20D 2,253 / 335.
- Existing Potential Accumulation report contains only **758** rows: 671 OBSERVATIONS_AVAILABLE and 87 PARTIAL_DATA (671 complete 20-session price histories; 87 WAIT_FOR_DATA).
- Existing VCP report contains only **758** rows: 500 COMPLETE and 258 WAIT_FOR_DATA for both range and volume observations.
- Therefore, the existing Track 1 Potential Accumulation and VCP reports leave **1,830** full-Mainboard symbols without an evaluation row. These are NOT_EVALUATED by the current reports; they must not be described as WAIT or as having no accumulation/VCP evidence.
- This artifact confirms the original gap: Delivery Quantity is already full-Mainboard, while Potential Accumulation and VCP are still A/B-union scoped.

### Real-data execution limitation and next action
- The EOD report artifact contains the full Mainboard candidate frame and existing stage reports, but does not contain the 200-session raw Bhavcopy cache or the raw Delivery cache files.
- The repository tree currently tracks fundamental history snapshots, but not `data/bhavcopy/` or `data/cache/delivery/`; those datasets are stored in the GitHub Actions cache (the 10-Nov checkpoint records a ~35 MB restored NSE cache).
- Consequently, the real-data Track 2 observer run over all 2,588 symbols has **not** yet been executed in this session. The artifact inspection above is a read-only coverage audit, not a substitute for rerunning the observation engines.
- Next safe step: restore the existing main-branch Actions cache in an isolated audit-only workflow, download the fixed 09-Nov report artifact, run only the Track 2 builder with network/Telegram disabled, and upload its separate `outputs/track2_full_mainboard/` reports. No production scanner wiring is implied.


## Real-data Track 2 offline run — completed (10-Nov-2026)

- Isolated GitHub Actions run [42804931499](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/42804931499) — **SUCCESS** on audit branch commit `d8e0de8e41e532d52225de41e799606da4f066fe`.
- Restored the existing main-branch NSE Actions cache read-only and downloaded the fixed 09-Nov EOD artifact. The validation used **201 Bhavcopy sessions including the 09-Nov as-of session (200 prior sessions)** and **21 cached Delivery report dates** from 12-Oct through 09-Nov. No cache errors were reported.
- Exact cohort parity was independently checked against the source `v8_main_board_universe_audit.csv`: **2,588/2,588 symbols match**, with zero missing, extra, duplicate or invalid symbols. The cohort and each of the three observer outputs contain 2,588 unique rows.
- Delivery Quantity observer: **2,253 COMPLETE_5_10_20D**, **335 WAIT_FOR_DATA**. Window coverage: 5D **2,352 COMPLETE / 236 WAIT**, 10D **2,302 / 286 WAIT**, 20D **2,253 / 335 WAIT**.
- Potential Accumulation observer: **2,253 OBSERVATIONS_AVAILABLE**, **258 PARTIAL_DATA**, **77 WAIT_FOR_DATA**.
- VCP observer: **2,023 COMPLETE**, **565 WAIT_FOR_DATA**. All 2,588 rows explicitly carry `FalseVCPOutcomeStatus=NOT_EVALUATED_NO_APPROVED_FORWARD_HORIZON`; complete observations remain `VCPStatus=NOT_CLASSIFIED` rather than being promoted to a VCP category.
- Requested SIDEWAYS_ACCUMULATION / DIP_ACCUMULATION patterns remain `NOT_CLASSIFIED_PENDING_APPROVED_RULES`. No category thresholds were invented.
- Safety assertions in the run summary: `track1_artifacts_unchanged=true`, `network_fetches=0`, `telegram_enabled=false`, `production_scanner_called=false`. All three observer error fields are null.
- Artifact: `track2-full-mainboard-offline-42804931499` (artifact ID `13758437527`). It contains the cohort, three observer CSVs, coverage manifest and offline validation summary.
- **Conclusion:** the standalone Track 2 builder has now completed a successful real-data, full-Mainboard offline execution with exact cohort coverage and isolated outputs. This validates the standalone research reports only; it does **not** authorize scheduled workflow wiring or production scanner integration. Track 1, main branch and Master Specification remain unchanged.

## Track 2 status-quality audit — 10-Nov-2026

The uploaded real-data artifact was inspected at row and status-field level. This is a read-only analysis; no observer logic or eligibility behavior was changed.

### Delivery Quantity — WAIT breakdown
- The 2,588-row cohort is 2,385 EQ + 203 BE.
- All **203 BE symbols** report `INVALID_DELIVERY_QUANTITY` in each of the 5D/10D/20D windows. Cross-tab confirms the 203 rows are exactly the BE series; no EQ symbol has this reason. The implementation emits this reason when the source quantity is null/non-finite/negative. The report does not distinguish a structurally unavailable BE delivery quantity from a genuinely malformed numeric value. This should be clarified in diagnostics before interpreting these as data-quality failures.
- EQ coverage: **2,253 COMPLETE_5_10_20D**, **132 WAIT_FOR_DATA**. The EQ WAIT reason is `INSUFFICIENT_OR_MISSING_SYMBOL_SESSION_DATA`: 33 symbols fail 5D, 83 fail 10D, 132 fail 20D.
- These are observational statuses only; none of these values are a Track 1 eligibility gate.

### Potential Accumulation — partial/WAIT decomposition
- **2,253 OBSERVATIONS_AVAILABLE**.
- The **258 PARTIAL_DATA** rows split into:
  - **138 BE**: 20D price history complete, delivery evidence WAIT.
  - **120 EQ**: delivery evidence available, 20D price history WAIT.
- The **77 WAIT_FOR_DATA** rows have both price history and delivery evidence WAIT; this group contains **65 BE + 12 EQ**.
- Price-range coverage declines with longer lookbacks: 20D **2,391**, 50D **2,174**, 100D **1,867**, 200D **1,669** observations available.
- Pivot structure and all four EMA observations (20/44/50/200) are COMPLETE for **1,665** and WAIT for **923**. The implementation requires the symbol history to match the entire ordered market-session date set (201 dates) before producing pivots/EMAs. This is stricter than the separate 200-session range window and explains why the 200D range has four more available rows than pivot/EMA. Confirm whether full 201-session exact coverage is the intended contract; do not relax it without approval.

### VCP — missing-data observability gap
- **2,023 COMPLETE / 565 WAIT_FOR_DATA**. The implementation uses exactly 60 market sessions (three 20-session blocks) and requires a complete, unique, valid OHLC row for every one of those dates before either range or volume observations are produced.
- All 565 WAIT rows have both range and volume status WAIT. The current output does not expose a per-symbol reason or actual symbol-specific valid-session count, so it cannot distinguish insufficient listing history, missing session rows, duplicate dates, or invalid OHLC. Add diagnostic reason/count fields and tests before any attempt to reduce this WAIT population.
- For all 2,588 symbols, `FalseVCPOutcomeStatus=NOT_EVALUATED_NO_APPROVED_FORWARD_HORIZON`; this is intentional and must remain separate from the 60-session observation status.

### Current safe conclusion / next diagnostic work
1. Keep all Track 2 reports observational and separate from Track 1.
2. Add source-level diagnostic fields for BE delivery quantity missingness (missing vs malformed vs series not covered), without converting missing values to zero or treating BE as PASS.
3. Add VCP WAIT reason and per-symbol available/valid session counts; identify whether each WAIT is due to history length, missing date, duplicate date, invalid OHLC, or missing/invalid volume. Preserve WAIT unless the source evidence proves the required window complete.
4. Review the 201-date exact-history requirement for pivot/EMA and document the intended session contract; do not weaken it silently.
5. Re-run focused tests and the isolated offline validation after diagnostic-only changes. No Track 2 production wiring, Track 1 changes, main-branch changes or Master Specification edits are authorized by this audit.


## Latest diagnostic offline rerun — completed (10-Nov-2026)

- GitHub Actions run [42807562907](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/42807562907) — **SUCCESS**, audit branch commit `b7a3fc473abc6f5f8cd8a90fc834d2c4a184e27c`.
- The run restored the existing NSE Actions cache read-only, downloaded source EOD artifact from run `42634890331`, and completed Track 2 with no observer errors.
- Input and output cohort: **2,588 rows / 2,588 unique symbols**; zero duplicate and invalid symbols; `cohort_status=COMPLETE`.
- Historical input: **201 Bhavcopy sessions** (09-Nov as-of session plus 200 prior sessions); **21 Delivery report dates** from 12-Oct through 09-Nov; no Bhavcopy or Delivery cache errors.
- Delivery Quantity observer: **2,253 COMPLETE_5_10_20D / 335 WAIT_FOR_DATA**. The diagnostic observer CSV now distinguishes the 203 BE rows as `MISSING_DELIVERY_QUANTITY` in each 5D/10D/20D window; the remaining EQ rows are 2,253 complete plus 132 WAIT due to missing/insufficient symbol-session data. No missing quantity is converted to zero. Note: the merged cohort also retains original Track 1 source columns, where the older generic `INVALID_DELIVERY_QUANTITY` reason remains; use the dedicated Track 2 Delivery Quantity observer CSV for the new diagnostic reason fields.
- Potential Accumulation observer: **2,253 OBSERVATIONS_AVAILABLE / 258 PARTIAL_DATA / 77 WAIT_FOR_DATA**. Price-history coverage: 20D **2,391**, 50D **2,174**, 100D **1,867**, 200D **1,669**. Pivot structure and EMA20/44/50/200 remain **1,665 COMPLETE / 923 WAIT_FOR_DATA**. All 1,665 complete rows have exactly 201 symbol-history sessions; the pivot/EMA observer still requires exact match to the complete 201-date ordered session set. The separate 200D rolling-range observer has four more available rows (1,669), so the 201-session contract remains an explicit review item and was not relaxed.
- VCP observer: **2,023 COMPLETE / 565 WAIT_FOR_DATA**. The added diagnostics show all 565 WAIT rows have `MISSING_SYMBOL_SESSION_ROWS`; their 60-session window has 1–59 missing sessions, with no duplicate dates, missing/invalid OHLC rows, or missing/invalid volume rows reported in those WAIT rows. The volume status is `RANGE_WINDOW_INCOMPLETE` because the range window is not complete. This resolves the previous report-observability gap; it does not justify relaxing the 60-session requirement.
- All 2,588 rows remain `FalseVCPOutcomeStatus=NOT_EVALUATED_NO_APPROVED_FORWARD_HORIZON`. Requested sideways/dip patterns remain `NOT_CLASSIFIED_PENDING_APPROVED_RULES`; no classification thresholds were introduced.
- Safety assertions: `track1_artifacts_unchanged=true`, `network_fetches=0`, `telegram_enabled=false`, `production_scanner_called=false`. All three observer error fields are null. The separate Track 2 artifact uploaded successfully (artifact ID `13762065857`; name `track2-full-mainboard-offline-42807562907`).
- The run log confirms the isolated workflow did not call the production scanner, perform network fetches, or send Telegram messages. The source Track 1 artifact was unchanged.

### Updated diagnostic conclusion
1. The full-Mainboard standalone Track 2 execution and all three observer outputs now have exact 2,588-row cohort coverage.
2. The Delivery Quantity and VCP reason/count diagnostics are present in the dedicated observer artifacts; BE missing quantity remains WAIT and must not be interpreted as zero or as a malformed numeric value without source-contract evidence.
3. The 201-session pivot/EMA exact-history requirement remains unresolved as a contract decision. Do not relax it without an explicit approved decision and tests.
4. Track 2 remains an isolated observational research report. No scheduled EOD integration, production scanner wiring, Track 1 eligibility/ranking change, main-branch change, or Master Specification edit was made or authorized.


## 10. Verified raw Delivery source contract (09-Nov-2026 offline audit)

Offline validation run **42810173636** completed successfully on audit branch commit `1b6098009d1af88fa64cabf6d18e6ac5dd4fe16e`. It restored the existing cache read-only and audited all 21 cached Delivery report dates (2026-10-12 through 2026-11-09) against the 2,588-symbol Mainboard cohort. No NSE/network fetch occurred; Telegram was disabled; the production scanner was not called; protected Track 1 artifacts remained byte-for-byte unchanged.

### BE source rows
- The `DELIV_QTY` column exists in each of the 21 BE report files.
- Across those files there are **4,502 BE source rows**, and all **4,502 have missing/null DELIV_QTY**; no non-finite or negative quantity was observed.
- Across the 203 BE Mainboard candidates and 21 dates (4,263 candidate-date pairs), **3,542 source rows were present and all 3,542 had missing quantity**; **721 candidate-date pairs had no matching source row**. No duplicate source symbol rows were found.
- This verifies the raw cached-file condition behind the observer's `MISSING_DELIVERY_QUANTITY` status. It does **not** establish why NSE's BE records carry blank quantities or prove that BE delivery quantity should be treated as zero. Keep the value missing/WAIT; do not impute zero or change eligibility.

### EQ source rows
- The `DELIV_QTY` column exists in all 21 EQ report files.
- Across the 2,385 EQ Mainboard candidates and 21 dates (50,085 candidate-date pairs), **48,800 matching source rows** had valid numeric quantity, **1,285 pairs** had no matching source row, and **one** matching row had quantity zero. No missing, non-finite or negative quantity was found among matching EQ rows; no duplicate source symbol rows were found.
- The zero quantity is retained as zero, distinct from missing. Existing completeness rules still determine WAIT status for incomplete windows.

### 201-session Pivot/EMA contract
The cached market calendar has 201 distinct sessions including 09-Nov-2026: 200 prior complete sessions plus the current EOD as-of session. The symbol-level Pivot/EMA observer requires the full ordered 201-session history. On this cohort, Pivot Structure and EMA20/44/50/200 each report **1,665 COMPLETE / 923 WAIT_FOR_DATA**. Four symbols (`BHARATCOAL`, `CENTEXT`, `SPCENET`, `SETL`) have a complete trailing 200-session price range but lack the additional earliest date required by the 201-session Pivot/EMA contract. This is a distinct window contract, not grounds to relax the 201-session requirement.

### Track 2 run result and safety
- Full Mainboard cohort: **2,588/2,588** rows, exact unique-symbol coverage, zero duplicates/invalid symbols.
- Delivery Quantity: **2,253 COMPLETE_5_10_20D / 335 WAIT_FOR_DATA**.
- Potential Accumulation: **2,253 OBSERVATIONS_AVAILABLE / 258 PARTIAL_DATA / 77 WAIT_FOR_DATA**.
- VCP: **2,023 COMPLETE / 565 WAIT_FOR_DATA**. All 565 VCP WAIT rows are due to missing symbol-session rows in the 60-session window; no duplicate dates, missing/invalid OHLC rows or missing/invalid volume rows were reported for those WAIT rows.
- Observer errors: none. Research categories remain `NOT_CLASSIFIED_PENDING_APPROVED_RULES`; false-VCP forward outcomes remain unevaluated.
- Workflow artifact: `track2-full-mainboard-offline-42810173636` (artifact ID 13761744331).

These are source/data-quality findings only. They do not change Track 1 gates, Mainboard membership, scanner scheduling, watchlist eligibility, or the Master Specification. Track 2 remains standalone and non-gating.


## 11. Shadow-store free-text redaction hardening (audit branch only)

A separate pre-integration security review found that the shadow store's allow-listed field names and forbidden-key checks did not inspect free-text **values**. This could allow sensitive content embedded in `ReasonText`, `SourceReport`, source report names, or otherwise allow-listed string values to be persisted.

The audit branch now applies recursive text-value checks at snapshot/event construction and persisted-record validation. The denylist rejects common credential assignments (including token/credential/API-key/password/secret fields), Bearer strings, common GitHub/AWS token formats, private-key headers, URLs containing query strings or URL user-info, email addresses, phone-like digit sequences, control characters, and text values over 2,000 characters. This is a defensive heuristic, not a guarantee that every possible secret or account identifier can be recognized; curated input and least-data collection remain required.

Regression validation run **42811907344** completed SUCCESS on commit `8506a46bf53d5398aff569242fbb12b1541f3645`: Python compilation PASS; **411 pytest tests passed**; **33 V8 regression tests passed**; **43 sector/news/official-index tests passed**. The initial redaction test run exposed two gaps (generic `token=` and `credential=` assignments); those patterns were added and the full CI rerun passed.

This remains an isolated helper hardening change. The signal shadow store is still not wired into the production scanner or scheduled EOD workflow; no signal snapshots were deployed or written. Main branch, Master Specification, scanner selection, and trading gates remain unchanged.
