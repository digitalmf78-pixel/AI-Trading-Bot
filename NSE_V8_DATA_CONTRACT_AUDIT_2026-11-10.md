# NSE V8.0 — Data Contract Audit
**Date:** 10-Nov-2026  
**Working branch:** audit/implementation-roadmap-2026-11-10  
**Source:** Master Implementation Log v1.1 (09-Nov-2026) and current main-branch source inspection  
**Scope:** Phase 1 — Data contracts and canonical schemas  
**Code changes:** None in this audit.

## 1. Core finding
The repository has useful module-specific CSV schemas, but it does not yet expose one consistent provenance/freshness/verification contract across Delivery, price/volume, Fundamentals, institutional evidence, News and Events. Extend schemas compatibly; do not force a risky rewrite of existing Track 1 CSVs.

## 2. Existing data contracts found

| Domain | Existing file / output | Existing fields / behaviour | Gap against implementation log |
|---|---|---|---|
| Delivery quantity | `delivery_quantity_analysis.py`; `outputs/v8_delivery_quantity_observations_YYYYMMDD.csv` | Symbol, series, 5/10/20 session quantity totals/averages/first/last/change/slope; Delivery % average; traded-volume average; close first/last/change/range; dated quantity/%/volume/close values; as-of date, source dates, per-window status/reason | No Delivered Value field; 30/90/200 delivery windows are not part of this module; source/fetch/freshness metadata is not fully standardized |
| Price/volume | Bhavcopy history consumed by `potential_accumulation_analysis.py` and VCP modules | OHLCV, point-in-time history index, 20/50/100/200 rolling ranges, pivots, ATR, EMA20/44/50/200 and delivery/price response observations | Potential Accumulation report is called with the A/B union, not an independent full Mainboard research cohort; no explicit Sideways/Dip result types yet |
| Fundamentals | `fundamental_data_provider.py`; `data/inputs/fundamental_metrics.csv`; `data/cache/fundamental_history/` | Symbol, as-of/retrieved time, source/URL, financial period, publication date/status, official filing URL/source, metric-period alignment, TTM audit, metrics and valuation timestamps/status | Broad provenance metadata exists; audit still needed for cache history shape, official reconciliation and per-field freshness/status |
| Institutional | `fii_dii_activity.py`; `outputs/v8_fii_dii_market_activity.csv` | Exact-date FII/FPI and DII aggregate cash-flow data with explicit `MARKET_WIDE_AGGREGATE_NOT_PER_STOCK` scope | Market-wide context only. No stock-specific bulk/block deals, shareholding, promoter pledge or insider/PIT/SAST evidence engine found in inspected modules |
| News | `news_catalyst.py`; `data/inputs/news_evidence_auto.csv` | Symbol, PublishedAt, Headline, Source, SourceType, URL, Impact, EventID, SourceDomain; official/secondary distinction and issuer matching | Visible schema lacks explicit FirstSeenAt/LastCheckedAt and durable revision/syndication history; current window is 5 calendar days, requested window is 7 |
| Events | `news_catalyst.py`; `outputs/v8_upcoming_corporate_events.csv` | EODDate, symbol, EventType, EventDate, AnnouncementDate, Headline, Source, SourceType, URL, Status, LookbackDays | Current 90-day announcement discovery lookback is not the requested next-20-calendar-day event horizon; no durable changed/cancelled/postponed event history in visible output schema |
| Telegram | `build_marathi_digest` / `send_marathi_telegram` in `news_catalyst.py` | Current EOD/premarket digest, liquidity/fundamental summary, per-stock existing confirmation fields, 3500-character chunks, retries and Telegram acknowledgement logs | Required four-section ordering (Catalyst, Early Accumulation, Trade Ready, Negative/Risk Alerts) is not implemented as a distinct reporting contract |
| Watchlists | `hybrid_watchlists.py` | Four separate CSV outputs; status and reason; reports do not mutate candidate dataframe | Daily status snapshots/transitions and immutable prior status history require verification/implementation |

## 3. Track boundary finding — critical and now verified
The full scanner flow shows:
1. `current` is first filtered to the official Mainboard universe.
2. `apply_delivery_filter(current, ...)` returns a filtered Delivery-qualified frame **and a full audit frame**. The implementation builds the audit by iterating over the entire supplied candidate dataframe, then returns `output, audit`.
3. `build_delivery_quantity_report(delivery_audit, ...)` is called before the A/B union. Therefore the existing Delivery Quantity observer already receives the full Mainboard audit cohort (including A/B WAIT/reject rows), subject to the fetched Delivery session coverage.
4. Later, `build_potential_accumulation_report(current, ...)` is called only after the A/B union and RVOL classification. Its function contract says it creates observations for A/B names.

**Conclusion:** raw quantity observations have a full-Mainboard cohort path, but the current Potential Accumulation / price-response engine is A/B-union-only. It does not yet meet the approved Track 2 objective to detect early accumulation before 60% A/B eligibility.

**Required design:** retain Track 1 exactly as-is; build a separately named Track 2 research cohort/output from the full eligible Mainboard universe, reusing existing `delivery_audit`, Delivery sessions and Bhavcopy history where valid. Track 2 must never feed back into Track 1 membership or bypass its 60% A/B rules.

## 4. Canonical contract proposal (schema design only; not yet applied)
Use common metadata fields where applicable:
- Identity: `TckrSymb`, `CompanyName`, `Series`, `ISIN` (only where source supplies it).
- Point-in-time: `AsOfDate`, `AsOfTimestampIST`, `SourcePublishedAt`, `FetchedAtUTC`, `FirstSeenAtUTC`, `LastCheckedAtUTC`.
- Provenance: `SourceType`, `SourceName`, `SourceURL`, `SourceRecordID`.
- Period: `WindowStart`, `WindowEnd`, `SessionCount`, `ReportingPeriodEnd`.
- Quality: `DataStatus`, `VerificationStatus`, `FreshnessStatus`, `CoverageStatus`, `Reason`.
- Revision/deduplication: `CanonicalEventID`, `DuplicateOf`, `RevisionNumber`, `PreviousEventDate`, `CurrentEventDate`, `EventChangeStatus`.

Do not populate fields with invented values. Where a source cannot supply a field, leave it empty and use a clear status.

## 5. Delivery / value calculation constraint
The inspected Delivery Quantity alias map has quantity, Delivery %, traded volume and closing price; it does not expose a direct delivered-value source field. If Delivered Value is derived as Delivered Quantity × a price, label it `ESTIMATED` and store the exact price basis/date. Prefer a reliable official delivered-value field if present. Never silently label a derived estimate as official.

## 6. News and event contract constraints
- News window: preceding 7 calendar days, using published timestamp in IST-aware point-in-time comparisons.
- Event horizon: next 20 calendar days, independent of the 90-day announcement discovery lookback.
- An announcement discovered within the 90-day lookback may describe an event outside the next-20-day display horizon; preserve that distinction.
- An event with no explicit date remains `DATE_NOT_CONFIRMED`; never substitute announcement date.
- Event changes/cancellations/postponements need append-only history or equivalent revision records; do not overwrite old event facts.
- Duplicate detection must distinguish syndicated copies from a genuinely new issuer announcement.

## 7. Phase 1 work still required
1. Inspect fundamental cache write/read and official verification paths end-to-end.
2. Inspect all repository source files for stock-specific institutional disclosure coverage.
3. Inspect news/event collection windows and output/cache persistence end-to-end.
4. Inspect current workflow artifacts for actual schema columns and row coverage.
5. Measure actual Delivery report and Bhavcopy history coverage for 5/10/20/30/90/200 sessions.
6. Finalize versioned schema proposal and tests before implementing new producers/consumers.

## 8. Safety and compatibility checks
- No existing production thresholds, filters, scores or candidate membership changed.
- No new hard gate introduced.
- No secrets or credentials added.
- No production code or workflow changes made in this audit.
- All new research outputs must be isolated from Track 1 candidate selection.
