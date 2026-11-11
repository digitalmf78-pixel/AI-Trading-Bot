# NSE V8 Fixed-Range Base & VCP — Implementation Audit

**Date:** 11-Nov-2026  
**Audited branch:** `main`  
**Main commit verified after PR #62:** `a1018f5c9ec0f8bb49b5f16cbe1c34cff01cd858`  
**Scope:** Read-only code and test audit of Fixed-Range Base and VCP observations, including Track 2 wiring. No trading rules or production code changed in this audit.

## 1. Executive result

- **Fixed-Range Base:** Not implemented as a detected base with algorithmic start/end boundaries. The current code emits rolling 20/50/100/200-session price-range observations. Those rolling-window endpoints are mechanical lookback boundaries, not detected consolidation boundaries.
- **VCP:** The descriptive three-block observer is implemented and tested. It measures three consecutive 20-session blocks (60 dates in its current input calendar), price-range widths and contraction depth, block-average volume and ratios, and a price/volume contraction relationship. It intentionally does not classify a final VCP.
- **Interim Base/VCP watchlist:** `BASE_FORMING` is an observation label only when two successive range contractions are observed. Its reason explicitly says `NOT_VCP_CONFIRMED`. It is not a fixed-range base determination, BUY signal, or scanner gate.
- **Track 2:** The full-Mainboard observer is now wired into the EOD scanner on `main` by merged PR #45. An older paragraph in the working parameter register saying Track 2 had no scanner/workflow integration is stale and is superseded by the correction recorded in Section 35 of that register.

## 2. Verified current implementation

### 2.1 Rolling range observations — `potential_accumulation_analysis.py`

For each candidate, the observer currently emits 20/50/100/200-session rolling values:
- window high, low and width percentage;
- sessions since latest exact high/low and exact-equality high/low touch counts;
- window start/end dates and session count;
- average daily intraday range percentage;
- latest close position within the rolling high-low range.

The range window checks require exact membership against the date list supplied by `history_index.py`, unique symbol/date rows, finite positive High/Low/Close, and structurally valid candles. These fields remain raw rolling observations. They do not locate a fixed base start, fixed base end, or base duration.

### 2.2 VCP observations — `vcp_observation_analysis.py`

The current observer:
- splits the last 60 dates supplied by the shared history index into three consecutive 20-date blocks;
- measures each block's high/low range width;
- calculates sequential range ratios and contraction depth;
- counts whether each later block is narrower than the prior block;
- measures block-average volume and sequential volume ratios;
- emits the price/volume contraction relationship;
- emits a descriptive latest/prior block volume dry-up marker when the ratio is below 0.5x.

The 0.5x marker is observational only. It is not a filter, score, confirmation, or entry condition. Complete observations retain `VCPStatus=NOT_CLASSIFIED`; incomplete inputs retain `WAIT_FOR_DATA`.

### 2.3 Watchlist semantics — `hybrid_watchlists.py`

- `BASE_FORMING` is emitted when VCP input status is COMPLETE and exactly two contraction transitions are observed.
- The reason is `TWO_SUCCESSIVE_20D_RANGE_CONTRACTIONS_OBSERVED; NOT_VCP_CONFIRMED`.
- Complete data without two transitions receives `NO_SETUP`; incomplete data receives `WAIT_FOR_DATA`.
- This interim label must not be described as a fixed-range base, VCP_CONFIRMED, or a BUY/ENTRY signal.

### 2.4 Track 2 wiring

PR #45 (`3c72add025ccad3f5aaa41506e0bbb9e70abbd39`) snapshots the official Mainboard frame before Delivery A/B and calls `build_track2_full_mainboard_report` after the shared Delivery fetch. Track 2 writes to its isolated `outputs/track2_full_mainboard/` namespace and its errors do not gate or mutate Track 1. The register's earlier statement that no scanner/workflow integration existed is historical and no longer current.

## 3. Data-integrity follow-up — resolved by PR #62

The two data-integrity findings recorded in the original audit were implemented and merged to `main` by PR #62 (`a1018f5c9ec0f8bb49b5f16cbe1c34cff01cd858`).

### Official NSE session parity — implemented

`history_index.build_price_history_index` now builds the expected session sequence from the official NSE Capital Market calendar, from the earliest observed Bhavcopy date through the as-of date. This preserves official special sessions (including Muhurat Trading) and makes a missing official session within that observed coverage interval visible to completeness checks. Unknown/missing calendar-year coverage fails closed and produces an empty expected-session set, which keeps downstream windows in `WAIT_FOR_DATA`.

**Known boundary:** the sequence begins at the earliest date present in the supplied Bhavcopy frames. It cannot independently prove that the cache contains every official session before that earliest observed date. A future cache-coverage metadata contract would be needed to verify the entire requested lookback from a declared coverage start; do not silently infer or backfill that coverage.

### Pivot OHLC integrity — implemented

`potential_accumulation_analysis.py` now validates finite, positive Open/High/Low/Close values and candle structure before marking Pivot Structure complete. Invalid Open values and candles whose Open/Close lie outside Low/High return `WAIT_FOR_DATA`. The pivot selection formula is unchanged. Existing Rolling Range validation behavior is preserved; no new scanner filter or trading threshold was added.

### Validation evidence

- PR #62 changed the official-session index and pivot OHLC completeness checks, plus focused calendar and OHLC regression fixtures.
- NSE V8 PR Checks run #439: compilation, unit/data-audit tests, V8 regression, and sector/news/official-index tests all **PASS**.
- News Matching and Parser Tests run #714: **PASS**.
- PR #62 was squash-merged to `main` as `a1018f5`.

## 4. Definitions that remain unapproved — do not guess

### Fixed-Range Base
The current code does not define:
- the event/condition that starts a base;
- the event/condition that ends a base;
- minimum or maximum base duration;
- acceptable base width or volatility;
- whether width is measured from full high-low, closes, or another approved measure;
- support/resistance zone tolerance and minimum separated tests;
- how a breakout invalidates or completes a base.

### VCP final classification
The current code does not define approved thresholds for:
- minimum/maximum contraction transitions;
- minimum contraction depth or allowed range expansion;
- required number of contractions;
- volume contraction/dry-up acceptance;
- final `VCP_FORMING`, `VCP_CONFIRMED`, or `NO_VCP` classification;
- false-VCP forward horizon, breakout event, failure buffer, re-entry rule, and outcome window.

No numerical value or final classification should be added until the user approves the exact definitions. The existing three-block metrics and interim `BASE_FORMING` observation must remain non-gating.

## 5. Safe implementation sequence

1. Treat PR #62 official-session parity and pivot OHLC validation as implemented; retain the documented earliest-observed-date coverage boundary and do not claim cache completeness before it.
2. Keep current rolling-range and three-block VCP measurements descriptive and non-gating.
3. Implement fixed-range base boundary detection only after the start/end/duration/width definitions are explicitly approved.
4. Implement final VCP classification only after the contraction and volume thresholds are explicitly approved.
5. Continue validating Track 1 output parity and Track 2 full-Mainboard row coverage; no observer failure may alter Track 1 candidate membership.

## 6. Change-control statement

This audit made no source-code, workflow, scanner, Telegram, scoring, filter, ranking, entry, risk, or Master Specification changes. Existing VCP observations remain non-gating. The immutable original Master Specification remains unchanged.
