# Technical Momentum, Breakout & VCP Backtest — Research Only

**Date:** 14-Nov-2026  
**Branch:** `research/technical-momentum-backtest-2026-11-14`  
**Scope:** Point-in-time EOD feature study on cached NSE EQ Bhavcopy. No production scanner, ranking, eligibility, Telegram, or order-flow changes.

## Purpose

Test whether combinations of EMA trend, prior-high breakouts, RVOL, three-block range contraction, and volume dry-up are associated with better forward outcomes. The study reports 5/10/20-session close returns plus MFE/MAE and the frequency of favorable excursions reaching 3%, 5%, 10%, and 15%.

## Features

- EMA20, EMA44, EMA50, EMA200: exponential moving averages calculated causally from the symbol's available closes. EMA200 is only mature after 200 valid sessions.
- EMA stack: close > EMA20 > EMA44 > EMA50; a separate stricter observation adds EMA50 > EMA200.
- 20/50/100-session breakout: signal-day close exceeds the maximum High of the preceding 20/50/100 sessions. The signal-day High is excluded from the reference.
- RVOL20: signal-day volume divided by the mean volume of the preceding 20 sessions.
- VCP-style observer: three consecutive 20-session High-Low range widths; the latest block includes the signal EOD. Two contractions means block 2 is narrower than block 1 and block 3 narrower than block 2.
- Volume dry-up: mean volume in the latest 20-session block divided by mean volume in the immediately preceding 20-session block is below 0.5.

These are measurable feature definitions for comparison, not approved final VCP, fixed-base, breakout-confirmation, or entry rules.

## Entry and outcomes

- Signal is known only after EOD.
- Reference entry is the Open of the next official NSE equity session.
- Forward 5/10/20-session close returns are measured from that next-session Open to the close of the Nth next session.
- MFE/MAE use High/Low across the same forward horizon.
- The comparison includes all signal rows and a de-overlapped view retaining at most one observation per symbol/setup in each 21-session interval.

MFE reaching 3/5/10/15% is a favorable excursion, not a booked or guaranteed return. Costs, slippage, taxes, liquidity impact, and four-position portfolio constraints are not simulated.

## Data and limitations

- Uses only local cached Bhavcopy; the technical script itself makes no network calls.
- EQ-series history is not a point-in-time official Main Board universe; current cache membership creates survivorship bias.
- Historical point-in-time fundamentals, historical news, and sector-relative-strength series are not joined in this phase.
- Missing symbol/session candles are not forward-filled; affected features or outcomes remain unavailable.
- A 200-session price cache can support mature 200 EMA observations only near the end of the sample, leaving little or no forward 5/10/20-session outcome coverage for that strict setup. A longer price history is needed before drawing conclusions about EMA200 alignment.
- The workflow must publish the cache coverage and comparison artifacts. A small or incomplete sample must be reported as insufficient evidence, not as a win-rate estimate.

## Change control

This is an isolated research branch. No production thresholds, Delivery A/B rules, scanner membership, scoring, watchlists, Telegram messages, or execution behavior are changed. Do not promote any setup without adequate sample size, out-of-sample validation, costs/slippage, and a portfolio-level simulation.
