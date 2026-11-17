# ECMS Fundamental U-Turn Module — Research Design

**Design date:** 2026-11-17  
**Status:** Research design only; not production-approved.  
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
| EPS basis | Use diluted EPS consistently where both years are available; do not silently mix diluted and basic EPS. If only basic EPS exists for either year, mark basis mismatch / WAIT_FOR_DATA until explicitly resolved. |
| EPS units | INR per share, same share class and comparable corporate-action basis |
| Peak event date | Official NSE/BSE result announcement publication date/time for the latest completed FY |
| Pre-result price window | Proposed configurable default: 20 completed NSE trading sessions ending strictly before the announcement calendar date. This lookback is a research default, not a user-confirmed investment rule. |
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
| `EPS_Basis` | `DILUTED` or `BASIC`; must match |
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

The module must also retain units, consolidated/standalone basis, source retrieval timestamp, filing period end, raw source labels, corporate-action adjustment status and validation reasons. EPS comparisons must use the same reporting basis. If official consolidated EPS is unavailable for either year, do not pair it with standalone EPS.

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

## 8. Minimum tests before any live shadow use

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

## 9. Open decisions before coding

- Confirm whether the proposed 20-session pre-result peak window is acceptable, or specify another number.
- Confirm whether the first research release should require diluted EPS only (recommended), or permit basic EPS when diluted EPS is absent.
- Confirm whether the first test universe should be 3–5 liquid NSE Main Board issuers with recent official annual results.

No implementation or production behavior is approved by this design document.
