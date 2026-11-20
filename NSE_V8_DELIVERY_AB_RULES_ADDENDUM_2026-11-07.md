# NSE V8 — Authoritative Delivery A/B Rules Addendum
**Updated:** 2026-11-12  
**Status:** Active production rules  
**Scope:** Delivery A/B screening only. This addendum supplements the Master Specification; it does not replace or rewrite it.

## 1. Lookback and valid sessions
- Use the 30-calendar-day window ending on and including the applicable EOD as-of date.
- Count all valid, distinct, candidate-specific NSE Delivery report sessions in this window; never use a report dated after the as-of date.
- Use every valid in-window session up to the maximum available in the 30-calendar-day window. Do not stop at five when more reports exist.
- At least five valid distinct reports are required before evaluating either category. Fewer than five means `WAIT_FOR_DATA`, not PASS or FAIL.
- Thirty calendar days is a calendar window, not an expectation of 30 trading-session reports. Always show the actual valid report count.

## 2. Category A — Consecutive daily Delivery strength
- For each symbol, order all its valid distinct Delivery observations in the 30-calendar-day window chronologically.
- Count the longest uninterrupted run of consecutive valid symbol-specific NSE sessions where each daily Delivery % is >=60.00%.
- A below-60.00% day or a missing symbol observation breaks the run. Do not bridge missing sessions or fabricate values.
- Category A passes only when the longest consecutive run is at least 5 sessions. Exactly five passes; four or fewer fails.
- Display the longest run compactly as `A: n/30` (for example, six consecutive qualifying days = `A: 6/30`). The denominator is the 30-calendar-day lookback, not 30 expected trading sessions.

## 3. Category B — Total qualifying daily Delivery count
- Count all valid individual sessions in the same 30-calendar-day window where daily Delivery % is >=60.00%, whether consecutive or not.
- Category B passes only when at least 5 valid days meet the >=60.00% threshold. Exactly five passes; four or fewer fails.
- Display the total count compactly as `B: n/30`.
- A daily value exactly 60.00% passes.

## 4. Eligibility and output
- Evaluate A and B independently.
- Production eligibility is the full A OR B union. A stock passes the Delivery stage if A has a consecutive >=60% streak of at least five sessions OR B has at least five qualifying daily sessions, consecutive or not. Preserve A_ONLY, B_ONLY, A_AND_B membership and de-duplicate symbols.
- If the symbol has fewer than five valid distinct Delivery report sessions in the window, both categories remain WAIT_FOR_DATA, even if partial counts appear promising.
- If the latest valid report is stale under the existing freshness rule, both categories remain WAIT_FOR_DATA_STALE_REPORT; stale data must not pass.
- For every stock, report: as-of date; 30-calendar-day window start/end; valid session count; coverage where determinable; A longest consecutive daily-streak count/status; B total qualifying daily-session count/status; average/minimum/maximum daily Delivery %; latest report date; and PASS/FAIL/WAIT reason.
- The compact Telegram display is `A n/30 PASS|FAIL|WAIT | B n/30 PASS|FAIL|WAIT`.
- These are Delivery eligibility rules, not BUY signals and not proof of institutional buyer identity.

## 5. Data reuse and historical integrity
- Fetch/prepare the 30-day Delivery report set once per EOD run and reuse the same in-memory report set for A/B and other Delivery observations.
- For historical/backtest signals, use only reports available on or before that signal date and inside its 30-calendar-day lookback.
- Missing/invalid report data is not a pass. Expected but unavailable reports must remain visible as missing/WAIT evidence; do not fabricate daily values.

## 6. Separate five-session Delivery-only watchlist
- The standalone strict five-session Delivery-only watchlist remains a separate artifact if explicitly requested. Do not confuse it with the production 30-calendar-day A/B count rules.

## 7. Change control
This 20-Nov-2026 user-approved correction supersedes the previous rolling-average interpretation of Category A. Category B remains a total qualifying-day count. The original Master Specification file remains unchanged. No RVOL, liquidity, fundamentals, technical, risk, or unrelated production parameter is changed.
## 8. Display-only count implementation (2026-11-12)
- Scanner CSV now emits `DeliveryACount30DDisplay` and `DeliveryBCount30DDisplay`, formatted as `n/30` for eligible-to-evaluate, fresh symbol-specific reports.
- Numerators use the longest consecutive qualifying daily streak for Category A and the total qualifying daily observations for Category B. The denominator means 30 **calendar** days, not 30 actual trading reports.
- Fewer than five valid symbol reports or a stale window produces `WAIT_FOR_DATA/30`; raw count and status fields remain available for audit.
- Category A explicitly measures the longest consecutive qualifying streak; Category B measures the total qualifying days.
- No data source, eligibility condition, cache content, or strategy threshold was changed by this display-only patch. Test execution and end-to-end report verification are separate required checks.
