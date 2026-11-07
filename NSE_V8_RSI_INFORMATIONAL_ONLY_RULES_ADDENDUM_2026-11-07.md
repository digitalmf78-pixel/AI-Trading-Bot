# NSE V8 RSI Informational-Only Rules Addendum — 2026-11-07

## Authority and scope
This addendum records the agreed RSI policy for NSE Swing Trading V8.0. It supplements the Master Specification; the Master Specification is not modified.

## Absolute no-rejection rule
- RSI is an informational technical-observation and Telegram-reporting module only.
- RSI values, RSI zones, RSI direction, RSI retest, RSI divergence, overbought, or oversold conditions MUST NOT reject, exclude, suppress, downgrade, or change the eligibility of any stock.
- RSI MUST NOT be used as a hard gate, soft gate, ranking penalty, score adjustment, tie-breaker, candidate cap, watchlist gate, entry eligibility gate, or Telegram inclusion filter.
- Missing RSI history or a missing RSI pattern result MUST NOT cause a stock rejection. Show WAIT_FOR_DATA / NOT_EVALUATED and retain the stock through all unrelated existing gates.
- RSI MUST NOT change RVOL > 1.5, Delivery A/B, liquidity, fundamentals, existing technical rules, news, sector, or risk controls.

## RSI observations
- Calculate RSI using period 14.
- Report the current RSI14 value and prior-session RSI14 where available.
- Descriptive zone: RSI <= 30 = OVERSOLD; RSI >= 70 = OVERBOUGHT; otherwise NEUTRAL.
- Direction compares current RSI14 with prior-session RSI14: change > +0.5 = RISING; change < -0.5 = FALLING; otherwise FLAT.
- Behaviour labels are descriptive only: OVERSOLD_RECOVERY, OVERSOLD_PRESSURE, OVERBOUGHT_COOLING, OVERBOUGHT_MOMENTUM, OVERSOLD, OVERBOUGHT, RSI_RISING, RSI_FALLING, or NEUTRAL.
- Retest and divergence must be reported as NOT_EVALUATED until dedicated, validated detectors and their exact definitions are implemented. Do not infer or fabricate a detected pattern.

## Telegram reporting
For every stock already included by the existing non-RSI pipeline, include RSI14, zone, direction, behaviour, retest status, and divergence status when available. RSI must not determine which stocks appear in Telegram. Telegram text must identify RSI information as informational only, not a BUY recommendation or rejection criterion.

## Change control
No existing stock-selection threshold or non-RSI filter is changed by this addendum. No automatic order behaviour is introduced. The RSI module may be extended only as an informational observer unless a future explicit user-approved rule changes this policy.
