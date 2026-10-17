# Independent 5-Day Delivery + Relative Valuation Watchlist

## Scope
- Add this file as a **new workflow only** at `.github/workflows/delivery_60_valuation_watchlist.yml`.
- It does not edit, import, or run the existing NSE Swing Trading V8.0 code/modules.
- It downloads NSE `sec_bhavdata_full` reports and selects stocks only when the daily `DELIV_PER` is **>= 60.00% on each of the five latest distinct valid trading-session reports**.
- If fewer than five valid sessions are available, it emits an empty CSV and reports `WAIT_FOR_DATA` in the Actions log.
- It outputs only `SYMBOL` and `VALUATION` in `delivery_60_valuation_watchlist.csv` and uploads it as a GitHub Actions artifact.

## Valuation meaning / limitation
- Valuation uses a simple **relative P/E vs the median positive peer P/E** from the public Screener.in company page.
- Current P/E <= 80% of peer median: `RELATIVELY_UNDERVALUED`.
- Current P/E > 80% and <= 120% of peer median: `FAIRLY_VALUED`.
- Current P/E > 120% of peer median: `RELATIVELY_OVERVALUED`.
- If the current P/E or at least three positive peer P/E observations cannot be retrieved, the output is `DATA_INSUFFICIENT`; the workflow does not guess.
- This is a relative valuation indicator, not a guaranteed intrinsic-value estimate. It does not use technical indicators, news, sectors, or trading-entry signals.

## Add it safely
1. Open `digitalmf78-pixel/AI-Trading-Bot` on GitHub.
2. Open `.github/workflows` and choose **Add file → Create new file**.
3. Name the new file `delivery_60_valuation_watchlist.yml`.
4. Paste the complete YAML file and commit it. Do not replace any existing file.
5. Open **Actions → Independent 5-Day Delivery 60% + Relative Valuation Watchlist → Run workflow** to test it.
6. Download the artifact named `delivery-60-valuation-watchlist-<run id>` and check `delivery_60_valuation_watchlist.csv`.

The workflow uses public NSE/Screener pages; availability, blocking, or missing data can cause `DATA_INSUFFICIENT`/`WAIT_FOR_DATA`. Local syntax checks are not proof that a live GitHub Actions run will succeed.
