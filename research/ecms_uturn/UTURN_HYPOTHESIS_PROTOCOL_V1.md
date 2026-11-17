# ECMS U-Turn — Independent Research Protocol v1

**Status:** isolated research only. No production integration, order generation, or Volume Gainers dependency.

## Objective
Test whether a fall in annual diluted EPS can estimate a valuation-reset zone, and whether price/volume/delivery behaviour after the result shows a subsequent base/recovery. This is a falsifiable research hypothesis, not a buy/sell rule.

## Locked event-study definitions
1. Event date is the official exchange/company result-announcement date and time (IST). If announced during market hours, the event session is not used as a post-event session; the first eligible outcome session is the next NSE trading session. If announced after market close, same rule applies.
2. Pre-result peak is the maximum raw daily High from the **20 completed NSE sessions strictly before** the event session. The 20 session dates must be independently verified against the exchange calendar and bhavcopy; no calendar-day approximation.
3. EPS inputs are annual **diluted EPS**, previous FY and current FY, same issuer, same consolidated/standalone basis, same currency/unit and comparable continuing-operations basis. No quarterly EPS, basic EPS fallback, or silent basis switching. Missing, non-positive, mismatched, restated or non-comparable values => WAIT_FOR_DATA / NOT_COMPARABLE.
4. EPS decline only: current EPS must be lower than previous EPS. Otherwise status NO_EPS_DECLINE and no downside target.
5. Reference PE = pre-result peak High / previous FY annual diluted EPS.
6. Expected correction = (previous FY diluted EPS - current FY diluted EPS) × reference PE.
7. Target = peak High - expected correction = peak High × current FY diluted EPS / previous FY diluted EPS.
8. Research zone = target ±2%. The zone is an observation band, not an order.
9. A session touches the zone only when its daily range overlaps the zone: Low <= zone upper AND High >= zone lower.
10. Delivery confirmation requires delivery percentage >=60% on the same session as the zone touch. RVOL = session volume / mean volume of the previous 20 completed sessions, excluding current session; RVOL >=1.5. Both must be present on the same session. Missing delivery or insufficient volume history => WAIT_FOR_DATA for confirmation, not a pass.
11. A zone touch plus delivery/RVOL is labelled TECHNICAL_CONFIRMATION_ONLY. It is not proof of institutional accumulation, a bottom, or a profitable trade. Subsequent 21/63/126-session outcomes are reported separately.
12. No entry/exit/P&L simulation in v1. Do not call any observation a WIN. Corporate actions (bonus, split, rights, demerger), ISIN changes and price-series adjustments must be reconciled before a result can be promoted from PROVISIONAL to VERIFIED.

## Required audit trail
- Official result filing URL, announcement timestamp and first post-result session.
- Official annual report/results URLs and exact EPS table references, units and reporting basis.
- Exchange calendar/session list and 20 pre-event session dates.
- Raw NSE bhavcopy source file, symbol, series EQ, ISIN, OHLCV and file hash.
- Same-day delivery quantity, traded quantity and delivery percentage source.
- RVOL formula, 20 prior sessions and raw volume values.
- Corporate-action review and any adjustment factor.
- All rejected/WAIT_FOR_DATA reasons; never silently drop a stock.

## Sampling and bias controls
- Select 3–5 eligible Main Board stocks by a predeclared random seed from the defined universe, not by whether the chart subsequently recovered.
- Preserve all selected names, including data failures and negative outcomes.
- Record universe snapshot, random seed, selection timestamp and exclusions.
- No tuning the ±2%, 60% delivery or 1.5x RVOL thresholds after looking at outcomes. Any alternate thresholds must be a separately labelled experiment.
- Keep an EPS-no-decline control group where possible.

## Current implementation boundary
- Existing isolated ECMS research branch only.
- Shared NSE V8 cache is read-only.
- No changes to production workflows, scanner selection, Telegram, order logic or live trading.
- Research outputs must state cache coverage and incomplete horizons.
