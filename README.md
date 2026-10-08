# AI Trading Bot — NSE Swing Trading V8

This repository calculates an end-of-day research watchlist and optional next-day / open-position reviews. It **does not place orders**. Scores never override the V8 confirmation gate, and unavailable inputs produce `WAIT_FOR_DATA` rather than a trade signal.

## Layers

- Layers 1–13: NSE Bhavcopy, volume/price studies, indicators, support/resistance, and relative strength vs Nifty.
- Layers 14–24: sector and market context, delivery/volume inference, accumulation/distribution, verified news gate, score, risk/reward, chase filter, and EOD watchlist.
- Layers 25–34: next-session gap and opening checks, intraday VWAP/RVOL/RSI, index confirmation, breakout confirmation, and entry review.
- Layers 35–41: supplied-position review, thesis/news/selling-pressure checks, target/trailing-stop management, and HOLD/CAUTION/REDUCE/EXIT review labels.

The later layers are implemented in `v8_layers_14_41.py`. Inputs are optional CSVs under `data/inputs/`; the program creates header-only templates when they are absent. It writes reports to `outputs/`.

## Input files

### `data/inputs/sector_map.csv`

Columns: `TckrSymb,Sector,SectorIndexSymbol`. One row per stock. `SectorIndexSymbol` must match the index symbol used in `intraday_bars.csv`.

### `data/inputs/sector_history.csv`

Columns: `Date,Sector,Close`. Provide at least 21 trading closes per sector, including the EOD date, for the 20-session sector return.

### `data/inputs/news_evidence.csv`

Columns: `TckrSymb,PublishedAt,Headline,Source,SourceType,URL,Impact,EventID` (optional `SourceDomain` for RSS publishers). Use ISO-8601 timestamps with timezone. Set `SourceType` to `primary`/`official` for an issuer, exchange, or regulator source; other publishers are secondary sources. `Impact` accepts `positive`, `negative`, or `neutral`. Use the same `EventID` for copies of the same event. Similar headlines are also grouped so copies across sites do not count as separate confirmations.

The 3+1 gate requires one event with at least three distinct secondary source domains and one distinct primary source domain. This is intentionally strict; unverified or missing news cannot pass.

The daily RVOL Top 20 is also checked against NSE's public company-announcement and integrated-financial RSS feeds. Google News RSS is used only to discover secondary coverage. Automatic matches are written to `data/inputs/news_evidence_auto.csv`; the review report is `outputs/v8_catalyst_top20.csv`. A single NSE filing is marked as a verified event, while the separate 3+1 confirmation gate remains in force for a full V8 watchlist result. The Marathi impact label is a headline-based first pass; the linked filing is the source of truth, and timing alone does not prove that an announcement caused a price move.

### `data/inputs/intraday_bars.csv`

Columns: `Symbol,Datetime,Open,High,Low,Close,Volume`. Include the candidate stocks, Nifty bars identified as `NIFTY50` (or `NIFTY`/`^NSEI`), and sector index symbols. For opening RVOL, include at least five previous sessions of bars for the same symbol at the corresponding time of day, plus the next-session bars. Bars should be 5-minute or finer and timestamps should include a timezone.

### `data/inputs/positions.csv`

Columns: `TckrSymb,Quantity,AverageEntryPrice,InitialStop,Target,EntryDate,Thesis`. One row per open position. Do not put real holdings or account details in a public GitHub repository; use a private local checkout or a private storage mechanism.

## Reports

- `outputs/v8_eod_watchlist.csv`: per-symbol factor values, score, data coverage, and `WATCH`, `SKIP`, or `WAIT_FOR_DATA` status.
- `outputs/v8_next_day_entry.csv`: opening validation results; `ENTRY_ELIGIBLE_REVIEW` still requires a person's review.
- `outputs/v8_position_monitor.csv`: HOLD/CAUTION/REDUCE/EXIT review labels; no broker action is sent.
- `outputs/v8_layer_status_summary.csv`: layer-by-layer input availability for Layers 14–41.

## Current configurable rules

The checkpoint specified the 3+1 rule and preferred R:R of at least 1:2 but did not specify detailed formulas or weights for every later layer. The current implementation uses conservative defaults in `v8_layers_14_41.py`: sector/Nifty relative thresholds of ±2%, EMA20/EMA50 market regime, delivery classifications at 25%/40%, a minimum V8 score of 70 with full score-input coverage, and a weighted score (trend 15, RS 15, sector 10, market 10, RVOL 10, volume 10, CLV 10, setup 10, delivery 5, accumulation 5). WATCH also requires the 3+1 news gate, no risk-off regime, a non-weak sector, no distribution classification, and at least 1:2 R:R. The chase filter flags a close more than 3% above the planned entry, over 2 ATR above EMA20, or up more than 8% on the day. Sector mapping/history still must be supplied. Review these assumptions before relying on the report. A volume label is only a price/volume inference, not proof of a real-world catalyst.

## GitHub Actions

Run **Actions → NSE Data Test → Run workflow**. Telegram is off by default; turn on `send_telegram` only when a message is wanted. GitHub Actions caches downloaded Bhavcopies and confirmed NSE 404 dates for reuse on later runs. The job uploads report CSVs and input templates as an artifact. The workflow is manual and does not automatically run after a commit.
