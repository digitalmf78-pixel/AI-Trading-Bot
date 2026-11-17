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
