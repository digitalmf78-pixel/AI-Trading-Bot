# NSE V8 — Authoritative Delivery A/B Rules Addendum
**Effective date:** 2026-11-07  
**Status:** Active implementation rules  
**Scope:** Delivery A/B screening only. This addendum does not replace or rewrite the Master Specification.

## 1. Lookback window
- Use the 30-calendar-day window ending on the applicable as-of date.
- The as-of date is inclusive; dates after the as-of date must never be used.
- For historical/backtest signals, use only reports that were available on or before that signal date.
- Consider all valid, distinct, candidate-specific NSE delivery reports in that window. Do not silently restrict the classification to the latest five reports.

## 2. Minimum data requirement
- A symbol must have at least five valid, distinct delivery-report sessions in the window.
- Fewer than five valid sessions means `WAIT_FOR_DATA`; it is not a rejection and must not be treated as a pass.

## 3. Category A — average delivery
- Calculate the arithmetic average Delivery % across all valid sessions for that symbol in the 30-calendar-day window.
- Category A passes when the average is **>= 60.00%**.
- Exactly 60.00% passes. Any value below 60.00% fails Category A.

## 4. Category B — every-session delivery
- Category B passes only when every valid session in the same 30-calendar-day window has Delivery % **>= 60.00%**.
- Exactly 60.00% passes. If even one valid session is below 60.00%, Category B fails.

## 5. Pipeline and data reuse
- Fetch/prepare the 30-day delivery-report set once per EOD run.
- Reuse the same in-memory report set for Delivery A/B classification and 5D/10D/20D delivery-consistency analysis; avoid duplicate NSE requests in the same run.
- Preserve separate Category A and Category B audit statuses/metrics. Downstream V8 logic may union eligible A and B symbols while retaining membership (A-only / A-and-B).
- Do not convert `WAIT_FOR_DATA` into a pass or rejection.

## 6. Historical test integrity
- Backtests must apply the same 30-calendar-day A/B rules point-in-time for each signal date.
- Exclude future reports and reports outside the 30-day window.
- A workflow completing successfully is not evidence of a completed backtest unless it reports actual usable cached price data and performance metrics. Missing cache must remain `WAIT_FOR_DATA`.

## 7. Change control
- This addendum records the Delivery A/B rules agreed on 2026-11-07.
- The Master Specification remains unchanged. Any future change to these thresholds, windows, or eligibility semantics requires explicit review and a separately documented decision.
