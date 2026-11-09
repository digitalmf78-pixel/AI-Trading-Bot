# NSE V8 — Nifty Index Context Stale-Cache Fallback

## Observed failure
Run 42602196585 (NSE Data Test #230), commit e3daca57381a9adae2bfd0234945032496c95808, completed all compile/regression tests and ran the stock scan through 58 liquidity-qualified candidates. It then failed in STEP 12:

`RuntimeError: Nifty history does not contain the latest NSE EOD date 2026-11-08.`

The fetch URL is Yahoo Finance chart endpoint for `^NSEI`. The workflow selected latest EOD date 2026-11-08, which was a special Sunday Muhurat session in the repository's official calendar, but provider response did not return a close aligned to that exact date. This failure occurred after most scanner work and artifacts had already been generated.

## Patch behavior
- If cache has at least 50 valid closes, attempt provider refresh.
- If provider refresh fails or lacks exact requested EOD date, return the valid stale cache without overwriting it.
- Log `[NIFTY][STALE_CACHE_FALLBACK]` with the last cached date.
- Downstream market-regime consumers must independently require exact as-of date; otherwise they should emit WAIT_FOR_DATA and must not treat stale context as current.
- If cache has fewer than 50 valid closes and refresh cannot provide aligned data, fail closed with a clear diagnostic.
- Persist newly downloaded history only when it includes the requested exact EOD date and at least 50 closes.
- No Delivery A/B, RVOL, liquidity, fundamental selection, trading-calendar or master-specification rules changed.

## Validation
Added `test_nifty_history_stale_cache_fallback.py` for:
1. sufficient stale cache + provider failure,
2. exact-date provider refresh,
3. insufficient cache + provider failure remains WAIT/fail-closed.

Run:
`python -m py_compile volume_gainer.py`
`python -m pytest -q test_nifty_history_stale_cache_fallback.py test_nse_trading_calendar.py test_v8_regression.py`

The GitHub Actions EOD workflow must pass before this fix is considered production-verified.
