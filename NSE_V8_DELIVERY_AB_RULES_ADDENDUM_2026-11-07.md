# NSE V8 — Authoritative Delivery A/B Rules Addendum
**Updated:** 2026-11-10  
**Status:** Active production rules  
**Scope:** Delivery A/B screening only. This addendum supplements the Master Specification; it does not replace or rewrite it.

## 1. Lookback and valid sessions
- Use the 30-calendar-day window ending on and including the applicable EOD as-of date.
- Count all valid, distinct, candidate-specific NSE Delivery report sessions in this window; never use a report dated after the as-of date.
- Do not restrict production A/B classification to the latest five reports. If more than five valid sessions exist, use every valid in-window session.
- At least five valid distinct sessions are required. Fewer than five means `WAIT_FOR_DATA`, not PASS or FAIL.
- 30 calendar days is a calendar window, not an expectation of 30 trading-session reports.

## 2. Category A — Average Delivery Strength
- Calculate the arithmetic average Delivery % across all valid sessions for that symbol in the 30-calendar-day window.
- PASS when the average is **>=60.00%**. Exactly 60.00% passes.
- A daily value below 60.00% does not by itself fail Category A if the full-window average remains >=60.00%.

## 3. Category B — Consistent Daily Delivery Strength
- PASS only when every valid session in the same 30-calendar-day window has Delivery % **>=60.00%**.
- Exactly 60.00% passes. If even one valid session is below 60.00%, Category B fails.
- Category A and B are evaluated independently. A stock can pass A while failing B.
- Category B represents stronger consistency, not a BUY signal or proof of institutional buying.

## 4. Eligibility and output
- Production eligibility is the full **A OR B** union. Preserve the actual category membership/status and de-duplicate symbols.
- Since Category A is the average of the same values checked by B, a B pass mathematically implies an A pass. Retain B-only status as a defensive/audit field but flag any occurrence for consistency investigation.
- For every stock, report: as-of date; 30-calendar-day window start/end; valid session count; coverage where determinable; every valid session date and Delivery %; average Delivery %; minimum and maximum daily Delivery %; Category A status; Category B status; union eligibility/membership; and PASS/FAIL/WAIT_FOR_DATA reason.
- Explicitly display the actual valid-session count (e.g. 5, 12, 20) so users can distinguish a five-session sample from a wider sample. Do not imply 30 reports are expected.
- Keep 5D/10D/20D consistency fields as additional observations only; they do not replace or alter the 30-calendar-day A/B eligibility rule.

## 5. Data reuse and historical integrity
- Fetch/prepare the 30-day delivery-report set once per EOD run and reuse the same in-memory report set for A/B and 5D/10D/20D consistency analysis.
- For historical/backtest signals, use only reports available on or before that signal date and inside its 30-calendar-day lookback.
- Missing/invalid report data is not a pass. Expected but unavailable reports must remain visible as missing/WAIT evidence; do not fabricate daily values.

## 6. Separate five-session Delivery-only watchlist
- The strict five-session Delivery-only watchlist remains a separate artifact with its own explicitly requested rule (each of exactly five sessions >=60%).
- Do not confuse that standalone shortlist with the production 30-calendar-day A/B pipeline.

## 7. Change control
This update clarifies the previously approved 30-calendar-day A/B rule and minimum five-valid-session requirement. It does not change the 60.00% thresholds, lookback window, A OR B eligibility semantics, RVOL, liquidity, fundamentals, technical filters, risk controls, or any unrelated production parameter. The original Master Specification remains unchanged.
