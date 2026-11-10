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
| Institutional | `fii_dii_activity.py`; `outputs/v8_fii_dii_market_activity.csv` | Exact-date FII/FPI and DII aggregate cash-flow data with explicit `MARKET_WIDE_AGGREGATE_NOT_PER_STOCK` scope | Repository recursive tree and source inspection show no separate stock-specific bulk/block deals, shareholding, promoter pledge or insider/PIT/SAST evidence module; market-wide context only |
| News | `news_catalyst.py`; `data/inputs/news_evidence_auto.csv` | Symbol, PublishedAt, Headline, Source, SourceType, URL, Impact, EventID, SourceDomain; official/secondary distinction and issuer matching | Current 7-day requirement is not met (code explicitly uses five calendar dates); visible tracked tree has no dedicated durable news cache/history path, and schema lacks FirstSeenAt/LastCheckedAt/revision history |
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

## 7. Additional verified findings from workflow artifact and repository tree
- Fundamental history snapshots are tracked for 10 dates from 2026-10-28 through 2026-11-09. The scheduled workflow has regression tests asserting persistence of `fundamental_metrics.csv`, official filing cache and dated history snapshots. The 09-Nov run artifact also confirms historical Fundamentals are not point-in-time and cannot be claimed as a historical backtest.
- Fundamental metric verification in the 09-Nov artifact: 13 metric values marked OFFICIAL_XBRL_VERIFIED; 893 PROVIDER_ONLY; 18 PROVIDER_VALUE_MISMATCH; 2,643 DERIVED_RECONCILIATION_REQUIRED; 775 FILING_METADATA_NOT_CONFIRMED. These are metric-value rows, not unique-stock counts.
- The repository tree contains no dedicated stock-specific institutional activity module; `fii_dii_activity.py` is explicitly market-wide only.
- The tracked tree contains no dedicated durable News/Event cache or append-only event revision history path. News and upcoming-event outputs are generated under `data/inputs` / `outputs`, but persistent first-seen/revision lifecycle is not established by the inspected schema.

## 8. Phase 1 work still required
1. Complete a field-level audit of fundamental cache read/write and official verification paths; preserve existing functionality.
2. Define the new Track 2 research contract and full-Mainboard input/output schema.
3. Define append-only news/event cache and revision records without changing current source-matching rules.
4. Define stock-specific institutional evidence schema and official source audit.
5. Finalize versioned schema proposal and tests before implementing new producers/consumers.

## 9. Safety and compatibility checks
- No existing production thresholds, filters, scores or candidate membership changed.
- No new hard gate introduced.
- No secrets or credentials added.
- No production code or workflow changes made in this audit.
- All new research outputs must be isolated from Track 1 candidate selection.
