# Gemini U-Turn Case Replay — Cached NSE Evidence

**Run:** [44056971135](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44056971135)  
**Commit:** `9cee004059444cb0cd624e897fcb10cbc604e4ac`  
**Scope:** isolated research branch only; restored NSE V8 cache read-only. No Volume Gainers selection and no production changes.

## Data coverage

- Bhavcopy files indexed: 202 (2026-01-21 to 2026-11-16)
- Delivery files indexed: 200
- Valid OHLCV rows: 404 (202 per symbol)
- Delivery rows loaded: 400 (200 per symbol)
- Cache parsing errors for the two requested symbols: 0

## Gemini HDFC Bank case

Gemini supplied zone ₹1,650–₹1,690, delivery >=60%, RVOL >=1.5, target +12%, stop -4%.

| Cached observation | Result |
|---|---:|
| Close range | ₹680.20–₹953.10 |
| Intraday High maximum | ₹994.00 |
| Delivery >=60% sessions | 99 |
| RVOL >=1.5 sessions | 24 |
| Both delivery and RVOL conditions | 15 |
| Closes inside Gemini zone | 0 |
| Valid EOD signals / executed trades | 0 / 0 |

The entire observed high range was below the supplied ₹1,650–₹1,690 zone. Therefore the cache period cannot reproduce Gemini's stated HDFC entries around ₹1,675. Price history adjustment/corporate-action basis and the original 202X dates must be reconciled before comparing.

## Gemini 63 Moons case

Gemini supplied zone ₹425–₹450, delivery >=60%, RVOL >=1.5, target +15%, stop -5%.

| Cached observation | Result |
|---|---:|
| Close range | ₹470.30–₹961.50 |
| Intraday Low minimum | ₹467.00 |
| Delivery >=60% sessions | 18 |
| RVOL >=1.5 sessions | 32 |
| Both delivery and RVOL conditions | 3 |
| Closes inside Gemini zone | 0 |
| Valid EOD signals / executed trades | 0 / 0 |

The minimum observed intraday Low, ₹467, remained above the supplied ₹425–₹450 zone. Thus no entry could occur in this cached period, even before applying the technical filters.

## Method used for the replay

- Signal evaluated after session T close.
- Close must be inside the supplied price zone.
- Same-session delivery percentage >=60%.
- RVOL = current session volume / average volume of the previous 20 completed sessions; current session excluded.
- Entry at T+1 open only if it remains inside the zone.
- HDFC target +12% / stop -4%; 63 Moons target +15% / stop -5%.
- Maximum holding period 63 sessions.
- If both stop and target occur in one daily candle, stop is assumed first; gap through stop exits at open.
- No overlapping positions per symbol.

## Conclusions and limits

1. **No trades were generated for either Gemini case in the available 2026 cache window.** This is not a 0% win-rate result; it is zero qualifying trades.
2. The delivery/RVOL filters did have qualifying sessions. The blocking condition was the supplied price zone: no close in-zone for either stock, and no intraday range overlap for 63 Moons.
3. Gemini's historical trade dates are shown as `202X`, not actual dates. They cannot be mapped to sessions or independently verified.
4. EPS values were not supplied with exact financial-year labels, result announcement dates, or official diluted-EPS source references. The EPS/PE U-Turn target calculation was therefore not re-tested for these two stocks.
5. Corporate-action adjustment, price-series basis, brokerage, taxes and slippage are not audited/included. Outputs are research-only and provisional.
6. This replay does not validate the reported Gemini 66.7% or 75% win rates and must not be used as a performance claim.

## Required evidence to continue validation

For each stock: exact calendar year and dates for every simulated trade; exact FY labels and consolidated/standalone basis for both diluted EPS values; result announcement date/time; source filing; and confirmation of the price adjustment basis used for the quoted peak/zone.
