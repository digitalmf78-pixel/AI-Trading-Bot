# PI Industries (PIIND) — Bad-Result U-Turn Cache Replay

**Research branch:** `research/bharat-sm-data-fundamental-audit-2026-11-17`  
**Replay run:** [44058341441](https://github.com/digitalmf78-pixel/AI-Trading-Bot/actions/runs/44058341441) — successful  
**Code commit:** `1f3273b0e5ceca1ca27b00c7d1de91ddf85bcaf4)  
**Data:** restored shared NSE V8 cache, read-only; 202 OHLCV sessions and 200 delivery sessions through 2026-11-16.

## Why PIIND was selected

PI Industries announced Q2 FY27 results on 2026-11-04. The consolidated Q2 FY27 PAT was ₹122.2 crore versus ₹409.3 crore in Q2 FY26, a decline of approximately 70.1%. Revenue declined approximately 9.1%; EBITDA declined approximately 56.5%. The official results were approved at the board meeting on 4 Nov 2026, which concluded at 7:00 p.m. IST. Therefore, the first post-result market session is 5 Nov 2026.

Official source: [PI Industries Q2 FY27 results PDF](https://nsearchives.nseindia.com/corporate/PIIND_04112026193824_Resultssd.pdf).

## Annual diluted EPS inputs and formula

The formula uses annual diluted EPS only, not quarterly EPS:

| Input | Value | Basis |
|---|---:|---|
| Previous FY diluted EPS | ₹109.42 | Consolidated FY2025 |
| Current FY diluted EPS | ₹87.06 | Consolidated FY2026 |
| Annual EPS decline | 20.44% | FY2025 → FY2026 |
| Pre-result peak window | 20 completed sessions | 2026-10-05 to 2026-11-03 |
| Highest High in window | ₹2,259.00 | 2026-10-07 |
| Reference PE | 20.64x | ₹2,259 / ₹109.42 |
| Expected correction | ₹461.63 | (₹109.42 − ₹87.06) × Reference PE |
| Provisional U-Turn target | **₹1,797.37** | Peak − expected correction |
| Working zone | **₹1,761.43–₹1,833.32** | ±2% around target |

Official EPS sources:
- [PI Industries FY2025–26 audited consolidated results](https://www.piindustries.com/wp-content/uploads/2026/05/Audited-financial-Results-March-31-2026.pdf): consolidated diluted EPS FY2026 ₹87.06 and FY2025 ₹109.42.
- [PI Industries Q2 FY27 consolidated and standalone results](https://www.piindustries.com/wp-content/uploads/2026/11/Quarter-September-30-2026-Standalone-and-Consolidated.pdf): corroborates quarterly results and annual comparative EPS disclosures.

## What the cached price did after the result

Post-result window: 2026-11-05 to 2026-11-16 (8 cached sessions; includes the special Muhurat session on 8 Nov).

| Date | Open | High | Low | Close | Delivery % | RVOL | Observation |
|---|---:|---:|---:|---:|---:|---:|---|
| 05-Nov | 2,057.20 | 2,077.70 | 1,749.50 | 1,770.00 | 30.63 | 30.11x | Closed inside zone; very high turnover, weak delivery participation |
| 06-Nov | 1,753.00 | 1,758.00 | 1,716.40 | 1,735.00 | 21.81 | 1.75x | Below zone; continued weakness |
| 08-Nov | 1,738.00 | 1,754.40 | 1,737.10 | 1,750.70 | 39.64 | 0.13x | Green session, but low relative volume |
| 09-Nov | 1,741.00 | 1,742.20 | 1,699.40 | 1,712.90 | 40.13 | 1.80x | Weak close |
| 11-Nov | 1,727.00 | 1,776.00 | 1,712.90 | 1,761.00 | 40.45 | 1.58x | Intraday zone touch; close ₹0.43 below zone floor |
| 12-Nov | 1,744.00 | 1,778.80 | 1,740.00 | 1,740.20 | 47.14 | 1.09x | Intraday zone touch; failed to hold |
| 13-Nov | 1,740.20 | 1,741.00 | 1,702.50 | 1,714.80 | 38.43 | 0.54x | Weakness resumed |
| 16-Nov | 1,712.70 | 1,714.00 | 1,675.00 | 1,680.00 | 39.84 | 0.55x | New post-result low |

## Buying / U-Turn verdict

**Status: NO CONFIRMED BUYING / NO CONFIRMED U-TURN as of 2026-11-16.**

Evidence:
- Price entered the working zone on 5 Nov and closed at ₹1,770, but delivery was only 30.63%; the 30.11x RVOL reflects unusually heavy turnover, not proof of delivery accumulation.
- No post-result session had delivery >=60%.
- 11 Nov and 12 Nov traded into the target zone intraday but could not sustain a close inside it.
- Price subsequently declined to a new post-result low of ₹1,675 on 16 Nov.
- Latest close ₹1,680 was 6.53% below the calculated target; rebound from the latest low was only 0.30%.

The price-zone touch is a valuation/price observation, not a buy signal. The evidence so far points to continued selling pressure or weak demand rather than confirmed accumulation. Keep the U-Turn status as **WAIT / NO CONFIRMATION** and do not label the low as a bottom.

## Method and limitations

- Pre-result peak = highest High across the 20 completed sessions strictly before the 4 Nov result announcement date.
- Annual diluted EPS only; consolidated FY2025/FY2026 basis used consistently.
- Target = peak × current annual diluted EPS / previous annual diluted EPS.
- Zone = ±2% around the target; this is a research tolerance, not an order band.
- Delivery % and RVOL are read from the same NSE cache sessions. RVOL = current volume / previous 20 completed sessions' average volume, excluding the current session.
- No entry, exit, P&L, brokerage, slippage or position sizing was simulated.
- Corporate-action and adjusted-price reconciliation is still pending. Treat the calculated target as provisional until that audit passes.
- This single-stock case study does not establish a strategy win rate and does not change production code, cache, scanner, or Volume Gainers selection.

## Next research step

Repeat this same event-study on 1–2 more companies with a verified weak Q2 FY27 result, official annual diluted EPS, and complete cached price/delivery history. Only after multiple cases should we decide whether the U-Turn layer is useful.