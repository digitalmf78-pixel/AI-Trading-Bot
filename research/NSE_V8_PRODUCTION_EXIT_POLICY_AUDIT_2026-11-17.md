# NSE V8 Production Exit-Policy Audit — 2026-11-17

## Scope and safety

This is a read-only research audit of the current production `main` snapshot at `8b2dd01a5125cbe77a3246ec913262d8f36f9fc2`. It does not change scanner logic, the Master Specification, Bhavcopy/Delivery caches, workflows, or broker integrations. It is not an approval to merge the EMA44 research stack or to enable automated trading.

## Executive finding

**The current V8 scanner has EOD risk-plan and manual position-review outputs, but it does not yet define a complete executable exit policy.** An execution-level backtest cannot honestly treat the present position monitor as a deterministic trading system without first specifying how daily OHLC touches, gaps, partial exits, trailing stops, and time exits are handled.

The existing EMA44 Type A signal-level backtest is therefore not an execution backtest and must remain separate from any future exit-policy simulation.

## What production currently does

### 1. Entry candidate / final EOD gates

In `v8_layers_14_41.py::run_eod_layers()`, a row can reach `EODWatchlistStatus=WATCH` only after the required-data checks and all of these conditions:

- Portfolio risk control = PASS.
- Mandatory 3+1 confirmation = PASS.
- Market regime is not RISK_OFF.
- Sector strength = PASS.
- Structural RiskRewardStatus = PASS (at least 2R).
- ChaseStatus = CLEAR.
- SetupType is Breakout or Pullback.
- Delivery filter = PASS_GE_60_PERCENT and DeliveryStatus = PASS.
- Accumulation/distribution is not Distribution.
- For RVOL >= 1.5, VolumeReason must be Demand-led.
- V8Score >= 70.

After this, the portfolio allocator enforces configured open-position capacity, total exposure, sector exposure, and duplicate-symbol checks. The final shortlist is capped at four rows. This is an EOD candidate/watchlist process, not an order-placement process.

### 2. Stop and target planning

- Planned stop is the lower of valid structural support and `Close - 1.5 * ATR14` (when both are valid).
- Planned entry is based on `EntryZoneHigh`.
- Structural target is the nearest verified overhead resistance candidate above entry.
- Risk/reward is calculated as `(resistance - entry) / (entry - stop)`; PASS requires >= 2.0.
- If no verified overhead resistance exists above entry, status remains WAIT_FOR_DATA. No synthetic 2R target is created.

**Code consistency issue to resolve:** the RR calculation temporarily falls back to current Close when EntryZoneHigh is missing, but the output `EntryPricePlan` is still assigned from EntryZoneHigh. The risk-control module then reads EntryPricePlan (and only uses EntryZoneHigh as a fallback when the column itself is absent, not when its value is NaN). This can make the RR calculation use one entry while risk controls see a missing entry. Do not patch until the intended entry fallback is explicitly decided.

### 3. Portfolio risk configuration

`risk_controls.py` fails closed when required account/portfolio inputs are missing or invalid. Required settings include account equity, risk-per-trade percentage, single-position cap, sector and total exposure caps, max stop distance, current exposure, sector exposure map, verified portfolio exposure, max open positions, and current open positions.

The code calculates quantity from the risk budget and single-position cap and checks stop distance, sector exposure, total exposure, and position counts. Missing configuration does not mean a zero-sized or default account; it produces WAIT_FOR_DATA.

### 4. Position monitor behavior

`monitor_positions()` reads a user-maintained `data/inputs/positions.csv` and emits a report with `DecisionMode=MANUAL_REVIEW_ONLY`. Its own docstring says no orders are sent.

Current decision rules:
- Initial stop: EXIT when latest daily **Close <= InitialStop**.
- Adverse primary-source news: CAUTION.
- Target reached by daily **Close >= Target**, or selling pressure: REDUCE.
- Missing critical position fields/news: CAUTION.
- Weakening thesis or target within 2%: CAUTION.
- 20+ market sessions: CAUTION / review due.
- Otherwise HOLD.

The computed trailing stop is `max(initial stop, recent swing low, current price - 2*ATR14)`, but it is only written to the report; it is not used to trigger an exit.

### 5. Important limitations

1. **Intraday stop touch is ignored:** the monitor uses Close <= InitialStop, not daily Low <= InitialStop. A stop can be crossed intraday and the close recover without an EXIT action.
2. **Intraday target touch is ignored:** the monitor uses Close >= Target, not daily High >= Target. A target can be reached intraday and the close retreat without a REDUCE action.
3. **Trailing stop is informational only:** it is calculated but never tested as an exit trigger.
4. **No gap-fill execution model:** there is no defined execution price when the market opens beyond a stop or target.
5. **No same-session collision rule:** there is no policy for a day whose High touches target and Low touches stop when daily bars cannot reveal which happened first.
6. **No partial-exit sizing rule:** REDUCE is a manual review label; the quantity or percentage to sell is not specified.
7. **No automatic time exit:** 20+ sessions triggers CAUTION/review, not a mandatory close. Ten-session status is descriptive.
8. **No broker order placement:** the position monitor explicitly declares manual review only; code search found no production order-placement integration in the relevant V8 path.
9. **No intraday stop/target history in this monitor:** it reads the current EOD result and daily historical sessions, not a deterministic tick/1-minute path for stop/target execution.
10. **Potential risk-plan entry mismatch:** see section 2.

## Backtest boundary

The previous EMA44 Type A historical test measured signal-level forward outcomes at 5D/10D/20D with costs. It did not simulate production stop/target execution, partial exits, portfolio concurrency, position sizing, or drawdown. Its EQ-series proxy and lack of point-in-time fundamentals also leave universe/survivorship limitations. Its negative net results mean the EMA44 PR stack is not approved for production merge.

Do not label that result an execution backtest.

## Decisions required before an execution-level backtest

The following are **proposals requiring explicit user approval**, not current production rules:

| Decision | Conservative research proposal | Needs approval |
|---|---|---|
| Entry | Next official NSE session Open after an eligible signal | Yes |
| Initial stop | Use the production StopLossPlan captured as-of signal date; never recompute with future data | Confirm |
| Stop trigger | Daily Low <= stop; if Open < stop, model fill at Open, otherwise at stop | Yes |
| Target trigger | Daily High >= structural target | Yes |
| Same-day stop and target both touched | Stop-first (conservative ambiguity resolution) | Yes |
| Target action | Full exit, or specify a fixed partial quantity/percentage | Yes |
| Trailing stop | Disabled in baseline until activation and update rules are defined | Yes |
| Time exit | Treat 5D/10D/20D as measurement horizons only; no automatic time exit unless specified | Yes |
| Costs | Retain previously tested cost/slippage assumptions only if user reconfirms they are appropriate | Confirm |
| Portfolio simulation | Keep signal-level first; add concurrency/sizing/drawdown only after account assumptions are explicitly supplied | Yes |

Any future implementation must validate OHLC consistency (Low <= Open/Close <= High), official NSE session sequence, no future leakage, duplicate/missing bars, and stop/target collision handling. Data validation must not be weakened for speed.

## Acceptance criteria for a future strategy change

Before any production merge, require:
- A pre-registered exit policy and frozen parameters.
- Out-of-sample / walk-forward evaluation, not only in-sample aggregate results.
- Net results after realistic brokerage, taxes/fees, and slippage.
- Profit factor > 1 and positive expectancy across adequately sized, independent trade samples.
- Drawdown, loss streak, exposure, and overlapping-signal analysis.
- Stability across different months and market regimes.
- Point-in-time universe handling or a clearly quantified survivorship limitation.
- Tests for every exit edge case (gap-through stop, gap-through target, both levels touched, missing/invalid OHLC, partial exit, trailing stop update, and time exit).

**No production files were modified. No PRs #143–#145 were merged.**
