# Delivery 60% + Relative Valuation Watchlist — corrected workflow

## What the latest Actions log showed

- The main NSE cache **was restored successfully** from `nse-bhavcopy-Linux-main-39009733627`.
- The diagnostic step found 54 files matching `data/bhavcopy/bhavcopy_YYYYMMDD.csv`, spanning 2026-07-31 to 2026-10-16, and 8 cached delivery reports. This run therefore does **not** prove that 220 trading-day Bhavcopy history is present in this cache.
- The workflow reused five existing delivery reports (2026-10-12 through 2026-10-16) and found 388 symbols with delivery >=60% on every one of those five sessions.
- Screener valuation calls failed with `Network is unreachable`; the script nevertheless attempted 388 per-symbol requests and took around 11 minutes 50 seconds overall.
- The separate valuation cache was empty at the beginning of this run.

## Changes in this version

1. Adds one short Screener connectivity preflight. If the runner cannot reach Screener, it skips hundreds of doomed requests and marks valuation as `DATA_INSUFFICIENT`; it does not guess cheap/expensive labels.
2. Network/HTTP failures are not cached, so a temporary outage cannot be stored as a 36-hour valuation result.
3. Legacy valuation-cache entries without `cacheable: true` are ignored and replaced, preventing previous outage results from being treated as real valuation data.
4. Reuses the existing `delivery_filter.py` and main NSE cache paths. It does not edit or run the main V8 scanner.

## Install

Use this YAML as the complete replacement for the **separate** workflow file:
`.github/workflows/delivery_60_valuation_watchlist.yml`

Do not replace or edit any other workflow or Python file.

## Output

Artifact CSV: `delivery_60_valuation_watchlist.csv`

Columns: `SYMBOL`, `VALUATION`

Possible valuation labels:
- `RELATIVELY_UNDERVALUED`
- `FAIRLY_VALUED`
- `RELATIVELY_OVERVALUED`
- `DATA_INSUFFICIENT`

The valuation labels are only relative P/E-vs-peer comparisons when the source page provides sufficient data. This is not a complete intrinsic-value estimate. A `DATA_INSUFFICIENT` value means no reliable label was available.
