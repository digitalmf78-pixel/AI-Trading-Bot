# NSE V8 P2 Cash Flow Basis + DNS Workflow Integration

Apply this patch on top of the latest `AI-Trading-Bot-main(7).zip` baseline.

## Included
- `fundamental_data_provider.py`: fail-closed Cash Flow period-basis validation; unknown/YTD basis cannot be summed as standalone TTM.
- `nse_xbrl_fetch.py`: HTTPS allow-listed NSE XML fetcher with bounded DNS/HTTP retries, normal TLS verification, XML validation.
- `test_nse_xbrl_fetch.py`: mocked DNS retry, host allow-list and HTML challenge tests.
- Updated `test_fundamental_shortlist_and_alignment.py`.
- Updated `.github/workflows/nse-test-scheduled.yml`: compile-checks the new module, runs P2 tests in Actions, and logs DNS reachability for official NSE hosts.

## Apply
Extract the ZIP at repository root and replace the included files, including `.github/workflows/nse-test-scheduled.yml`. Commit and push, then run the `NSE Data Test` workflow manually.

## Validation limits
Unit tests simulate transient DNS failure; they do not prove that a permanent resolver failure can be fixed by application code. The workflow DNS step reports the actual GitHub runner resolution result but is non-blocking.

This patch does not implement XBRL fact/context parsing or YTD normalization. It prevents unverified Cash Flow period values from producing TTM. P2 remains incomplete until actual official XML contexts are parsed and validated. No master spec, RVOL, Delivery, Liquidity, or other trading thresholds are changed.
