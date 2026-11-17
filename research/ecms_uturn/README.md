# ECMS U-Turn Research — P0 to P8

**Status:** isolated research only. This is not a standalone scanner, buy/sell system, or production ECMS feature.

U-Turn is an explanatory layer intended to run **only after a stock has already been selected by the NSE Volume Gainers scan**. It examines whether the selected stock may be undergoing a valuation reset, forming a possible base, recovering, or becoming stretched/overextended. The layer must not create its own stock universe or issue trade instructions.

## P0 — Scope and isolation
- Input universe: stocks already selected by the Volume Gainers scan.
- No independent scanning, orders, Telegram changes, or production workflow changes during research.
- All tests run on the isolated ECMS research branch and read the shared NSE V8 cache without modifying it.

## P1 — Fundamental data eligibility
- Use annual diluted EPS only.
- Compare consecutive audited financial years on the same reporting basis (standalone-to-standalone or consolidated-to-consolidated).
- Use official NSE filings, issuer annual reports and audited results; record period, units, ISIN and source URL.
- EPS zero, negative, missing, mismatched, non-consecutive, or unresolved corporate-action data => `WAIT_FOR_DATA`.
- Profit/loss state changes that make the ratio meaningless => `NOT_COMPARABLE_FOR_THIS_FORMULA`.
- Never silently substitute quarterly EPS, basic EPS or third-party EPS.

## P2 — Pre-result reference peak
- Peak = maximum daily High in the 20 completed NSE equity sessions strictly before the result announcement session.
- Verify the date list against the official NSE equity holiday calendar.
- Verify symbol, ISIN, series CM/STK/EQ and one valid OHLC row per session.
- Require both the strict cache audit and event-study parser to agree on all 20 sessions, peak date and peak High.

## P3 — Valuation-reset calculation
For a valid positive annual diluted EPS decline:

`Reference_PE = Pre_Result_Peak_High / Previous_FY_Diluted_EPS`

`Expected_Correction = (Previous_FY_Diluted_EPS - Current_FY_Diluted_EPS) × Reference_PE`

`U_Turn_Target = Pre_Result_Peak_High - Expected_Correction`

Equivalent: `Peak_High × Current_FY_EPS / Previous_FY_EPS`.

- If current EPS is equal to or greater than previous EPS: `NO_EPS_DECLINE`; no downside target.
- The target is a research reference level, not a forecast, entry or guarantee.

## P4 — Two-sided context
- Downside/reset side: assess whether the price is approaching or crossing the calculated valuation zone and whether a base/recovery is developing.
- Upside/stretch side: assess whether price, trend, momentum and volume show an extended or overbought state.
- Keep valuation and technical context separate. RSI, moving averages and volume do not validate EPS facts.
- Missing inputs remain visible; do not force a label.

## P5 — Price/volume zone check
- Zone = ±2% around the U-Turn target.
- Zone touch = daily range overlaps the zone (`Low <= ZoneHigh` and `High >= ZoneLow`).
- RVOL = current session volume / average volume of the prior 20 completed sessions (exclude current session).
- Delivery threshold = at least 60%; RVOL threshold = at least 1.5x.
- Both thresholds must be met on the **same zone-touch session**.
- Passing this gate yields `TECHNICAL_CONFIRMATION_ONLY`, not proof of accumulation or a profitable trade.

## P6 — Event-study validation
- Report 21-, 63- and 126-session outcomes separately.
- Keep price-only returns and gross cash-dividend-inclusive simple returns separately labelled.
- Reconcile stock actions (bonus, split, rights, demerger) before comparing price levels.
- No entry/exit, position sizing, stop-loss, fees, slippage or P&L simulation in V1.

## P7 — Evidence and sampling
- Predeclare universe snapshot, eligibility criteria, random seed and timestamp.
- Retain selected symbols, data failures, no-decline controls and negative outcomes; never replace a name after seeing EPS or price outcomes.
- Freeze thresholds before event outcomes are reviewed.
- Separate source-verification samples from event-study samples; a source audit does not become a random event-study automatically.
- Three-stock pilot is descriptive only and is not statistically representative.

## P8 — Output and integration gate
Allowed statuses include:
- `PROVISIONAL_TARGET`
- `NO_EPS_DECLINE`
- `WAIT_FOR_DATA`
- `NOT_COMPARABLE_FOR_THIS_FORMULA`
- `ZONE_TOUCH_NOT_CONFIRMED`
- `TECHNICAL_CONFIRMATION_ONLY`

No buy/sell, entry, exit, target-profit or “WIN” labels are allowed. Production integration requires a separate explicit approval after research acceptance and a successful Volume Gainers tape test.

## Current research artifacts
- [Hypothesis protocol](UTURN_HYPOTHESIS_PROTOCOL_V1.md)
- [Pilot event-study results](PILOT_EVENT_STUDY_V1_RESULTS.md)
- [EPS source audit](PILOT_SAMPLE_EPS_SOURCE_AUDIT.md)
- [Dividend / corporate-action review](PILOT_SAMPLE_DIVIDEND_CORPORATE_ACTION_REVIEW.md)
- [Official calendar and event-time audit](PILOT_OFFICIAL_CALENDAR_EVENT_TIME_AUDIT.md)
- [Cache reconciliation and fixed random sample](PILOT_CACHE_RECONCILIATION_AND_RANDOM_SAMPLE_V1.md)

The latest CI artifact is the acceptance evidence; documentation alone does not make a failed gate pass.
