# ECMS Fundamental U-Turn Module — Research Design

**Design date:** 2026-11-17  
**Status:** Research implementation v1 added on the isolated research branch; dedicated CI passed 23 unit tests on 17-Nov-2026 (confirmed in Runs #13 and #14). Issuer-level OHLC/corporate-action reconciliation remains pending; not production-approved.  
**Scope:** ECMS only, on branch `research/bharat-sm-data-fundamental-audit-2026-11-17`.  
**User-confirmed inputs:** annual EPS comparison; peak price means the price peak before the result announcement.  
**No backtesting, basketting, trading order or buy/sell signal is included.**

## 1. Purpose

Estimate the valuation impact of a decline in annual EPS using the valuation multiple observed at the pre-result price peak. Identify whether the post-result market price is near that estimated reset level. This is an explanatory research observation, not a prediction, guaranteed support level, reversal confirmation or entry signal.

## 2. Approved interpretation and configurable assumptions

| Item | Research definition |
|---|---|
| Previous EPS | Audited EPS for the immediately preceding completed financial year |
| Current EPS | Audited EPS for the latest completed financial year, after its result is officially published |
| EPS basis | Diluted EPS only for both years. If diluted EPS is missing for either year, mark `WAIT_FOR_DATA`; no Basic EPS fallback. |
| EPS units | INR per share, same share class and comparable corporate-action basis |
| Peak event date | Official NSE/BSE result announcement publication date/time for the latest completed FY |
| Pre-result price window | User-confirmed: 20 completed NSE trading sessions ending strictly before the announcement calendar date. |
| Peak price | Maximum daily High in that pre-result window, sourced from validated exchange OHLC data |
| Tolerance | Initial default ±3%, retained from the user's supplied code; configurable for research, not a trading threshold |
| Price comparison | Latest valid post-announcement completed-session Close, with session date and source retained |

**Look-ahead protection:** Exclude the entire announcement calendar date from the peak window, even if the filing was published after market close. This conservative rule prevents accidental use of an intraday high from a session that overlaps the result event.

## 3. Calculation

Only calculate an EPS-decline valuation reset when both annual EPS values are positive and comparable, and Current EPS is strictly below Previous EPS.

```text
EPS_Drop = Previous_FY_EPS - Current_FY_EPS
Reference_PE = Pre_Result_Peak_High / Previous_FY_EPS
Expected_Correction = EPS_Drop * Reference_PE
U_Turn_Target = Pre_Result_Peak_High - Expected_Correction
```

Equivalent cross-check:

```text
U_Turn_Target = Pre_Result_Peak_High * Current_FY_EPS / Previous_FY_EPS
```

The two target calculations must agree within a small floating-point tolerance. A mismatch is an implementation error and must fail the row closed.

Proximity zone:

```text
Lower_Bound = U_Turn_Target * (1 - tolerance)
Upper_Bound = U_Turn_Target * (1 + tolerance)
Near_U_Turn_Zone = Lower_Bound <= Latest_Post_Result_Close <= Upper_Bound
```

The zone is a price proximity observation only. It must not be named confirmed support. A separate recovery/reversal signal is outside this module's scope.

### EPS cases

- Both EPS values positive and current EPS lower: eligible for the estimate.
- Current EPS equal to or above previous EPS: `NO_EPS_DECLINE`; do not produce an EPS-drop correction.
- Previous EPS zero/negative, current EPS zero/negative, missing EPS, incomparable basis, unverified annual period or unresolved corporate action: `WAIT_FOR_DATA` / `UNVERIFIED`; do not calculate.
- Loss-to-profit and profit-to-loss transitions: `NOT_COMPARABLE_FOR_THIS_FORMULA`; no division or target extrapolation.
- If result date or pre-result OHLC window is unavailable: `WAIT_FOR_DATA`.

## 4. Required input contract

One row per NSE symbol and result event. Never merge observations solely on company display name.

| Field | Meaning / validation |
|---|---|
| `Symbol` | Exact NSE Main Board symbol |
| `CompanyName` | Issuer name from exchange master / official filing |
| `Previous_FY`, `Current_FY` | Explicit financial-year identifiers; consecutive completed FYs |
| `Previous_EPS`, `Current_EPS` | INR/share, audited annual EPS |
| `Previous_EPS_Basis`, `Current_EPS_Basis` | Both must be `DILUTED`; no fallback |
| `Previous_Reporting_Basis`, `Current_Reporting_Basis` | Both must be identical: `CONSOLIDATED` or `STANDALONE` |
| `Previous_EPS_Unit`, `Current_EPS_Unit` | Both must be `INR/SHARE` |
| `Previous_EPS_Source_URL`, `Current_EPS_Source_URL` | Exact official filing/XBRL URLs, HTTPS |
| `Result_Announcement_Source_URL` | Exact official NSE/BSE announcement URL |
| `Peak_Price_Source_URL`, `Latest_Post_Result_Source_URL` | Exact exchange OHLC provenance URLs, HTTPS |
| `EPS_Source_URL` | Exact official filing / XBRL source for each FY |
| `EPS_Publication_Date` | Publication date for each annual result |
| `Result_Announcement_DateTime` | Official exchange announcement timestamp |
| `Peak_Window_Start`, `Peak_Window_End` | Actual NSE sessions used |
| `Peak_Price` | Maximum daily High in window |
| `Peak_Price_Date` | Session date where peak High occurred |
| `Peak_Price_Source` | Exchange OHLC/bhavcopy provenance |
| `Latest_Post_Result_Close` | Latest completed session close after result date |
| `Latest_Post_Result_Session` | Date of that close |
| `TolerancePct` | Configured proximity tolerance (initially 3%) |

The module requires separate previous/current diluted-EPS basis, reporting-basis and unit fields, plus official source URLs for each EPS year, the result announcement, pre-result peak OHLC and latest post-result OHLC. The caller's input/output row must retain source retrieval timestamps, filing period ends, raw source labels and corporate-action adjustment evidence alongside these URLs. EPS comparisons must use the same reporting basis. If official consolidated EPS is unavailable for either year, do not pair it with standalone EPS.

## 5. Result event and price peak selection

1. Discover result announcement only from issuer-matched official NSE/BSE corporate filing / financial results records.
2. Record exchange publication timestamp and the actual financial year covered. Do not substitute a future announced result date, news headline date or financial period end for publication date.
3. For the proposed 20-session window, obtain the 20 completed NSE trading sessions strictly before the announcement calendar date, using the official trading calendar.
4. Require complete, valid OHLC rows for the selected sessions. Use daily High, not Close, for `Peak_Price`.
5. If the history has fewer than the configured required sessions, a missing High, duplicate session, stale date or unresolved split/bonus adjustment, return `WAIT_FOR_DATA`.
6. The latest post-result Close must be from a completed NSE session strictly after the announcement date. Do not use live/intraday price.

## 6. Status model and output fields

Recommended statuses:

- `READY_EPS_DECLINE`: all data checks passed and an EPS decline is present.
- `NEAR_UTURN_ZONE`: latest post-result Close is within the estimated ± tolerance zone.
- `OUTSIDE_UTURN_ZONE`: valid calculation, but price is outside the zone.
- `NO_EPS_DECLINE`: current annual EPS did not decline.
- `WAIT_FOR_DATA`: missing, stale or incomplete required input.
- `UNVERIFIED`: data exists but official filing / period / basis / unit reconciliation is incomplete.
- `NOT_COMPARABLE_FOR_THIS_FORMULA`: EPS sign transition or incompatible EPS basis / periods.
- `CORPORATE_ACTION_REVIEW_REQUIRED`: EPS/share-price comparability is affected by an unadjusted corporate action.

Output columns should include the full input contract plus:
`EPS_Drop`, `Reference_PE`, `Expected_Correction`, `U_Turn_Target`, `Lower_Bound`, `Upper_Bound`, `Near_U_Turn_Support` (legacy-compatible boolean, but display label should say proximity zone), `U_Turn_Status`, `U_Turn_Reason`, `Calculation_Version`.

## 7. ECMS integration boundary

- Research-only output file: `outputs/ecms/fundamental_uturn_research.csv`.
- Independent module; do not alter P0–P8 scan order, EOD trigger, Morning confirmation, fundamental PASS/FAIL/WAIT gate, candidate inclusion, cache keys, Telegram decision messages or NSE V8.
- U-Turn output is an additional evidence layer. It must never promote an unverified fundamental row to PASS or reject a candidate solely because the U-Turn calculation is unavailable.
- Keep the raw source observations and calculation output separately auditable.
- No production workflow invocation or automatic scheduled job until the design is implemented, unit-tested and manually reviewed.

## 8. Research implementation v1

Implemented in `strategies/ecms/fundamental_uturn.py` with tests in `tests/test_ecms_fundamental_uturn.py`.

- `select_pre_result_peak()` selects the maximum High from the latest 20 supplied pre-announcement sessions, excluding the entire result announcement date. The caller must supply validated NSE trading-session OHLC rows; this function does not fetch or infer the NSE calendar.
- `calculate_uturn_targets()` enforces consecutive annual FYs, diluted EPS only, positive EPS, explicit consolidated/standalone basis, official-verification flags, corporate-action adjustment flag, and a completed post-result close strictly after the announcement date.
- It calculates the two equivalent target formulas and fails closed on a mismatch. Default proximity tolerance is ±3%.
- Outputs are research observations only; `Near_U_Turn_Support` remains for legacy compatibility, while the user-facing interpretation must be “proximity zone”, not confirmed support.
- No provider, NSE price feed, result-announcement scraper, workflow, Telegram, cache, EOD/Morning, P0–P8 or NSE V8 integration was added.
- The first 3–5 issuer sample has not been populated: issuer selection is blocked until official FY EPS, exact announcement timestamp, 20-session exchange OHLC and corporate-action comparability are evidenced. No symbols or values are fabricated.

## 9. Minimum tests before any live shadow use

1. Example: prior EPS 20, current EPS 16, peak High 400 gives reference P/E 20, correction 80 and target 320.
2. Equivalent target formula returns same value.
3. EPS growth/equal EPS returns `NO_EPS_DECLINE`.
4. Zero/negative/missing EPS never divides or creates a target.
5. Basic-vs-diluted mismatch returns `WAIT_FOR_DATA`.
6. Standalone-vs-consolidated mismatch returns `WAIT_FOR_DATA`.
7. Non-consecutive or mismatched FY periods return `WAIT_FOR_DATA`.
8. Announcement date is excluded from pre-result OHLC window.
9. Only 20 valid completed sessions qualify under the default window.
10. Missing/duplicate OHLC, invalid High, stale price and corporate-action ambiguity fail closed.
11. ±3% lower/upper boundaries are inclusive; outside values are false.
12. Post-result close from announcement day or earlier is rejected.
13. Duplicate symbols/events cannot create duplicate output rows.
14. All outputs preserve source URLs, dates, units, basis and calculation version.
15. Research module failure does not interrupt or modify the existing ECMS scan.

## 10. Remaining research gates

1. Run the unit tests in GitHub Actions and fix any failures.
2. Select 3–5 NSE Main Board issuers only after official source and price-history coverage is checked; record exclusions and missing evidence.
3. Validate annual diluted EPS against issuer-matched NSE/BSE official filings/XBRL, with identical consolidated/standalone basis and FY period.
4. Validate 20-session OHLC and event timestamps; check splits, bonuses, rights and other corporate actions.
5. Produce a manually reviewed research CSV with source URLs and per-field provenance.

No implementation or production behavior is approved by this design document.


## 11. Initial FY2026 issuer sample

Three NSE Main Board issuers have been selected for a source-verification sample: INFY, ACI and AARTIIND. FY2025/FY2026 consolidated diluted EPS and result approval date/time have been checked against NSE iXBRL and NSE annual-report documents. The sample deliberately includes one EPS-decline case (ACI) and two no-decline cases (INFY, AARTIIND). See `research/ecms_uturn/SAMPLE_UNIVERSE_FY2026.md` and `research/ecms_uturn/sample_universe_fy2026.csv`.

The 20-session peak High, post-result close, corporate-action adjustment and full OHLC provenance are not yet populated. The sample is therefore not eligible for U-Turn target calculation until those fields are independently verified.


## 12. Official NSE OHLC intake

The research-only parser `strategies/ecms/uturn_nse_ohlc.py` consumes caller-supplied daily NSE CM UDiFF bhavcopy tables. It validates the official archive host, date encoded in the source URL, `TradDt`, `Sgmt=CM`, `FinInstrmTp=STK`, `SctySrs=EQ`, ticker, positive High/Close, Indian equity ISIN and a stable ISIN across all 20 sessions. It requires the caller to provide exactly 20 verified NSE trading dates; it does not infer holidays or fetch network data. The peak selector returns the source URL corresponding to the selected maximum High.

NSE's official archive pages list security-wise price/volume archives and daily bhavcopy reports. The UDiFF cash-market bhavcopy uses fields including `TradDt`, `TckrSymb`, `SctySrs`, `HghPric` and `ClsPric`. Reference: [NSE Historical Reports](https://www.nseindia.in/static/resources/historical-reports-capital-market-daily-monthly-archives), [NSE All Reports](https://www.nseindia.com/all-reports/).

No actual 20-session files have yet been downloaded or reconciled for INFY, ACI or AARTIIND. The parser's fixture tests validate logic only; they do not substitute for issuer-specific source-file verification.


## 13. Two-sided U-Turn research extension

The U-Turn concept has two distinct research directions. They must remain separate calculations and separate status fields; neither is a trade signal.

### A. Downside / potential-bottom side

The existing annual diluted-EPS valuation-reset calculator remains the downside valuation component. It estimates a reset zone only when the prior and current completed-FY diluted EPS values are positive, comparable and verified. The price-context layer may then report:
- `RESET_ZONE_ONLY`: completed-session Close is inside the estimated valuation zone, without the required price/RSI stabilization evidence.
- `BOTTOM_WATCH`: Close is inside the zone, RSI is at/below the configurable oversold research threshold, and both Close and RSI have improved versus the previous completed session.
- `WAIT_FOR_DATA`: incomplete OHLCV history or invalid inputs.

Even `BOTTOM_WATCH` is only a research observation, not a confirmed bottom, support or entry signal.

### B. Upside / overextension side

A separate OHLCV context module, `strategies/ecms/uturn_two_sided.py`, measures:
- Wilder RSI (default 14 sessions);
- 20-session and 50-session simple moving averages;
- latest Close extension versus SMA20;
- latest Volume versus the preceding 20 completed sessions' average Volume (the current session is excluded from the average).

Initial configurable research defaults: RSI >= 70, Close extension >= 10% above SMA20, and volume expansion ratio >= 1.5. These are exploratory thresholds only, not validated trading thresholds. Classifications:
- `OVEREXTENDED`: RSI and SMA20 extension conditions are both met.
- `STRETCHED`: only one of those conditions is met.
- `MOMENTUM_STRONG`: Close > SMA20 > SMA50 with RSI >= 55; this is explicitly not an overextension call.
- `WEAKENING`: Close < SMA20, RSI < 50 and volume ratio >= the configured expansion threshold.
- `NEUTRAL`: none of the above.
- `WAIT_FOR_DATA`: incomplete/invalid completed-session OHLCV history.

These labels identify momentum/extension context, not a market top or reversal. An overbought RSI alone does not prove a top; strong trends can remain overbought. EPS growth/decline remains a separate fundamental context and must not be inferred from price indicators.

### Two-sided output contract and isolation

Keep the existing downside valuation result (for example `U_Turn_Target` and `U_Turn_Status`) separate from the price-context result (for example `Price_Context_Status`, `RSI14`, `SMA20`, `SMA50`, `ExtensionPct_SMA20`, `VolumeRatio_Prior20`). Do not merge the two statuses into a single buy/sell label. For every stock, preserve `WAIT_FOR_DATA` independently on either side when inputs are missing.

The two-sided module is research-only. It does not alter the seven fundamental metrics, candidate inclusion, P0–P8 order, EOD trigger, Morning confirmation, production cache, Telegram decisions, schedules or NSE V8. No historical backtesting, basketting, orders or auto-buy/sell.
