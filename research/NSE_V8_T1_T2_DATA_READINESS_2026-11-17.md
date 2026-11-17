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
