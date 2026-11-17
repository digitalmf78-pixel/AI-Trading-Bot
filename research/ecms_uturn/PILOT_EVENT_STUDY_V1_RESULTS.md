# ECMS U-Turn Pilot Event Study — V1 Results

**Status:** validation gates passed for this three-symbol descriptive pilot. Results remain research-only and are not a trade signal.  
**Latest successful U-Turn CI:** [run #44077735477](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44077735477)  
**Latest successful read-only cache audit:** [run #44077339832](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44077339832)

No production ECMS changes, Volume Gainers dependency, orders, entry/exit simulation or P&L.

## Data and validation

- 204 price files, 202 sessions and 606 symbol-session OHLCV rows were processed.
- 202 delivery files were discovered; 600 delivery rows matched symbol/session rows in the event-study cache.
- Strict audit verified all **60/60** expected pre-result OHLC rows (20 per symbol), with matching ISINs and one valid symbol row per session.
- Event-study and strict parser agreed on all three 20-session windows, peak dates and peak Highs.
- Independent NSE official 2026 equity-calendar comparison passed for all three windows.
- Latest post-result close coverage: 3/3 READY (16-Nov-2026).
- Delivery coverage for the three pre-result windows: 60/60 matched.
- Event dates and first post-result sessions were checked against issuer/NSE evidence. ACI's exact public release minute remains unverified; the board meeting was 18:00–21:30 on 11-May and its NSE outcome PDF is timestamped in the archive as 12-May 00:30:06.
- Corporate-action review found no bonus/split/rights/demerger requiring a stock-price adjustment in the reviewed event windows. Cash dividends are listed separately and included in a gross no-reinvestment simple-return estimate.

Machine-readable audit: `v8_cache_audit/official_calendar_corporate_action_audit.json` in the latest CI artifact.

## EPS inputs, pre-result peaks and horizon outcomes

Annual consolidated diluted EPS values were verified from official annual reports / NSE filings. The 20-session windows and peaks passed the independent calendar and parser checks.

| Symbol | FY25 diluted EPS | FY26 diluted EPS | EPS status | Peak High | Peak date | U-Turn target |
|---|---:|---:|---|---:|---|---:|
| INFY | ₹64.34 | ₹71.46 | No decline / control | ₹1,376.90 | 08-Apr-2026 | No target |
| ACI | ₹13.12 | ₹8.65 | EPS decline | ₹639.80 | 04-May-2026 | ₹421.82 |
| AARTIIND | ₹9.12 | ₹11.55 | No decline / control | ₹512.40 | 29-Apr-2026 | No target |

### Price-only and gross dividend-inclusive simple returns

The dividend-inclusive column adds gross cash dividends whose ex-dates fall after the start session and on/before the horizon end. It assumes no reinvestment and makes no tax/fee adjustment; it is **not** an official total-return index.

| Symbol | Horizon | End session | Price-only return | Cash dividend added/share | Gross dividend-inclusive simple return |
|---|---:|---|---:|---:|---:|
| INFY | 21 | 25-May-2026 | +1.20% | ₹0.00 | +1.20% |
| INFY | 63 | 24-Jul-2026 | -9.85% | ₹25.00 | -7.68% |
| INFY | 126 | 26-Oct-2026 | +0.99% | ₹25.00 | +3.15% |
| ACI | 21 | 10-Jun-2026 | -10.13% | ₹2.50 | -9.72% |
| ACI | 63 | 10-Aug-2026 | -13.18% | ₹2.50 | -12.76% |
| ACI | 126 | 09-Nov-2026 | -28.99% | ₹2.50 | -28.57% |
| AARTIIND | 21 | 03-Jun-2026 | -4.96% | ₹0.00 | -4.96% |
| AARTIIND | 63 | 03-Aug-2026 | -0.25% | ₹0.00 | -0.25% |
| AARTIIND | 126 | 03-Nov-2026 | -10.01% | ₹1.00 | -9.81% |

The 3-Nov-2026 INFY interim dividend of ₹26 falls after its 126-session endpoint (26-Oct) and is therefore not included in that horizon. It is recorded in the corporate-action audit.

## ACI target-zone and delivery/RVOL result

- Formula target: ₹421.82.
- ±2% zone: ₹413.38–₹430.26.
- Daily range overlapped the zone on 8 sessions from 04-Nov to 13-Nov-2026.
- **Same-session technical confirmation count: 0.**
- 12-Nov: delivery 75.41%, but RVOL 1.15x (below 1.5x).
- 13-Nov: RVOL 10.69x, but delivery 23.19% (below 60%).
- The two locked thresholds did not coincide on the same zone-touch session.
- A zone touch is not itself a bottom, accumulation, or trade signal.

## Interpretation

The one EPS-decline case (ACI) later traded through the calculated valuation zone, but it did so after a prolonged decline and without any session meeting both locked delivery/RVOL thresholds. At the 126-session endpoint its price-only close return was -28.99%; adding the ₹2.50 gross cash dividend gives a simple -28.57% estimate.

The controls (INFY and AARTIIND) had no EPS decline, so the formula correctly withheld a downside target. Their subsequent price changes are descriptive control outcomes, not evidence that the formula predicts returns.

## What this test does and does not establish

**Established:** date parsing was corrected; strict and event-study parsers now agree; 20-session windows match the official NSE 2026 equity calendar; post-result close and delivery rows are present; official EPS pairs and cash dividends are recorded; ACI's two same-session confirmation thresholds did not coincide.

**Not established:** predictive accuracy, a statistically meaningful hit rate, a profitable trading strategy, a reliable bottom detector, or generalization to the full Main Board universe.

The three-symbol pilot was not randomly selected and contains only one EPS-decline case. The fixed-seed five-stock source-verification sample (UNITDSPR, INSPIRISYS, BORANA, KEYFINSERV, JSWSTEEL) is separate; it produced no verified EPS-decline case and was not replaced or re-labelled as an event-study sample.

No entry/exit, position sizing, stop-loss, fees, slippage, tax, dividend reinvestment, or P&L simulation was performed. Production integration remains unauthorized.
