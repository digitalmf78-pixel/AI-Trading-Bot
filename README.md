# NSE V8 Sector Mapping Diagnostic Fix

## Scope
Replace only `sector_data.py` in `digitalmf78-pixel/AI-Trading-Bot`.

## Findings from report/log
- `VALUE` is Mirae Asset Nifty 500 Value 50 ETF. Its benchmark is a broad-market factor index, not a tracked Nifty sector index.
- `DIVIDEND` is Mirae Asset BSE 500 Dividend Leaders 50 ETF. Its benchmark is a BSE index, not a tracked Nifty sector index.
- The module was treating both as `ETF_UNDERLYING_INDEX_REQUIRED`, even though the benchmark is known and unsuitable for this module's sector-strength calculation. The replacement records them as `ETF_UNDERLYING_INDEX_UNSUPPORTED`, with official evidence and no sector assignment.
- The log confirms the NSE quote API returned HTTP 403 twice for BEDMUTHA, JKIPL and AROGRANITE. The rendered-page fallback returned HTTP 200 but did not contain a parseable `Basic Industry` label. Those three remain `WAIT_FOR_DATA`; no sector is guessed.
- `PSUBANKADD` remains mapped to Nifty PSU Bank.
- No change to Delivery Filter, technical setup, risk/reward, news/catalyst, or the V8 master strategy.

## Validation
Run:
`python -m py_compile sector_data.py test_etf_underlying_mapping.py`
`python -m unittest -v test_etf_underlying_mapping.py`

These are local tests only. After replacement, run the existing GitHub Actions workflow and inspect the NEW artifact/log. Do not treat local tests as proof of live workflow success.
