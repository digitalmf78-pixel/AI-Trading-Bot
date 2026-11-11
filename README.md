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

## Free, no-key multi-source fundamental enrichment

- Yahoo Finance via `yfinance` remains enabled without an API key. It supplies the existing statement, ratio, cash-flow and valuation snapshot fields where available.
- The no-key fallback queries **both Moneycontrol and Tickertape** through the Apache-2.0 `Bharat-sm-data` open-source client. It attempts each provider rather than stopping at first success, and requests quarterly/annual income statements, balance sheet, cash flow, ratios, margins, scorecard, shareholding, dividend history, mutual-fund holdings and smallcase holdings where the source exposes them.
- Free-source collection is enabled in the scheduled EOD workflow with a conservative budget of **10 symbols per run** and a **7-day per-symbol retry cooldown**. Tune `FREE_FUNDAMENTAL_MAX_SYMBOLS_PER_RUN` and `FREE_FUNDAMENTAL_RETRY_DAYS` only after reviewing rate limits and the upstream sites' terms.
- The Moneycontrol/Tickertape client uses public website endpoints, not supported official public APIs. Upstream sites can change, block automated requests, or restrict scraping/redistribution. Use only where permitted for personal research; no raw third-party statement payloads are committed by this adapter.
- NSE Integrated Filing / XBRL remains the official verification source. Yahoo, Moneycontrol and Tickertape values remain provider evidence until reconciled with an official filing and matching financial period/basis.
- Mapped additional fields include gross/operating/net margins, current/quick ratios, asset turnover, EPS, book value per share and promoter/FII/DII/public holding/pledge percentages. They are passed through to the fundamental report but are not added to the existing Fundamental Score or threshold gates. Each filled metric records its source and URL. Existing/manual values are never overwritten. When metrics come from different providers, the row is marked `MULTI_SOURCE_METRIC_LEVEL` / `UNVERIFIED`; no mixed-source statement is treated as a single aligned filing or promoted to official verification.
- No paid API, API key, subscription or provider login is required for the enabled sources. Investing.com and Screener scraping are not enabled: their current connectors require extra browser/login handling and need separate stability/terms validation.
- This is data enrichment only. It does not change NSE Mainboard membership, RVOL, Delivery A/B, liquidity, technical filters, ranking thresholds, or candidate retention. Provider failure never rejects a candidate.

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
- Latest CI (run 42807562406): Python compilation PASS; **403 pytest tests passed**, **33 V8 regression tests PASS**, and **43 sector/news/official-index tests PASS**.
- Real-data offline validation (run 42807562907, source EOD 09-Nov-2026) completed successfully using the existing cached 201-session Bhavcopy history and 21 Delivery report dates. Exact cohort parity: **2,588/2,588** unique Mainboard symbols, zero duplicates/invalid symbols. Delivery Quantity: 2,253 COMPLETE / 335 WAIT; Potential Accumulation: 2,253 OBSERVATIONS_AVAILABLE / 258 PARTIAL_DATA / 77 WAIT; VCP: 2,023 COMPLETE / 565 WAIT. All observer errors were null.
- Diagnostic findings: 203 BE rows have missing Delivery Quantity in the dedicated Track 2 observer report; 132 EQ rows WAIT on Delivery Quantity session coverage. All 565 VCP WAIT rows are due to missing symbol-session rows in the 60-session window; no duplicate dates or invalid OHLCV rows were reported in those WAIT rows. Pivot/EMA observations require exact 201-session symbol history (1,665 COMPLETE / 923 WAIT); this contract remains under review and was not relaxed.
- Safety checks passed: Track 1 source artifacts unchanged; zero network fetches; Telegram disabled; production scanner not called. SIDEWAYS/DIP remain NOT_CLASSIFIED_PENDING_APPROVED_RULES and false-VCP forward outcomes remain unevaluated.
- Track 2 remains an isolated, non-gating report and is **not wired into the scheduled EOD workflow**. Audit branch only; Master Specification, main branch and production scanner remain unchanged. See `NSE_V8_TRACK2_FULL_MAINBOARD_ACCUMULATION_DESIGN_AUDIT_2026-11-10.md` for detailed diagnostics and the unresolved 201-session contract.


### Track 2 raw-source audit update (10-Nov-2026)
- Offline Track 2 validation run [42810173636](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/42810173636) completed SUCCESS; artifact `track2-full-mainboard-offline-42810173636` (ID 13761744331).
- Raw Delivery source audit across 21 report dates confirmed the BE `DELIV_QTY` column is present but all 4,502 BE source rows have blank/missing quantity. Of 4,263 BE candidate-date pairs, 3,542 source rows exist (all quantities missing) and 721 have no matching source row. Do not convert missing to zero; the reason for blank BE values is not established.
- EQ candidate-date audit: 48,800 valid quantity rows, 1,285 missing source rows and one explicit zero; no duplicate source symbol rows.
- Pivot/EMA exact history contract remains 201 symbol sessions (200 prior + current EOD): 1,665 COMPLETE / 923 WAIT. Four symbols have complete 200D range but lack the additional earliest session.
- Track 2 coverage: 2,588/2,588; Delivery Quantity 2,253 complete / 335 WAIT; Potential Accumulation 2,253 available / 258 partial / 77 WAIT; VCP 2,023 complete / 565 WAIT. All observer errors null.
- Safety: zero network fetches, Telegram disabled, production scanner not called, Track 1 artifacts unchanged. Track 2 remains standalone/non-gating; Master Specification and main branch unchanged. Detailed source audit is in `NSE_V8_TRACK2_FULL_MAINBOARD_ACCUMULATION_DESIGN_AUDIT_2026-11-10.md`.


### Shadow-store safety audit (10-Nov-2026)
- Hardened `signal_shadow_store.py` so allow-listed text values and stage-event free text are scanned for common credentials/tokens, Bearer strings, private URLs, email/phone-like identifiers, control characters and oversized text. Checks run both when building records and when validating persisted records.
- CI run [42811907344](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/42811907344) passed: compilation PASS, **411 pytest tests**, **33 V8 regression tests**, and **43 sector/news/official-index tests**.
- The checks are heuristic and do not replace curated input/least-data rules. Shadow store remains standalone and is not connected to production scanner or scheduled EOD; no signal snapshots were deployed. Main branch and Master Specification remain unchanged. See the Track 2 design/data-contract audit for details.


### Cohort Assembly validation update (10-Nov-2026)
- Strengthened tests for the canonical **2,588-row Mainboard cohort** vs the **758-row Delivery A/B report**: all 2,588 remain; 758 stage rows present; 1,830 are `NOT_EVALUATED` where the downstream report has no row.
- Confirmed native WAIT/reject statuses are preserved, News/Corporate Event one-to-many evidence stays separate and does not inflate stage coverage counts, and source frames are not mutated.
- CI [42812305661](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/42812305661) SUCCESS: **415 pytest**, **33 V8 regression**, **43 sector/news/index tests**; compilation PASS.
- This is synthetic contract validation, not yet a real-EOD integrated cohort run. The helper remains standalone/non-gating; no production wiring was made.


### News / Corporate Events window audit (10-Nov-2026)
- Confirmed current News window is **5 calendar days** (EOD: start 00:00 IST at EOD−4 through 22:00 IST EOD; PREMARKET: start local date−4 through 09:15). Recorded data-contract target remains **7 days**; no runtime change applied.
- Confirmed issuer announcement discovery uses a **90-day lookback**, while explicit future EventDates are currently marked confirmed without a separate next-20-calendar-day display cap. Added a characterization test; this is documented current behavior, not an approved final horizon.
- Keep 90-day discovery separate from the 20-day display horizon; do not reduce source lookback. Any future alignment requires explicit approval and real-EOD validation.
- CI [42812650737](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/42812650737) SUCCESS: **416 pytest**, **33 V8 regression**, **43 sector/news/index tests**; compilation PASS. No runtime behavior changed.


## News/Catalyst window — approved 7 calendar days (10-Nov-2026)

- EOD: 00:00 IST on EOD date minus six calendar days through 22:00 IST on EOD date.
- PREMARKET: 00:00 IST on local scan date minus six calendar days through 09:15 IST on local scan date.
- Both windows cover seven calendar dates inclusive, including weekends/holidays.
- This changes News evidence lookback only; Corporate Events retains its separate 90-calendar-day source-discovery lookback. Official evidence remains primary and secondary coverage remains unverified.
- The original Master Specification is not rewritten; see the dated implementation audit for validation status.


## Signal shadow-store status — audit only (10-Nov-2026)

The append-only JSONL snapshot/event helper and full-Mainboard cohort assembly helper remain standalone and are **not** connected to the production scanner or scheduled EOD workflow. The shadow-store audit covers immutable identity/digests, exact retry no-ops, conflicts, tamper detection, and free-text redaction. A one-shot `source_reports` generator-consumption defect was fixed with a regression test. Before integration, define the date partition/manifest and retention policy, validate stage-event-to-snapshot identity linkage, and implement serialized single-writer GitHub persistence with restart/retry tests. No real EOD shadow snapshots or forward outcomes exist yet. See the dated Track 2/Shadow Store audit for detailed findings. 


### Shadow persistence writer — design checkpoint (10-Nov-2026)

A dedicated, opt-in shadow persistence workflow is the recommended future design; it is not implemented or enabled. The standalone JSONL helper now stages validated complete partitions in a same-directory temporary file, fsyncs, atomically replaces the target, and cleans up after a simulated replace failure. Latest CI run 42826235237 passed: 421 pytest + 33 V8 regression tests. The future writer must still serialize all writers with one shared GitHub Actions concurrency group, use optimistic latest-branch fetch/push retries (never force-push), and make reruns idempotent with an auditable manifest. It must remain separate from production EOD scanning, NSE fetching and Telegram delivery. Multi-run race, fsync-failure, rerun, tamper and redaction tests remain required before enabling writes. See the dated audit report for the full protocol and open decisions.


- Further atomic persistence tests passed in CI run 42826604469: simulated staged-file fsync failure leaves the old partition intact; simulated parent-directory fsync failure is recovered by an idempotent retry. New files default to mode 0600; existing permissions are preserved. This remains single-process helper validation, not multi-writer workflow validation.
