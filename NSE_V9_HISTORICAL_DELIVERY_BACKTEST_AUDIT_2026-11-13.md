# V9 Historical Delivery Backtest Audit — 2026-11-13

## Status and scope

- Research-only audit of workflow run `43476942945` and artifact `delivery-ab-historical-backtest-43476942945`.
- The backtest job completed successfully. This means the code ran and reports were produced; it does **not** validate profitability or production readiness.
- This document records findings and the next research plan. It does not change scanner production rules, ranking, Telegram, or order behaviour.
- Source PR: #93, research branch `research/delivery-5d-consistency-backtest-2026-11-13`.

## Cache coverage and integrity

| Item | Result |
|---|---:|
| Price cache files / dates | 201 / 201 |
| Price rows | 502,424 |
| Symbols | 2,996 |
| Price date range | 2026-01-16 to 2026-11-09 |
| Delivery cache files / dates | 203 / 203 |
| Delivery date range | 2026-01-19 to 2026-11-13 |
| Price / delivery file issues | 0 / 0 |
| Delivery reports backfilled for requested 200 price sessions | 200 valid; 1 downloaded, 199 reused; 0 missing/rejected |
| Network calls during backtest | No |
| Point-in-time fundamentals | Not backtested |

The backfill summary requested 200 price sessions from 2026-01-19 through 2026-11-09. The separate cache inventory contains 203 Delivery report dates through 2026-11-13.

## Existing A OR B cohort results

The signal rows already include the prior-20-official-session average traded-value liquidity gate of at least INR 1.5 crore. RVOL is descriptive only and is not a rejection gate.

| Cohort | Signal rows | 5D avg return | 10D avg return | 20D avg return | 20D win rate | 20D median | 20D PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| A OR B | 85,741 | +0.087% | +0.119% | +0.449% | 48.04% | -0.225% | 1.121 |
| A_ONLY | 476 | +0.239% | -1.153% | -1.878% | 36.14% | -2.413% | 0.618 |
| A_AND_B | 48,920 | +0.005% | +0.034% | +0.312% | 49.28% | 0.000% | 1.090 |
| B_ONLY | 36,345 | +0.196% | +0.251% | +0.666% | 46.50% | -0.750% | 1.166 |

20D observations are 76,352 for A OR B, 404 for A_ONLY, 43,815 for A_AND_B, and 32,133 for B_ONLY. Incomplete forward horizons are excluded from each horizon's metric.

## Exact latest-five Delivery consistency cohorts

These groups are subdivisions of the unchanged A OR B eligible signals. The 5D rule is observational only.

| Cohort | Signal rows | 5D avg return | 10D avg return | 20D avg return | 20D win rate | 20D median | 20D PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| HIGH (5/5 >=60%) | 7,376 | -0.321% | -0.373% | +0.082% | 53.46% | +0.341% | 1.033 |
| MODERATE (3–4/5) | 27,337 | +0.086% | +0.090% | +0.385% | 49.05% | 0.000% | 1.110 |
| LOW (0–2/5) | 51,028 | +0.148% | +0.208% | +0.541% | 46.66% | -0.696% | 1.135 |
| WAIT_FOR_DATA | 0 | n/a | n/a | n/a | n/a | n/a | n/a |

### Interpretation

1. The HIGH group does not show a convincing average-return advantage. LOW has the highest raw 20D average and profit factor among these three groups; HIGH has the highest 20D win rate but a much smaller average return.
2. Do not give HIGH consistency a positive ranking weight based on this test. Do not reject A OR B candidates just because they are LOW.
3. A_ONLY has weak 10D/20D results, but only 404 complete 20D observations. Treat it as a hypothesis for further testing, not a basis for changing the approved A/B gate.
4. A OR B's 20D mean is positive while its median is negative. This indicates skew/outlier sensitivity; the average alone is not a robust description of a typical signal.
5. All figures are gross research statistics, not executable trade returns.

## Important limitations / audit findings

- **Overlapping observations:** 85,741 rows are symbol-date signal observations, not independent trades. The same symbol can appear on consecutive dates and forward windows overlap. Standard win-rate/PF interpretation is therefore optimistic if treated as a portfolio record.
- **Entry price:** The report measures future close relative to the signal-day close. An EOD signal cannot generally be filled at that same close after the signal is known. A realistic simulation should use next official session Open as the entry reference (and label it a reference, not a guaranteed fill).
- **Exit/portfolio logic:** There is no 2–4 week portfolio simulation, no four-position cap, no capital allocation, no cash handling, and no explicit exit rule.
- **Costs:** Brokerage, taxes, exchange charges, slippage, spread, and market impact are absent. The small gross average returns may not survive costs.
- **Universe bias:** Historical cache is EQ-series only and uses current cache membership. Historical point-in-time Main Board/ETF classification is unavailable. This is not a complete point-in-time Main Board universe.
- **Fundamentals/news/sector:** Point-in-time fundamentals are not backtested. Existing fundamentals, news, sector and technical layers are not validated by these cohort statistics.
- **Forward completeness:** Horizon metrics exclude signals without every required future official-session price row. Coverage counts must always be shown next to performance metrics.
- **No forced conclusions:** A successful workflow, clean cache, and positive gross PF do not establish a profitable or production-ready strategy.

## Recommended V9 next phase (research-only)

### Phase 1 — Make the comparison statistically safer
1. Add non-overlapping signal episodes per symbol (define an episode start and reset/cooldown explicitly).
2. Report both all-signal observations and one-observation-per-symbol/episode metrics.
3. Add date-wise and symbol-wise sample coverage, and cohort breakdown by calendar quarter/month.
4. Include median, trimmed mean, win rate, profit factor, MFE/MAE, and complete-horizon counts together.

### Phase 2 — Simulate the actual strategy constraints
1. Use next official session Open as the research entry reference; never assume the signal-day close was fillable.
2. Simulate max 4 concurrent positions, total capital INR 1,00,000, and max INR 25,000 per position.
3. Define deterministic selection/ranking and tie-breaks from information available at signal time. Do not invent a ranking retrospectively.
4. Define exits before testing (time exit within 2–4 weeks, and any stop/exit logic only if explicitly approved).
5. Add conservative configurable costs and slippage; publish gross and net results separately.
6. Compare against simple baselines (e.g. liquidity-qualified universe and A/B without consistency weighting).

### Phase 3 — Robustness and leakage checks
1. Use chronological train/validation/test periods; avoid tuning and evaluating on the same period.
2. Check survivorship and point-in-time universe limitations; until resolved, label results as cache-universe research.
3. Test sensitivity to Delivery threshold, lookback, liquidity threshold, and entry/exit assumptions without selecting only the best-looking combination.
4. Add tests for missing sessions, duplicate symbol/date rows, future-data leakage, and next-open execution assumptions.

## Decisions now

- Keep the existing production A OR B eligibility rule unchanged.
- Keep the exact latest-five consistency field research-only; no ranking boost or hard rejection.
- Do not merge PR #93 into production until its code review and all evidence are complete.
- Do not claim a validated win rate, net expectancy, or net profit factor.
- The next implementation should be a separate research-only portfolio/episode backtest, reviewed in its own PR. No production files should be changed for that work.

## Artifact provenance

- GitHub Actions run: 43476942945
- Artifact: delivery-ab-historical-backtest-43476942945
- Artifact SHA-256 reported by GitHub: a3d9a5d6f631132ad5b775715e3dfcb1aa147a239087303b4f3c87d705e154a7
