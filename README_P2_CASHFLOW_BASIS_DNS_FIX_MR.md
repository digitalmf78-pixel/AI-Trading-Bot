# NSE V8 P2 Cash Flow Basis + DNS Resilience Patch

Baseline: `AI-Trading-Bot-main(7).zip` (uploaded 2026-10-31).

## Changes

1. `fundamental_data_provider.py`
   - Cash Flow quarter-end alignment alone is no longer treated as proof that values are standalone quarters.
   - TTM is allowed only when the provider explicitly declares `STANDALONE_QUARTERLY` (or `QUARTERLY_STANDALONE`) via `ticker.quarterly_cashflow_period_basis` or `DataFrame.attrs['period_basis']`.
   - Unknown/YTD/unlabelled period basis fails closed with `CASHFLOW_PERIOD_BASIS_UNVERIFIED`; no Cash Flow TTM is manufactured.
   - Adds `CashFlowPeriodBasis` to audit diagnostics.

2. `nse_xbrl_fetch.py`
   - Adds allow-listed HTTPS downloader for official NSE XBRL hosts.
   - Retries transient DNS resolution failures with bounded exponential backoff and HTTP transient errors.
   - Keeps normal TLS certificate verification enabled; does not hardcode IP addresses or bypass DNS/TLS.
   - Rejects malformed XML and HTML challenge pages.

3. Tests updated/added to prove explicit-basis acceptance, unknown-basis fail-closed behavior, transient DNS retry, host allow-listing, and HTML challenge rejection.

## Validation

Focused tests:
`pytest -q test_nse_xbrl_fetch.py test_fundamental_data_provider.py test_fundamental_shortlist_and_alignment.py test_fundamental_official_filings.py`
Result: **44 passed**.

Full repository `pytest -q` did not finish within the available execution window; no full-suite PASS is claimed.

## Important limitation

This patch does NOT yet parse XBRL financial facts or normalize cumulative YTD cash-flow facts. That requires inspecting actual NSE XML taxonomy/context and matching facts. Until that is implemented, unknown basis remains unavailable rather than incorrectly summed. DNS retries address transient DNS failures; a permanently broken resolver/network must be solved by the execution environment. Run the downloader from GitHub Actions (which has its own network/DNS) to determine whether the earlier DNS error was local-environment-specific.

No master specification, selection threshold, Delivery/RVOL/Liquidity rule, or other trading filter is changed.
