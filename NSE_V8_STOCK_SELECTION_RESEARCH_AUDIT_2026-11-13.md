# Stock Selection Research — Initial Data Audit
**Date:** 13-Nov-2026  
**Repository:** digitalmf78-pixel/AI-Trading-Bot  
**Research branch:** `research/stock-selection-backtest-2026-11-13`  
**Evidence artifact:** EOD workflow run `43435420965` (`nse-v8-reports-43435420965`)  
**Scope:** Research-only. No production scanner rules or scores changed.

## 1. Safety and change-control
- The Master Specification remains immutable.
- Track 1 production eligibility and all approved Delivery/RVOL/Liquidity rules remain unchanged.
- Bhavcopy cache is read-only for this research.
- No experimental score, threshold, VCP classification, or new rejection gate is enabled.
- Missing/duplicate/invalid data remains `WAIT_FOR_DATA`; it is never imputed as zero.
- Research signals must be point-in-time. Forward prices may be used only in a separate outcome table after signal features have been frozen.

## 2. Evidence inspected
The downloaded EOD artifact contains the full Track 2 Mainboard cohort and the corresponding Delivery Quantity, Potential Accumulation, and VCP observation reports, plus the delivery-history backfill coverage and existing signal log.

### 2.1 Delivery history backfill
| Check | Observed result |
|---|---:|
| Requested price sessions | 200 |
| Requested date range | 2026-01-22 to 2026-11-13 |
| Valid Delivery report dates | 200 |
| Reused existing cache | 200 |
| New downloads in this run | 0 |
| Missing/rejected reports | 0 |
| Bhavcopy cache modified | No |
| Backfill status | COMPLETE |

This verifies report-date archive coverage for the requested 200-session window. It does **not** mean every symbol has complete Delivery Quantity on all 200 dates; per-symbol completeness must be measured separately.

### 2.2 Track 2 cohort and observer coverage
| Dataset | Rows | Status distribution |
|---|---:|---|
| Full Mainboard research cohort | 2,593 | 2,593 unique valid symbols; no duplicate or invalid symbol rows |
| Delivery Quantity | 2,593 | 2,256 COMPLETE_5_10_20D; 337 WAIT_FOR_DATA |
| Potential Accumulation | 2,593 | 2,256 OBSERVATIONS_AVAILABLE; 273 PARTIAL_DATA; 64 WAIT_FOR_DATA |
| VCP | 2,593 | 2,133 COMPLETE; 460 WAIT_FOR_DATA |

The cohort manifest reports 21 Delivery source dates from 2026-10-15 through 2026-11-13. The Track 2 report is a full Mainboard observational cohort, not a production shortlist.

### 2.3 Price-history depth
| Measure | Complete | Incomplete / WAIT |
|---|---:|---:|
| Exact 200-session range / EMA200 history | 1,671 | 922 |
| 100-session price range | 1,870 | 723 |
| 50-session price range | 2,185 | 408 |
| 20-session price range | 2,402 | 191 |

For the 200-session study, the available artifact therefore supports a fully observed 200-session price-history cohort of 1,671 symbols, not all 2,593. Any comparison must show this coverage denominator and must not silently exclude the remaining symbols.

### 2.4 VCP window integrity
- VCP observation window: 60 sessions, split into three sequential 20-session blocks.
- 2,133 symbols have complete 60-session VCP observations.
- 460 symbols are WAIT_FOR_DATA because of missing symbol-session rows.
- The current VCP module is observational; complete observations still carry `VCPStatus=NOT_CLASSIFIED`.
- No confirmed VCP label or VCP score can be inferred from these rows.

### 2.5 Existing forward-outcome readiness
- The artifact's `signal_log.csv` contains 1,064 rows across four EOD dates (2026-11-09, 2026-11-11, 2026-11-12, 2026-11-13).
- Result5D, Result10D, Result20D, MFE and MAE are all blank in this artifact.
- Four daily cohorts are not enough to validate a new strategy, and the existing log is not yet a completed forward-outcome sample.
- The separate RVOL historical comparison is not an Accumulation/VCP backtest. Its own caveats include overlapping daily signals, no transaction-cost/slippage model, current-cache survivorship, and missing point-in-time historical Mainboard/fundamental classifications.

## 3. Findings and blockers
1. **Archive-level Delivery backfill is complete**, and this run reused 200 valid report dates without touching Bhavcopy.
2. **Per-symbol coverage is not uniform.** Delivery Quantity 20D and 200-session price/EMA history have material WAIT cohorts; reports must retain them.
3. **Current Accumulation and VCP outputs are single-as-of observations.** They are not yet a multi-date historical signal panel, so they cannot by themselves establish whether a setup predicted future returns.
4. **No usable forward outcome columns are populated in the current signal log artifact.** The 5D/10D/20D outcome engine must be run and independently audited before scoring claims.
5. **A point-in-time replay harness is required.** For each historical as-of date, features must use only data available on or before that date; forward OHLC is joined only after the feature snapshot is frozen.
6. **Survivorship/universe limitation:** the current Mainboard cohort is not a historically reconstructed Mainboard universe for each past date. Results using today's universe must be labelled current-universe retrospective, not survivorship-free historical results.

## 4. Approved research sequence
### Phase A — Data and point-in-time contract
- Reconcile the official NSE trading calendar, Bhavcopy session dates, Delivery report dates, symbol/series identity, duplicates, corporate-action adjustments, and source coverage.
- Establish historical as-of cohorts. Clearly label current-universe limitations until dated historical Mainboard membership is available.
- Confirm no future row enters feature construction and that every feature has an as-of timestamp and source.

### Phase B — Accumulation research
- Build separate observational hypotheses for sideways accumulation and dip accumulation; do not equate high Delivery % alone with institutional accumulation.
- Evaluate price stability/range, delivery quantity and percentage, traded volume, up-day/down-day delivery/price response, selling pressure, and higher-low/pivot evidence.
- Compare each feature independently and in combination against forward 5D/10D/20D returns, MFE and MAE.
- Do not create a 100-point score until definitions and out-of-sample performance are documented.

### Phase C — VCP research
- Validate contraction depth and sequence, volume dry-up, base quality, and breakout follow-through with explicit, pre-registered rules.
- Compare VCP candidates with matched non-VCP controls from the same as-of universe.
- Evaluate false positives, time-to-breakout, 5D/10D/20D returns, MFE/MAE, and missing-data rates.
- Keep `NOT_CLASSIFIED` until rules are approved and tested.

### Phase D — Independent scoring and combined ranking
Only after Phases A–C:
- Test Accumulation, VCP, Trend, Fundamentals, and Sector Strength independently.
- Evaluate Market Regime as a contextual modifier/stratification variable before considering any score.
- Test the proposed 25/25/20/20/10 weighting as a hypothesis, not as an approved production rule.
- Use chronological train/validation/test splits or walk-forward evaluation; avoid random splits and leakage.
- Include realistic fees, slippage, liquidity/position sizing, overlapping-signal handling, drawdown and portfolio-level constraints.
- Report confidence intervals/sample counts and compare with simple baselines.

## 5. Exit criteria before any production proposal
- Reproducible historical feature snapshots and forward outcome labels.
- Point-in-time leakage tests and explicit historical-universe caveats.
- Coverage and WAIT_FOR_DATA tables for every cohort and horizon.
- Baseline vs Accumulation-only vs VCP-only vs combined results.
- 5D/10D/20D returns, win rate, median/mean return, profit factor, MFE/MAE, drawdown and transaction-cost sensitivity.
- Out-of-sample / walk-forward evidence that the proposed method adds value.
- Separate user approval before any production code or Master Specification change.

## 6. Current decision
**DATA AUDIT: INITIAL PASS WITH MATERIAL LIMITATIONS.**  
**ACCUMULATION BACKTEST: NOT STARTED.**  
**VCP BACKTEST: NOT STARTED.**  
**SCORING / COMPOSITE RANKING: NOT IMPLEMENTED.**  
**PRODUCTION CHANGES: NONE.**

The next implementation task is a research-only point-in-time replay/backtest harness that consumes the existing Bhavcopy and Delivery caches read-only, writes dated feature/outcome artifacts, and never changes Track 1 selection.


## 7. Critical lookback-versus-forward-history constraint
The inspected Bhavcopy history spans 201 official sessions (2026-01-16 through 2026-11-13). It can produce today's 200-session observations, but it cannot produce a valid historical sample for a 200-session lookback **and** a subsequent 5D/10D/20D outcome:
- At earlier as-of dates, 200 prior sessions are not yet available.
- At the latest as-of date, there are no future sessions in the cache.
- Therefore the current cache contains **zero** as-of dates that simultaneously have a complete 200-session lookback and a complete forward 20-session outcome.

Minimum history arithmetic:
- 220 sessions are needed for at least one mature 200-session lookback date plus 20 future sessions.
- Approximately 420 contiguous official sessions are needed to evaluate 200 separate mature as-of dates and retain a complete 20-session forward horizon for the last tested date.

**Next data task:** build a separate research-only historical price cache (for example, `data/research/bhavcopy_backtest/`) from official NSE Bhavcopy sources, targeting at least 420 valid official sessions. Do not rewrite, prune, or replace `data/bhavcopy/`; the existing production Bhavcopy cache remains untouched. Validate each filename date against the file's internal date, EQ identity, duplicate symbol/session rows, OHLCV structure, gaps and official calendar before any backtest. If the source cannot supply the full period, report the actual supported date range and reduce the tested lookback explicitly rather than synthesizing history.


## 7. Isolated historical Bhavcopy backfill implementation (research branch)
- Added `scripts/research_bhavcopy_backfill.py`; it reads the official NSE CM ZIP archive pattern and writes only to `data/research/bhavcopy_backtest/`.
- The production `data/bhavcopy/` directory is not imported as a destination, modified, or pruned by this downloader.
- Default target is 420 official NSE sessions ending on/before the requested date; the calendar is read from the repository's official NSE Capital Market calendar and unknown years fail closed.
- Each ZIP must contain exactly one CSV. Each CSV is validated against its internal business date, required symbol/series/OHLCV columns, EQ-row presence, duplicate EQ symbol/session identities, finite/non-negative volume and valid positive OHLC candle structure.
- Valid files are staged, re-read and revalidated before atomic replacement. Existing valid research-cache files are reused. HTTP 404, invalid responses, request failures and capped/unattempted dates remain explicit in the JSON manifest.
- Added `test_research_bhavcopy_backfill.py` for calendar count, date mismatch, duplicate symbol, missing fields, OHLC integrity, ZIP parsing and malformed response coverage.
- Added manual-only workflow `.github/workflows/research-bhavcopy-backfill.yml`; the research cache is stored in a separately namespaced GitHub Actions cache and the manifest is uploaded as an artifact. It does not alter the scheduled production EOD workflow or scanner.
- This is downloader implementation only. No 420-session archive fetch has yet been run, and no Accumulation/VCP backtest result is claimed until coverage is verified.
