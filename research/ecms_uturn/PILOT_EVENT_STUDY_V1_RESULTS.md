# ECMS U-Turn Pilot Event Study — V1 Results

**Run basis:** read-only NSE V8 cache, 2026-11-17 research branch.  
**Status:** research pilot; all price outcomes remain provisional pending corporate-action reconciliation and independent exchange-calendar verification.  
**No production changes, Volume Gainers dependency, orders, entry/exit simulation, or P&L.**

## Data coverage

- 204 price files and 202 price sessions were discovered in the restored cache.
- 606 symbol-session OHLCV rows were parsed for INFY, ACI and AARTIIND.
- 202 delivery files were discovered; 600 delivery rows matched symbol/session rows.
- Post-result windows had delivery rows for the observed sessions.
- Each event had 20 pre-result cache sessions matching its manifest list. The manifest calendar dates have not yet been independently checked against NSE's official calendar.
- The 3-symbol pilot was not randomly selected. It is descriptive only and not statistically representative. Cash dividends are excluded from the price-only horizon returns; see [PILOT_SAMPLE_DIVIDEND_CORPORATE_ACTION_REVIEW.md](PILOT_SAMPLE_DIVIDEND_CORPORATE_ACTION_REVIEW.md).

## EPS inputs and event-study observations

| Symbol | FY25 diluted EPS | FY26 diluted EPS | EPS status | Pre-result peak High | Provisional target | 21-session close return | 63-session close return | 126-session close return |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| INFY | ₹64.34 | ₹71.46 | No decline / control | ₹1,376.90 | No target | +1.20% | -9.85% | +0.99% |
| ACI | ₹13.12 | ₹8.65 | Decline | ₹639.80 | ₹421.82 | -10.13% | -13.18% | -28.99% |
| AARTIIND | ₹9.12 | ₹11.55 | No decline / control | ₹512.40 | No target | -4.96% | -0.25% | -10.01% |

Annual diluted EPS values were checked against official issuer / NSE sources; see [PILOT_SAMPLE_EPS_SOURCE_AUDIT.md](PILOT_SAMPLE_EPS_SOURCE_AUDIT.md).

## ACI zone and delivery/RVOL test

- Target: ₹421.82; ±2% zone: ₹413.38–₹430.26.
- The daily high/low range overlapped the zone on 8 sessions from 4 Nov to 13 Nov 2026.
- **Same-session confirmation count: 0.**
- 12 Nov: delivery 75.41%, but RVOL only 1.15x (below 1.5x).
- 13 Nov: RVOL 10.69x, but delivery only 23.19% (below 60%).
- Thus the two thresholds did not coincide on the same zone-touch session. No technical confirmation was recorded.
- A zone touch is not itself a bottom, accumulation, or trade signal.

## Interpretation

The only EPS-decline case in this pilot (ACI) later traded through the target zone, but it did so after a prolonged decline and without a session meeting both locked delivery/RVOL thresholds. At the 126-session observation endpoint, its close was 28.99% below the first post-result session close. This does **not** prove the formula is useful or useless: the pilot contains only one decline case and two no-decline controls, and no randomized sample.

The controls (INFY and AARTIIND) had no EPS decline, so the formula correctly withheld a downside target. Their post-result price changes are reported only as descriptive control outcomes.

## Remaining blockers before any stronger conclusion

1. Independently verify the 20-session calendar lists and result announcement timestamps against NSE records.
2. Reconcile bonus, split, rights, demerger and other corporate actions for every symbol over each observation window.
3. Expand to a predeclared, reproducible random sample from an eligible Main Board universe; record universe snapshot, seed, timestamp and every exclusion.
4. Preserve failed-data cases and negative outcomes; do not tune the thresholds after seeing results.
5. Keep all outputs research-only. No production ECMS integration is authorized by this report.
