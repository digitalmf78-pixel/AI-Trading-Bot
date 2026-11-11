# NSE V8 Fixed-Range Base & VCP — Implementation Audit

**Date:** 11-Nov-2026  
**Audited branch:** `main`  
**Main commit:** `e3c749b5eed3ae2a5b3315052c16f5d4f55f2e0d`  
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

## 3. New data-integrity finding requiring a safe follow-up

### Global official-session coverage is not independently proven by the shared history index

`history_index.build_price_history_index` currently builds its `market_dates` set from dates found in the supplied Bhavcopy frames and then adds the requested as-of date. It does not construct the expected date sequence from `nse_trading_calendar.py`.

Consequently, if an entire official NSE session is absent from all supplied/cached Bhavcopy frames, the global date list can omit that session. A symbol can then appear complete relative to the observed date list even though the official session is missing from the cache. The current per-symbol exact-date checks protect against a symbol-specific missing row only when the date exists in the global date list; they cannot independently detect a globally absent date.

This affects the interpretation of both the 60-date VCP window and rolling range windows. Until official-calendar parity is added, logs and reports should not overstate the observed date set as independently verified official-session coverage.

**Recommended safe code follow-up:** build the expected session sequence from the existing official NSE calendar for the requested as-of date and compare it with the available Bhavcopy date set before declaring any 20/50/100/200 or 60-session window complete. Missing calendar coverage or a missing expected Bhavcopy session must return `WAIT_FOR_DATA`; do not reach farther back to replace it. Preserve special sessions such as Muhurat Trading.

### Pivot observation integrity in Potential Accumulation

The rolling range branch validates finite positive OHLC structure. The separate pivot-completeness branch currently checks date coverage and non-null High/Low values, but does not apply the same full finite-positive and candle-structure validation before marking `PivotStructureStatus=COMPLETE`. The ATR helper has its own partial checks, but that does not make the pivot status itself a complete OHLC integrity assertion.

**Recommended safe code follow-up:** reuse one shared per-session OHLC validator for rolling ranges, pivot detection and ATR inputs. Invalid or non-finite values must make the affected observation `WAIT_FOR_DATA`, not a completed pivot observation. This is a data-integrity correction only; no pivot formula or signal threshold should change.

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

1. Add official-calendar expected-session parity to the shared history-window contract, with tests for holidays, Muhurat/special sessions, globally missing Bhavcopy dates, duplicate dates, future dates and insufficient calendar-year coverage.
2. Unify finite-positive OHLC and candle-structure validation across rolling range, pivot and ATR observations; preserve existing pivot selection logic.
3. Keep the current rolling range and three-block VCP measurements descriptive while the above data-integrity fixes are validated.
4. Implement fixed-range base boundary detection only after the start/end/duration/width definitions are explicitly approved.
5. Implement final VCP classification only after the contraction and volume thresholds are explicitly approved.
6. Validate Track 1 output parity and Track 2 full-Mainboard row coverage; no observer failure may alter Track 1 candidate membership.

## 6. Change-control statement

This audit made no source-code, workflow, scanner, Telegram, scoring, filter, ranking, entry, risk, or Master Specification changes. Existing VCP observations remain non-gating. The immutable original Master Specification remains unchanged.
