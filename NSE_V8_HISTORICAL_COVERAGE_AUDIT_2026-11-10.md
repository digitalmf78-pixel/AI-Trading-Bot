# NSE V8.0 — Historical Coverage and EOD Artifact Audit
**Date:** 10-Nov-2026  
**Artifact:** GitHub Actions run `42774048772`, artifact `nse-v8-reports-42774048772`  
**Artifact head:** `b1505af3759dccd5131c0a3c51964946707a9cb9` (main)  
**Working branch:** `audit/implementation-roadmap-2026-11-10`

## 1. Cache coverage actually reported by the run
From `outputs/rsi_retest/cache_coverage.csv`:

| Dataset | Files/dates | Rows / symbols | Date range | Issues |
|---|---:|---:|---|---:|
| Bhavcopy / price cache | 201 files / 201 dates | 502,424 rows / 2,996 symbols | 2026-01-16 to 2026-11-09 | 0 |
| NSE Delivery cache | 21 files / 21 dates | Per-symbol coverage below | 2026-10-12 to 2026-11-09 | 0 |
| Historical Fundamentals | Not point-in-time | — | — | Explicitly marked unavailable for backtesting |

The audit reports `NetworkCallsMade=False`: this coverage check reused the existing cache. It does **not** prove that Delivery history exists for 90 or 200 sessions. It does prove 201 price/Bhavcopy sessions in this artifact.

The 21 Delivery dates include the special Sunday session 2026-11-08. Do not assume every calendar day is a trading session.

## 2. Full Mainboard Delivery Quantity coverage
The EOD artifact contains 2,588 unique rows in both:
- `outputs/v8_delivery_dual_category_audit.csv`
- `outputs/v8_delivery_quantity_observations_20261109.csv`

The quantity observer is applied to the full Delivery audit frame before A/B union. This confirms that raw 5/10/20 Delivery Quantity observations are available for the whole 2,588-symbol Mainboard candidate cohort, not only the 758 A/B names.

| Window | COMPLETE | WAIT_FOR_DATA | Complete coverage |
|---|---:|---:|---:|
| 5 report sessions | 2,352 | 236 | 90.88% |
| 10 report sessions | 2,302 | 286 | 88.95% |
| 20 report sessions | 2,253 | 335 | 87.06% |

For 20-session delivery history, 2,253 of 2,588 symbols have complete data. The rest must remain WAIT_FOR_DATA for calculations that require all 20 sessions. No fallback to fewer sessions is authorized.

## 3. Important distinction: Delivery observer vs Early Accumulation engine
- Delivery Quantity observer: full 2,588-symbol audit cohort, pre-A/B.
- Potential Accumulation / price-response report: 758-symbol A/B union only.
- Existing Potential Accumulation Watchlist: all 758 are labelled `ACCUMULATION_WATCH`; this is an observation/watch state, not a measured Sideways or Dip classification.
- Existing potential-accumulation report: 671 rows have `COMPLETE_20D` price history; 87 are `WAIT_FOR_DATA`.
- Existing Base/VCP watchlist: `BASE_FORMING=68`, `NO_SETUP=432`, `WAIT_FOR_DATA=258`.
- Existing Breakout Ready watchlist: `ENTRY_CANDIDATE=26`, `NO_SETUP=15`, `CHASED=6`, `WAIT_FOR_DATA=5`, `BREAKOUT_CONFIRMED=1`, `PULLBACK_CONFIRMED=1`.
- Existing Confirmed Entry watchlist: `WAIT_FOR_DATA=29`, `NO_SETUP=19`, `CHASED=6`.

**Track 2 gap remains:** use the full eligible Mainboard cohort to create separate SIDEWAYS_ACCUMULATION and DIP_ACCUMULATION observations. Do not change Track 1's Delivery A/B selection.

## 4. News and Upcoming Events artifact checks
From `data/inputs/news_evidence_auto.csv`:
- 293 matched news rows across 48 symbols.
- Source types: 74 primary and 219 secondary.
- Published timestamp range in the artifact: 2026-11-04 18:51:18 UTC to 2026-11-09 15:59:03 UTC.
- Visible schema: `TckrSymb, PublishedAt, Headline, Source, SourceType, URL, Impact, EventID, SourceDomain`.
- No exact duplicate rows by `TckrSymb + PublishedAt + Headline` in this artifact.

The current code reports a 5-calendar-day news window; requested target is 7 calendar days. This needs a tested window-boundary change in the dedicated News phase, not an unrelated rewrite.

From `outputs/v8_upcoming_corporate_events.csv`:
- 246 rows total.
- `OFFICIAL_DATE_CONFIRMED=6`
- `DATE_NOT_FOUND_OR_NO_FUTURE_DATE=232`
- `NO_MATCHING_UPCOMING_EVENT_FOUND=8`
- Four of the six explicitly dated events fall within the next 20 calendar days after 2026-11-09.
- Two confirmed-date rows are far outside the next-20-day horizon (2027-07-01 and 2029-02-16, both from an ICICIBANK “Outcome of Board Meeting” headline). They must not be displayed as next-20-day opportunities; preserve source facts and investigate the date extraction context before classifying them as active events.

The current event report's 90-day announcement lookback is not itself a next-20-day event filter. Keep discovery lookback and event horizon separate.

## 5. Fundamentals and Institutional evidence
- Fundamental report: 54 candidate rows; COMPLETE=31 and PARTIAL_DATA=23.
- Metric verification summary: OFFICIAL_XBRL_VERIFIED=13 metric values across 13 symbols; PROVIDER_ONLY=893 values across 332 symbols; PROVIDER_VALUE_MISMATCH=18 values across 18 symbols; DERIVED_RECONCILIATION_REQUIRED=2,643 values across 475 symbols; FILING_METADATA_NOT_CONFIRMED=775 values across 100 symbols.
- Filing metadata summary: 475 symbols matched official filing metadata; 99 symbols had filing URL missing; 1 row had no exact-match filing.
- Market-wide FII/FPI and DII report is explicitly scoped `MARKET_WIDE_AGGREGATE_NOT_PER_STOCK`. It is not stock-specific institutional evidence.
- Cache coverage report says historical Fundamentals are not point-in-time; do not claim a valid historical fundamental backtest from this artifact.

## 6. Phase 2 conclusion
1. Price/Bhavcopy history is 201 sessions and supports 200-session price observations for symbols with complete rows.
2. Delivery report history is only 21 sessions in this artifact. 5/10/20 session data is available with the coverage rates above; 30/90/200 report-session Delivery history is not demonstrated.
3. No network calls were made by the cache-coverage audit.
4. Early Accumulation must be split into a full-Mainboard research cohort and the existing A/B candidate watchlist.
5. News and Events have explicit 7-day and next-20-day gaps; event date extraction also needs out-of-horizon handling.
6. Institutional stock-specific evidence is a separate missing module; market-wide FII/DII is already present but correctly segregated.

## 7. No production changes
This report is based on the downloaded EOD artifact only. No source code, thresholds, production workflow, Master Specification or main branch was changed. This audit branch contains documentation only.
