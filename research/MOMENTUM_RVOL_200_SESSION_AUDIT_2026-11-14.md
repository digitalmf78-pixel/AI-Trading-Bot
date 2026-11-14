# 200-Session Momentum / RVOL Audit — 2026-11-14

## Scope and source

This is a research-only secondary analysis of the GitHub Actions artifact from the successful Delivery A/B historical backtest run 43476942945. It uses the artifact's `rvol_strategy_backtest/signals.csv` (85,741 symbol-date observations), not a new market-data download.

Coverage recorded in the artifact:
- 201 cached price files / 201 price dates; 502,424 rows; 2,996 symbols.
- Price dates: 2026-01-16 through 2026-11-09.
- 203 Delivery cache files / 203 dates; 200 requested session reports valid from 2026-01-19 through 2026-11-13.
- No cache file issues; no network calls during the backtest.
- EQ-series cache only; not a point-in-time official Main Board universe; no point-in-time fundamentals.

## Method

- RVOL = current session volume / average volume of the previous 20 sessions, as recorded in the source CSV.
- Forward returns and MFE/MAE are the source backtest's close-to-close research measures, not executable next-session trades.
- To reduce repeated daily signals for the same symbol, a non-overlap sample was derived: sort each symbol's observations by official cached session date, keep the first, then keep the next observation only when at least 21 cached session indices have elapsed since the previously selected observation. This yields 5,613 observations before horizon completeness filtering.
- Win = forward closing return > 0.
- MFE>=15% means the source's maximum favorable move over that horizon reached at least 15%; it is not a realized 15% booked return.
- Profit Factor = sum of positive forward returns / absolute sum of negative forward returns.
- The 20D sample excludes incomplete 20-session outcomes.

## RVOL buckets — non-overlapping sample

| RVOL bucket | Complete 20D n | Win rate | Avg 20D return | Median | PF | MFE >=15% |
|---|---:|---:|---:|---:|---:|---:|
| <0.75 | 2,468 | 43.48% | -0.679% | -1.181% | 0.841 | 14.02% |
| 0.75–<1.0 | 793 | 50.69% | +0.501% | +0.116% | 1.146 | 16.02% |
| 1.0–<1.5 | 826 | 52.42% | +1.678% | +0.370% | 1.493 | 19.61% |
| 1.5–<2.0 | 364 | 53.30% | +1.746% | +0.648% | 1.445 | 24.18% |
| 2.0–<3.0 | 260 | 47.31% | +0.602% | -0.197% | 1.136 | 22.69% |
| 3.0–<5.0 | 133 | 51.13% | +2.637% | +0.417% | 1.623 | 31.58% |
| >=5.0 | 122 | 52.46% | -1.103% | +0.509% | 0.857 | 31.97% |

### 5D and 10D comparison

| RVOL bucket | 5D n | 5D win | 5D avg | 10D n | 10D win | 10D avg |
|---|---:|---:|---:|---:|---:|---:|
| <0.75 | 2,661 | 44.68% | -0.021% | 2,608 | 41.76% | -0.172% |
| 0.75–<1.0 | 886 | 44.92% | -0.203% | 857 | 45.97% | -0.083% |
| 1.0–<1.5 | 906 | 46.36% | -0.061% | 881 | 46.31% | +0.451% |
| 1.5–<2.0 | 405 | 46.17% | -0.056% | 398 | 48.99% | +0.692% |
| 2.0–<3.0 | 292 | 47.60% | -0.190% | 282 | 46.10% | +0.255% |
| 3.0–<5.0 | 156 | 51.92% | +1.213% | 148 | 50.68% | +2.415% |
| >=5.0 | 142 | 50.70% | -1.768% | 132 | 37.88% | -2.987% |

## Liquidity buckets — non-overlapping sample, 20D

The source scanner's minimum average traded-value gate is INR 1.5 crore, so the first bucket effectively represents INR 1.5 crore to <2 crore.

| 20D average traded value | n | Win rate | Avg return | PF | MFE >=15% |
|---|---:|---:|---:|---:|---:|
| INR 1.5–<2 crore | 759 | 49.93% | +1.347% | 1.351 | 24.11% |
| INR 2–<5 crore | 1,302 | 48.69% | +0.941% | 1.222 | 22.43% |
| INR 5–<10 crore | 824 | 49.27% | -0.197% | 0.957 | 19.54% |
| INR 10–<20 crore | 615 | 45.04% | +0.178% | 1.043 | 17.40% |
| INR 20–<50 crore | 574 | 47.39% | -0.386% | 0.901 | 11.32% |
| >=INR 50 crore | 892 | 43.61% | -0.961% | 0.725 | 6.17% |

## Exact latest-five Delivery consistency — non-overlapping sample, 20D

| Consistency | n | Win rate | Avg return | PF | MFE >=15% |
|---|---:|---:|---:|---:|---:|
| HIGH (5/5 >=60%) | 390 | 52.82% | -0.002% | 0.999 | 7.95% |
| MODERATE (3–4/5) | 1,731 | 49.80% | +0.786% | 1.220 | 17.45% |
| LOW (0–2/5) | 2,845 | 45.31% | -0.086% | 0.981 | 18.63% |

This is a descriptive sidecar only. It does not justify changing the existing 30-calendar-day Delivery A OR B production gate.

## Regime sensitivity — RVOL 20D results

The historical sample is not stable across the selected date split. Using non-overlapping signals:

| RVOL | Before 2026-08-24: n / win / avg / PF | From 2026-08-24: n / win / avg / PF |
|---|---|---|
| <0.75 | 1,923 / 48.88% / +0.32% / 1.09 | 545 / 24.40% / -4.22% / 0.32 |
| 0.75–<1 | 635 / 56.06% / +1.24% / 1.41 | 158 / 29.11% / -2.45% / 0.53 |
| 1–<1.5 | 642 / 59.50% / +3.13% / 2.13 | 184 / 27.72% / -3.40% / 0.39 |
| 1.5–<2 | 303 / 59.08% / +2.93% / 1.81 | 61 / 24.59% / -4.14% / 0.23 |
| 2–<3 | 211 / 53.08% / +2.34% / 1.69 | 49 / 22.45% / -6.87% / 0.22 |
| 3–<5 | 109 / 54.13% / +4.60% / 2.52 | 24 / 37.50% / -6.28% / 0.35 |
| >=5 | 92 / 57.61% / -0.12% / 0.98 | 30 / 36.67% / -4.11% / 0.42 |

The split is descriptive and not a pre-registered independent test. The post-split 20D samples are smaller because the outcome horizon must be complete. Nevertheless, it is a strong warning that the apparent edge can disappear during a different market regime.

## Research interpretation

1. RVOL 1.0–2.0 has the best balance of sample size, 20D win rate and PF in the non-overlapping analysis.
2. RVOL 3.0–5.0 is the most interesting high-momentum research bucket: 31.58% of its 20D observations recorded MFE >=15%, with 51.13% closing Win Rate and PF 1.623. Sample size is only 133, so it is a candidate for validation, not a production rule.
3. RVOL >=5 is not a safe chase signal: despite a high MFE>=15% frequency, its average close-to-close return is negative and PF <1.
4. Delivery HIGH 5/5 does not improve the large-move rate in this sample. Do not make it a mandatory gate or positive score without additional validation.
5. The late-period breakdown means the next research phase must test market-regime filters and price-structure confirmation rather than merely raising the RVOL threshold.
6. Liquidity above INR 5 crore did not show a stronger 15% MFE rate in this sample; do not assume higher traded value automatically means better momentum.

## What is not tested yet

This artifact does not contain point-in-time EMA20/44/50/200 states, 5/10/20-session price momentum ranks, 20/50/100-session breakout states, base/VCP contraction labels, volume dry-up flags, sector-relative strength, historical news/fundamentals, or a four-position executable portfolio simulation.

Next research-only phase should add these features using only information available at each signal date, then compare:
- RVOL bands × EMA/trend alignment;
- RVOL bands × prior 20/50/100-session breakout;
- RVOL bands × base/VCP and volume dry-up;
- Delivery consistency × trend/structure (not as a standalone gate);
- Market-regime-conditioned results;
- 3%, 5%, 10%, and 15% MFE frequencies alongside MAE and close-to-close Win Rate;
- A next-official-session Open entry, conservative costs/slippage, predeclared exits, cash and max-four-position constraints.

No production scanner, Delivery A/B gate, score, ranking, watchlist membership, or trade behavior is changed by this report.
