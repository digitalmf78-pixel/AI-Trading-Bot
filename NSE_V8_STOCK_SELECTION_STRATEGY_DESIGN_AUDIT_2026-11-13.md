# NSE V8 Stock Selection Strategy — Discussion Design & Current-Code Gap Audit

**Date:** 13-Nov-2026  
**Baseline:** `main` at `d12867b916a57cefeda3c1ec4d9dfaea219e8855`  
**Purpose:** Record the stock-selection framework discussed on 13-Nov-2026 and compare it with verified repository behavior before any scoring or signal implementation.

> **Status: DESIGN ONLY — NOT A PRODUCTION RULESET.** The proposed scores and thresholds below are discussion-approved starting points. They are not implemented, backtested, or authorized as hard scanner gates. Do not change the immutable Master Specification. Do not change Track 1 candidate membership or the existing Delivery/RVOL/Liquidity rules.

## 1. Non-negotiable architecture

### Track 1 — existing authoritative scanner
Keep the current production candidate flow and all approved rules unchanged:
- Official NSE Mainboard universe.
- Existing Delivery A/B logic and its 30-calendar-day / minimum-valid-report contract.
- RVOL is classification/information, not a rejection filter.
- Liquidity minimum ₹1.5 crore traded value.
- Fundamental enrichment must not silently remove candidates; missing values remain explicit.
- Existing WAIT_FOR_DATA fail-closed behavior, no Top-N cap, no synthetic 2R target.
- Existing risk controls and final EOD checks remain authoritative until separately audited.

### Track 2 — independent research and observation
Track 2 may study the full official Mainboard cohort before Delivery A/B eligibility, but it must never add, remove, qualify, reject, reorder, or feed signals back into Track 1. Every input symbol must remain represented; ambiguous identity or missing evidence is WAIT_FOR_DATA. No future data may enter an as-of EOD observation.

## 2. Proposed research scores (each component 0–100)

These are proposed descriptive scores, not entry gates.

### 2.1 Accumulation score — 100
| Component | Points |
|---|---:|
| Delivery % strength and consistency | 25 |
| Delivery Quantity trend | 20 |
| Volume behaviour | 20 |
| Price stability / price response | 15 |
| Up-day vs down-day volume context | 10 |
| Support / pivot-low context | 10 |
| **Total** | **100** |

Research labels: 80–100 Strong; 65–79 Moderate; 50–64 Early; below 50 Weak. A high Delivery % alone must never be described as proof of institutional accumulation or buyer identity.

### 2.2 VCP score — 100
| Component | Points |
|---|---:|
| Price contraction sequence | 25 |
| Volume dry-up | 20 |
| Higher lows | 15 |
| Tightness of price range | 15 |
| Consolidation near a defined pivot/resistance | 10 |
| Breakout volume confirmation | 15 |
| **Total** | **100** |

Research labels: 80–100 Strong; 65–79 Good; 50–64 Early; below 50 Weak. Early VCP observation may begin after two contraction steps; confirmed VCP requires at least three valid contraction steps and approved volume/price conditions. **Exact contraction depth, range expansion tolerance, base duration, pivot tolerance, and volume thresholds remain undefined and must be approved and validated before classification.** Until then retain NOT_CLASSIFIED / WAIT_FOR_DATA.

### 2.3 Trend score — 100
| Component | Points |
|---|---:|
| Close above EMA20 | 15 |
| Close above EMA44 | 15 |
| Close above EMA50 | 20 |
| Close above EMA200 | 20 |
| EMA20 above EMA50 | 10 |
| EMA50 above EMA200 | 10 |
| Positive EMA50 slope | 10 |
| **Total** | **100** |

EMA200-below names are not automatically rejected; they may be separately observed as developing/early trend. All EMA calculations require sufficient, valid, point-in-time price history.

### 2.4 Fundamental score — 100
| Component | Points |
|---|---:|
| Sales growth | 15 |
| Net profit growth | 15 |
| ROE | 10 |
| ROCE | 15 |
| Debt-to-equity | 10 |
| Operating cash flow | 15 |
| Profit margin | 10 |
| EPS growth / consistency | 10 |
| **Total** | **100** |

Prefer three-year context plus latest published quarterly results. Apply sector-specific treatment for banks/NBFCs; do not blindly apply industrial debt ratios. Provider-only, estimated, unreconciled, stale, or missing values must carry provenance/status and must not be presented as official verified facts.

### 2.5 Sector score — 100
| Component | Points |
|---|---:|
| Sector relative strength vs NIFTY 50 | 25 |
| Sector momentum (5D / 20D) | 20 |
| Sector volume growth | 15 |
| Sector breadth / number of strong constituents | 15 |
| Sector trend (EMA50 / EMA200) | 15 |
| Sector news / catalysts | 10 |
| **Total** | **100** |

Where an official sector index or valid constituent data is unavailable, show an explicit proxy/unavailable status; do not fabricate a score. News absence is not negative news.

## 3. Composite ranking proposal

| Score | Weight |
|---|---:|
| Accumulation | 25% |
| VCP | 25% |
| Trend | 20% |
| Fundamentals | 20% |
| Sector | 10% |
| **Total** | **100%** |

Proposed labels: 80–100 Excellent; 70–79 Strong; 60–69 Good; 50–59 Average; below 50 Weak.

**Missing-data rule:** Do not rescale partial component totals to 100 and do not silently impute zero or a neutral score. If a required component is incomplete, emit PARTIAL_DATA / WAIT_FOR_DATA with a completeness breakdown; only publish a composite score when its approved completeness contract is met. Keep raw component scores visible.

## 4. Entry observation taxonomy

Keep the following distinct:
1. WATCH — research observation only.
2. EARLY_ENTRY_WATCH — early setup, not a buy instruction.
3. BREAKOUT_CONFIRMED — price closes above a valid pivot/resistance with approved volume/close confirmation.
4. RETEST_CONFIRMED — prior breakout level is retested and holds with approved confirmation.

Early Entry, Breakout and Retest need separately approved, testable definitions. Existing production EOD watch/risk/mandatory-confirmation gates remain in force; this document does not replace them.

## 5. Risk management proposal

- Proposed default risk budget: 0.5% of verified account equity per trade.
- Proposed hard per-trade ceiling: 1%.
- Quantity = risk budget amount / (entry minus structural stop), subject to position, sector, portfolio, open-position and stop-distance limits.
- Structural stop must invalidate the setup; target levels must be actual identified resistance levels. No invented 2R target.
- Missing/stale account exposure, equity, open positions or sector exposure must fail closed.

These values must be reconciled against the existing private risk configuration and validated before changing any defaults. Never commit account-specific risk data to the public repository.

## 6. Market regime observation

Proposed regime labels: STRONG_BULLISH, BULLISH, SIDEWAYS, BEARISH, HIGH_VOLATILITY. Inputs to evaluate: NIFTY 50/500 trend, market breadth, advance/decline, India VIX, sector breadth and market participation. A weak market should alter risk context / watchlist priority, not delete otherwise eligible research names. Exact formula and source coverage are not yet approved.

## 7. Current repository implementation audit

| Area | Verified current state | Gap / safe next step |
|---|---|---|
| Mainboard + Delivery A/B + RVOL + Liquidity | Existing Track 1 rules are authoritative; leave unchanged | No strategy-score change to this flow |
| Delivery Quantity | `delivery_quantity_analysis.py` provides 5/10/20-session quantity, Delivery %, traded-volume and price observations | It is descriptive, not an accumulation score; full-Mainboard Track 2 path exists |
| Accumulation / price response | `potential_accumulation_analysis.py` provides 20/50/100/200 range observations, 3-left/3-right pivots, higher-low observations, high-delivery price response, selling-pressure context and EMA20/44/50/200 positions | No 100-point score or Strong/Moderate/Early classification; existing report must remain descriptive until definitions and tests are approved |
| VCP | `vcp_observation_analysis.py` measures three consecutive 20-session blocks, contraction ratios/depth, block volume ratios and <0.5x dry-up observation | Explicitly leaves VCPStatus NOT_CLASSIFIED; dry-up is observation only. No confirmed VCP score/classifier |
| Fixed-range base | Existing rolling 20/50/100/200 windows are not detected base boundaries | Start/end/duration/width rules remain unapproved; do not call rolling range a fixed base |
| Watchlists | `hybrid_watchlists.py` emits observation-only accumulation/base-VCP/breakout/entry lists; final entry candidate is tied to existing EOD, risk, mandatory-confirmation and chase states | Proposed labels must not bypass existing production gates |
| Fundamentals | `fundamental_data_provider.py` and persistent cache/history exist; data provenance and verification are mixed by field | Build a field-level verified/partial status matrix before scoring; no missing-data drops |
| Sector | `sector_data.py` maintains official sector constituents and daily index history | No verified 100-point composite sector score from the inspected code; build from dated official history with proxy status |
| Risk | `risk_controls.py` reads private account config and applies portfolio controls | 0.5% default must be checked against actual private config; do not change account settings or expose them |
| Market regime | No complete approved market-regime scoring contract established in this audit | Define exact benchmark, breadth, VIX and freshness formulas before implementation |
| Backtest/outcomes | Signal outcome tracking and historical Delivery backtest work are separate from the new proposed score | Validate score buckets and entry types on point-in-time data before selecting thresholds |

Supporting audits:
- `NSE_V8_FIXED_RANGE_BASE_VCP_IMPLEMENTATION_AUDIT_2026-11-11.md`
- `NSE_V8_DATA_CONTRACT_AUDIT_2026-11-10.md`
- `NSE_V8_TRACK2_FULL_MAINBOARD_ACCUMULATION_DESIGN_AUDIT_2026-11-10.md`

## 8. Validation plan before any production scoring

1. Freeze an as-of date and validate complete official NSE session coverage, duplicate rows, symbol/series identity, OHLCV integrity and no future rows.
2. Build descriptive component observations without changing Track 1.
3. Add score calculations only behind a separate research output namespace; preserve raw inputs, component reasons, provenance and completeness.
4. Compare 5D / 10D / 20D forward outcomes by component-score bucket and by Early / Breakout / Retest setup. Use point-in-time historical inputs only; exclude or separately label non-point-in-time Fundamentals.
5. Report win rate, average return, median return, MFE, MAE, stop-hit rate, sample size, missing-data rate, turnover/slippage assumptions and sector concentration. Do not optimize thresholds on the same sample used for final claims.
6. Compare against simple baselines (Delivery A/B only; A/B + Liquidity; existing production shortlist) and test out-of-sample / walk-forward periods.
7. Only after evidence and explicit approval, create a separate implementation PR with unit tests and Track 1 non-interference assertions.

## 9. Explicit non-goals / safeguards

- No Master Specification edit.
- No Track 1 filter, threshold, candidate membership, ordering or Buy Signal change.
- No new hard gate based on the proposed scores.
- No synthetic data, invented fundamentals, invented targets or guessed sector/index values.
- No auto-trading or order placement.
- No changes to Bhavcopy cache or Delivery rules as part of this design document.
- Any observer failure remains isolated from Track 1.

**Bottom line:** The repository already contains useful descriptive building blocks for Delivery Quantity, price/EMA/pivot observations, VCP contractions, sector history, watchlists and risk controls. The new 100-point scores, composite ranking, confirmed VCP rules and market-regime model are not yet implemented or validated. The safe next step is research-only scoring plus point-in-time backtesting, isolated from Track 1.
