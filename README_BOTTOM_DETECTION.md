# NSE V8 — Independent Bottom Detection (Category A/B)

## Purpose
Adds a separate, informational bottom-detection report. It does not modify the existing Delivery A/B, RVOL, liquidity, fundamentals, news, EMA44, ranking, risk/reward, chase, or final-watchlist gates. It does not create BUY/SELL instructions or place orders.

## Categories
- **Category A — Potential Bottom:** price is within 3% of the nearest available 20D/50D/100D/200D low (or within 1.5 ATR) and at least one early stabilization clue exists (bullish close-location candle, declining recent volume, a confirmed pivot low, or double-bottom proximity). Status: `BOTTOM_FORMING`. This is not a confirmed reversal.
- **Category B — Confirmed Bottom Reversal:** requires two confirmed pivot lows (3 candles left + 3 candles right), the latest pivot low higher than the previous pivot low, bullish candle, close above the post-pivot swing high, current volume at least 1.2x the previous 20-session average, and close above EMA44. Status: `REVERSAL_CONFIRMED`.
- **Double bottom:** two confirmed pivot lows are within 0.75 × ATR(14). It is an independent diagnostic; it does not by itself qualify Category B.
- **WAIT_FOR_DATA:** insufficient history or missing required evidence is not treated as a pass.

## Support levels
20D/50D/100D/200D lows are calculated from complete available lookback windows only. The nearest support is the highest valid lookback low at or below the current close.

## Integration
After existing support/resistance calculations, the scanner writes:
`outputs/v8_bottom_detection_YYYYMMDD.csv`

The report receives the scanner's existing candidate rows and full EOD analysis history. It is intentionally separate and does not change the main candidate dataframe or any downstream filter.

## Validation
Run:
`python -m pytest -q test_bottom_detection.py`
and the existing focused V8 regression suite:
`python -u test_v8_regression.py`

No live NSE data or GitHub Actions execution is claimed by this README; CI must validate the pushed branch.
