# NSE V8 T1/T2 research data-readiness audit

Research-only utility. It does not modify the scanner, Master Specification, caches, scheduled workflows, risk rules, or broker integrations.

## Purpose
Audit archived EOD signal reports against the existing read-only data/bhavcopy cache and determine whether each signal has:
- valid point-in-time EntryPricePlan and StopLossPlan;
- two distinct explicit overhead resistance levels above planned entry;
- the next 20 official NSE sessions and validated EQ OHLC rows for that symbol.

Target 1 is the nearest distinct verified overhead level; Target 2 is the next distinct verified overhead level. No synthetic target or arbitrary percentage/2R target is created. If only one valid resistance exists, T2 remains WAIT_FOR_DATA.

## Run
python t1_t2_data_readiness.py --signals outputs/v8_eod_watchlist.csv

Multiple archived signal CSVs can be supplied. Use copies extracted from historical workflow artifacts; do not overwrite or alter the production cache.

Outputs:
- outputs/t1_t2_readiness/t1_t2_data_readiness.csv
- outputs/t1_t2_readiness/price_cache_validation_errors.txt

This is a data-readiness audit only, not a trading backtest. Entry fill timing, stop/target trigger and gap execution, fees/slippage, trailing stop, and time exit remain separate policy decisions. Same-day stop/target collision is stop-first per user-approved research rule. No production behavior changes.

## Validation
python -m unittest -v test_t1_t2_data_readiness


## First archived-report inspection (workflow run 42830154736)

The archived EOD artifact nse-v8-reports-42830154736 was downloaded and its outputs/v8_eod_watchlist.csv inspected offline. It contains 54 rows across signal AsOfDates 2026-10-28 through 2026-11-09 (not one common signal date).

| Check | Rows |
|---|---:|
| Archived EOD rows | 54 |
| Valid positive EntryPricePlan | 54 |
| Valid positive StopLossPlan | 54 |
| Existing verified TargetPricePlan | 48 |
| Distinct verified T1 available from the stored structural fields | 48 |
| Distinct verified T2 available from the next higher stored structural level | 37 |
| No T1 available | 6 |
| T1 available but no distinct T2 | 11 |

This is a point-in-time plan-field availability count only. It is not a win-rate or return result. The current cache's per-symbol 5/10/20 forward OHLC coverage must still be measured in the read-only Actions workflow. No target is invented for the 17 rows without a distinct T2.


## Historical price-cache audit — workflow run 44074064336

The cache was restored using the exact path manifest from the main NSE scheduled workflow. The cache key restored was nse-bhavcopy-Linux-main-44069755492. This fixed an initial cache miss caused by using only a partial path manifest.

- Bhavcopy files restored: 202
- Delivery report files restored: 200
- Validated EQ OHLC rows: 506,231
- Cache validation errors: 0
- Cache writes / downloads / pruning: none; this run restored and read the cache only.

The 54 archived EOD rows were matched to the restored price history:
- 5-session forward OHLC complete: 50/54; 4 rows have one or more missing symbol-session bars.
- 10-session forward OHLC complete: 16/54.
- 20-session forward OHLC complete: 0/54 (the 20-session future horizon has not elapsed for these signals yet).
- T1 plan plus complete 5-session OHLC: 44 rows.
- T2 plan plus complete 5-session OHLC: 35 rows.
- T1 plan plus complete 10-session OHLC: 14 rows.
- T2 plan plus complete 10-session OHLC: 10 rows.

These are data-coverage counts only. No stop/target touch outcomes or returns have been computed. The research tool now reports separate T1/T2 data-readiness flags for each 5D/10D/20D horizon so an incomplete 20D horizon does not hide already-complete 5D/10D data.


### Per-scenario readiness (workflow run 44074326424)

The corrected report separates target scenarios and measurement horizons:

| Data readiness | Rows |
|---|---:|
| T1 + 5D OHLC | 44 |
| T2 + 5D OHLC | 35 |
| T1 + 10D OHLC | 14 |
| T2 + 10D OHLC | 10 |
| T1 + 20D OHLC | 0 |
| T2 + 20D OHLC | 0 |

Overall, 44/54 rows have at least one scenario/horizon with complete data. Ten rows remain WAIT_FOR_DATA for all current horizons. The 20D horizon is incomplete for all 54 rows; this is expected from the available as-of dates and does not mean the underlying price history is invalid.

Validation:
- New focused research tests: 8 passed.
- Full NSE V8 CI: success, including compile, unit/data-audit tests, V8 regression script and sector/news/official-index tests.
- No production files, Master Specification, Bhavcopy cache, Delivery cache, or scheduled production workflow changed.


## Approved entry assumption

The user approved the research entry timing: **enter at the Open of the next official NSE trading session after the EOD signal date**. The audit now records:
- EntryExecutionRule = NEXT_OFFICIAL_SESSION_OPEN
- EntryExecutionPrice = next official session's validated EQ Open
- EntryExecutionStatus = ENTRY_READY only when that next-session Open exists and is valid; otherwise WAIT_FOR_DATA.

This is an explicit research assumption only. It does not change production EntryPricePlan, production scanner behavior, or place orders. All T1/T2 horizon readiness flags now require a valid next-session Open as well as valid point-in-time Entry/Stop and the relevant forward OHLC coverage.


### Entry-gap integrity

The research audit validates the next-session Open against the stored initial stop. If the next-session Open is at or below the initial stop, it does not create an entry and marks the row WAIT_FOR_DATA for execution analysis. T1/T2 are recalculated as the nearest two distinct verified structural levels strictly above the actual next-session Open. A gap above the prior planned T1 therefore does not count an already-underneath resistance as a valid target; the next verified overhead levels are used instead. No synthetic targets are created.
