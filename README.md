# NSE Swing Trading System V8

This repository generates an end-of-day (EOD) research shortlist and optional next-session/open-position reviews. It does **not** place orders. A score never overrides a mandatory gate, and missing or unverified evidence must remain `WAIT_FOR_DATA`.

## V8 flow

1. Download NSE EOD Bhavcopy and rank the RVOL Top 20 using the previous 20 full sessions as the RVOL baseline (the current session is excluded from that baseline).
2. Apply the five-valid-session Average Delivery filter: **average Delivery % >= 60.00% passes; below 60% rejects; fewer than five valid distinct sessions means `WAIT_FOR_DATA`.**
3. Apply price/volume, trend, breakout/pullback, support/resistance, relative-strength and market-context checks.
4. Require the 3+1 confirmation gate: at least **three independent evidence categories** plus a **separately verified primary/reliable source**. Categories may include price/volume, sector strength, accumulation/distribution and a real catalyst/news event. Multiple publishers repeating the same event remain one catalyst category.
5. Produce an EOD `WATCH` only when all required gates, score coverage, risk/reward and chase checks pass.
6. Run next-session opening checks only for final EOD `WATCH` candidates. Missing intraday data stays `WAIT_FOR_DATA`; no rejected or incomplete EOD candidate should enter this stage.

## Primary-source handling

`SourceType=primary` by itself is not enough. Official/exchange/regulator records must use a recognized official domain (for example, NSE/BSE or a regulator domain). A manually reviewed issuer website may use `SourceType=company_verified` or `issuer_verified` when `SourceDomain` matches the URL host. A source that cannot be verified remains unverified. An NSE RSS item is attributed to the official NSE feed as the publisher; its item URL is the linked filing.

## Input CSVs

- `data/inputs/sector_map.csv`: `TckrSymb,Sector,SectorIndexSymbol`
- `data/inputs/sector_history.csv`: `Date,Sector,Close`; at least 21 distinct EOD closes including the target EOD date are needed for a 20-session return.
- `data/inputs/news_evidence.csv`: `TckrSymb,PublishedAt,Headline,Source,SourceType,URL,Impact,EventID,SourceDomain`
- `data/inputs/intraday_bars.csv`: `Symbol,Datetime,Open,High,Low,Close,Volume`; use 5-minute or finer bars and include stocks, Nifty, and verified sector index symbols.
- `data/inputs/positions.csv`: `TckrSymb,Quantity,AverageEntryPrice,InitialStop,Target,EntryDate,Thesis`

Missing sector membership or exact-date sector history is not guessed: it remains `WAIT_FOR_DATA`. An ETF is not assigned to an unrelated sector index simply because its name sounds similar.

## Reports

- `outputs/v8_rvol_top20_delivery_audit.csv`: RVOL Top 20 with five-session delivery audit.
- `outputs/v8_eod_watchlist.csv`: per-symbol EOD gates, score, coverage and status.
- `outputs/v8_catalyst_top20.csv`: catalyst/source audit; OHLCV patterns are not proof of a real-world cause.
- `outputs/v8_next_day_entry.csv`: opening validation. `ENTRY_ELIGIBLE_REVIEW` still requires human review.
- `outputs/v8_position_monitor.csv`: supplied-position review labels only; no broker action is sent.
- `outputs/v8_layer_status_summary.csv`: layer-by-layer data availability for Layers 14–41.

## Tests and GitHub Actions

Run local regression tests with:

```bash
python -m py_compile delivery_filter.py news_catalyst.py v8_layers_14_41.py test_v8_regression.py
python test_v8_regression.py
```

The additive workflow in `.github/workflows/v8-regression.yml` runs these checks on push, pull requests and manual dispatch. The normal `NSE Data Test` workflow remains the end-to-end scan and uploads its reports as an artifact.

The exact formulas/weights not defined by the master specification are conservative implementation defaults. Do not treat generated watchlists as financial advice or automatic orders. Verify the primary filing, liquidity, risk and current market context before any human decision.
