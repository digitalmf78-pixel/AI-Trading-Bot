# NSE V8.0 — Data Contract Audit
**Date:** 10-Nov-2026  
**Working branch:** audit/implementation-roadmap-2026-11-10  
**Source:** Master Implementation Log v1.1 (09-Nov-2026) and current main-branch source inspection  
**Scope:** Phase 1 — Data contracts and canonical schemas  
**Code changes:** None in this audit.

## 1. Core finding
The repository has useful module-specific CSV schemas, but it does not yet expose one consistent provenance/freshness/verification contract across Delivery, price/volume, Fundamentals, institutional evidence, News and Events. The schemas should be extended compatibly and independently; do not force a risky rewrite of existing Track 1 CSVs.

## 2. Existing data contracts found

| Domain | Existing file / output | Existing fields / behaviour | Gap against implementation log |
|---|---|---|---|
| Delivery quantity | `delivery_quantity_analysis.py`; `outputs/v8_delivery_quantity_observations_YYYYMMDD.csv` | Symbol, series, 5/10/20 session quantity totals/averages/first/last/change/slope; Delivery % average; traded-volume average; close first/last/change/range; dated quantity/%/volume/close values; as-of date, source dates, per-window status/reason | No Delivered Value field; 30/90/200 delivery windows are not part of this module; source/fetch/freshness metadata is not fully standardized |
| Price/volume | Bhavcopy history consumed by `potential_accumulation_analysis.py` and VCP modules | OHLCV, point-in-time history index, 20/50/100/200 rolling ranges, pivots, ATR, EMA20/44/50/200 and delivery/price response observations | Research output is currently called with the A/B candidate cohort, not an independent full Mainboard research cohort; no explicit Sideways/Dip result types yet |
| Fundamentals | `fundamental_data_provider.py`; `data/inputs/fundamental_metrics.csv`; `data/cache/fundamental_history/` | Symbol, as-of/retrieved time, source/URL, financial period, publication date/status, official filing URL/source, metric-period alignment, TTM audit, metrics and valuation timestamps/status | Broad field-level provenance already exists; audit still needed for cache history shape, official reconciliation and missing/stale per-field statuses |
| Institutional | `fii_dii_activity.py`; `outputs/v8_fii_dii_market_activity.csv` | Exact-date FII/FPI and DII aggregate cash-flow data with explicit `MARKET_WIDE_AGGREGATE_NOT_PER_STOCK` scope | This is market-wide context only. No stock-specific bulk/block deals, shareholding, promoter pledge or insider/PIT/SAST evidence engine was found in inspected modules |
| News | `news_catalyst.py`; `data/inputs/news_evidence_auto.csv` | Symbol, PublishedAt, Headline, Source, SourceType, URL, Impact, EventID, SourceDomain; official/secondary source distinction and issuer matching | Missing explicit FirstSeenAt/LastCheckedAt and durable revision/syndication history in the visible schema; current news window is 5 days, requested window is 7 |
| Events | `news_catalyst.py`; `outputs/v8_upcoming_corporate_events.csv` | EODDate, symbol, EventType, EventDate, AnnouncementDate, Headline, Source, SourceType, URL, Status, LookbackDays | Current 90-day announcement discovery lookback is not the requested next-20-calendar-day event horizon; no durable changed/cancelled/postponed event history in the visible output schema |
| Telegram | `build_marathi_digest` / `send_marathi_telegram` in `news_catalyst.py` | Current EOD/premarket digest, liquidity/fundamental pipeline summary, per-stock existing confirmation fields, 3500-character chunks, retries and Telegram acknowledgement logs | Required four-section ordering (Catalyst, Early Accumulation, Trade Ready, Negative/Risk Alerts) is not implemented as a distinct reporting contract |
| Watchlists | `hybrid_watchlists.py` | Four separate CSV outputs; status and reason; reports do not mutate candidate dataframe | Daily status snapshots/transitions and immutable prior status history require verification/implementation |

## 3. Track boundary finding — critical
The current EOD integration calls `build_potential_accumulation_report(current, ...)` after the Delivery A/B union is formed. Its module docstring and function contract say it processes A/B names. This does **not** meet the new research-log requirement to detect potential accumulation before the 60% Delivery A/B eligibility is achieved.

The Delivery Quantity observer is called on `delivery_audit` before the A/B union and may already have a broader cohort, but the exact cohort and source-session coverage must be verified from the complete scanner flow and actual run artifacts. Do not assume this makes the Sideways/Dip research track complete.

**Required design:** retain Track 1 exactly as-is; create a separately named Track 2 cohort and outputs sourced from the eligible Mainboard universe. Track 2 must never feed back into Track 1 membership or bypass its 60% A/B rules.

## 4. Canonical contract proposal (schema design only; not yet applied)
Use common metadata fields where applicable:
- Identity: `TckrSymb`, `CompanyName`, `Series`, `ISIN` (where source supplies it).
- Point-in-time: `AsOfDate`, `AsOfTimestampIST`, `SourcePublishedAt`, `FetchedAtUTC`, `FirstSeenAtUTC`, `LastCheckedAtUTC`.
- Provenance: `SourceType`, `SourceName`, `SourceURL`, `SourceRecordID`.
- Period: `WindowStart`, `WindowEnd`, `SessionCount`, `ReportingPeriodEnd`.
- Quality: `DataStatus`, `VerificationStatus`, `FreshnessStatus`, `CoverageStatus`, `Reason`.
- Revision/deduplication: `CanonicalEventID`, `DuplicateOf`, `RevisionNumber`, `PreviousEventDate`, `CurrentEventDate`, `EventChangeStatus`.

Do not populate fields with invented values. Where a source cannot supply a field, leave it empty and use a clear status.

## 5. Delivery / value calculation constraint
The inspected Delivery Quantity alias map has quantity, Delivery %, traded volume and closing price; it does not expose a direct delivered-value source field. If Delivered Value is derived as Delivered Quantity × a price, it must be labeled `ESTIMATED` and the exact price basis/date stored. A reliable official delivered-value field, if present in a source, should be preferred. Do not silently label a derived estimate as official.

## 6. News and event contract constraints
- News window: preceding 7 calendar days, using published timestamp in IST-aware point-in-time comparisons.
- Event horizon: next 20 calendar days, independent of the 90-day announcement discovery lookback.
- An announcement can be discovered within the 90-day lookback while its event is outside the next-20-day display horizon; preserve the distinction.
- An event with no explicit date remains `DATE_NOT_CONFIRMED`; never substitute announcement date.
- Event changes/cancellations/postponements need append-only history or equivalent revision records; do not overwrite old event facts.
- Duplicate detection must distinguish syndicated copies from a genuinely new issuer announcement.

## 7. Phase 1 work still required
1. Inspect complete EOD cohort construction to prove the Delivery Quantity input cohort.
2. Inspect fundamental cache write/read and official verification paths.
3. Inspect all available source files for stock-specific institutional disclosure coverage.
4. Inspect news/event collection windows and output/cache persistence end-to-end.
5. Inspect current workflow artifacts for actual schema columns and row coverage.
6. Finalize versioned schema proposal and tests before implementing new producers/consumers.

## 8. Safety and compatibility checks
- No existing production thresholds, filters, scores or candidate membership changed.
- No new hard gate introduced.
- No secrets or credentials added.
- No code or workflow changes made in this audit.
- All new research outputs must be isolated from Track 1 candidate selection.
