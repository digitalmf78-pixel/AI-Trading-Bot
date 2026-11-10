# NSE V8 P2 — Official XBRL Financial Fact Audit (2026-11-03)

> **Status update (2026-11-10):** This document records the initial candidate-extraction phase. The subsequent [P2 Statement Reconciliation Audit](README_P2_XBRL_STATEMENT_RECONCILIATION_2026-11-03.md) reconciled 55/55 arithmetic checks across the five supplied NSE XML samples and established that `CashFlowsFromUsedInOperatingActivities` (not the separate intermediate subtotal `CashFlowsFromUsedInOperations`) is the operating-cash-flow total that cross-foots with investing, financing, and pre-FX cash movement in those samples. The production verifier therefore now permits this annual direct fact only when the filing has an exact annual-aligned basis, matching official filing metadata, hash-verified XML/context/entity/period/unit/dimensions/value, and the same-context CFO + CFI + CFF cross-foot all pass. This is **not** blanket verification of provider values.
>
> The earlier statement below that the production direct-fact mapping table is empty is historical and superseded by that later reconciliation. Q4 standalone CFO remains unavailable in the five reviewed samples; no annual-minus-9M CFO derivation is permitted without verified 9M evidence.
>
> Latest persisted audit snapshot from the 2026-11-09 EOD run: 13 metric rows across 13 symbols were `OFFICIAL_XBRL_VERIFIED`; 18 OperatingCashFlowINR rows across 18 symbols were `PROVIDER_VALUE_MISMATCH`; 775 metric rows across 100 symbols lacked confirmed filing metadata; and 99 symbols had no exact official filing URL in the fetched NSE filing register. These remain visible audit states, not reasons to promote or silently rewrite cached values.

## Purpose

This patch adds a conservative extraction/audit stage for the official NSE XBRL XML samples already downloaded by `nse_xbrl_sample_diagnostic.py`.

It is deliberately **not** a Fundamental Provider integration. It creates a reviewable candidate-fact report without changing `fundamental_metrics.csv`, TTM values, Fundamental Score, or trading selection.

## Files in this patch

- `nse_xbrl_financial_fact_audit.py` — parses filing identity, context periods, entity identifiers, dimensions, unit, decimals, scale, sign, reporting-basis declarations, and selected financial fact candidates.
- `test_nse_xbrl_financial_fact_audit.py` — tests period classification, symbol/period mismatch, dimensions, scale/sign handling, and candidate-only status.
- `.github/workflows/nse-test-scheduled.yml` — compiles/tests the new parser, runs it after the existing XBRL sample diagnostic, and includes its outputs in the report artifact.

## Actual five-sample dry-run findings

The parser was run locally against the five raw XML files in report artifact `nse-v8-reports-41607525943.zip`:

| Symbol | XML symbol identity | Basis declaration | Q4 Revenue fact | Q4 Profit/Loss fact | Annual `CashFlowsFromUsedInOperations` | Annual `CashFlowsFromUsedInOperatingActivities` |
|---|---|---|---:|---:|---:|---:|
| SETCO | MATCH | Standalone | 2,900,000 | 837,500,000 | 29,899,000 | -5,048,000 |
| LAL | MATCH | Standalone | 257,598,000 | 8,727,000 | -117,489,000 | -140,004,000 |
| DONEAR | MATCH | Consolidated | 2,389,703,000 | 51,387,000 | 280,621,000 | 156,047,000 |
| DNAMEDIA | MATCH | Standalone | 16,249,000 | -60,237,000 | -16,388,000 | -19,010,000 |
| NIRAJ | MATCH | Standalone | 1,346,342,000 | 52,259,000 | -634,585,000 | -856,518,000 |

All listed facts above are raw candidate values in INR, not verified normalized metrics. The Q4 facts use the exact 2026-01-01 to 2026-03-31 duration context. The two cash-flow tags above occur in the 2025-04-01 to 2026-03-31 annual context in these samples.

The dry run extracted 97 candidate facts across five XMLs. All five XML symbols matched their expected symbols and all five filing URLs passed the NSE HTTPS host allow-list check. These five sample XMLs had no explicit or typed context dimensions. The parser supports extracting dimensions when present; their absence in these five samples is not a global claim about NSE filings.

## Historical candidate mapping status (superseded by the later statement reconciliation)

The samples contain both:
- `CashFlowsFromUsedInOperations`
- `CashFlowsFromUsedInOperatingActivities`

Their values differ. This patch intentionally labels both as candidates and does **not** select either as the definitive Operating Cash Flow metric. Taxonomy/statement-row semantics and cross-company reconciliation must be completed before choosing a production mapping.

At the time of this initial candidate-only patch, the production direct-fact mapping was intentionally empty. This status was superseded after the later five-filing statement-reconciliation audit selected `CashFlowsFromUsedInOperatingActivities` as the cross-footed annual operating-cash-flow total. The production verifier now uses that single tag under the strict hash/context/value and same-context cash-flow cross-foot checks described in the status update above. A matching hash/value/context alone cannot make an unapproved fact tag authoritative.

Likewise:
- `ProfitLossForPeriod` is extracted as a candidate net-profit fact.
- `RevenueFromOperations` is extracted as a candidate revenue fact.
- Context duration is classified only when exact calendar/fiscal boundaries match.
- `decimals` is retained as precision metadata; it is not used as a multiplier.
- Explicit `scale` and `sign` attributes are applied to the numeric candidate value.
- Publication date is carried from the existing source CSV/diagnostic metadata; this patch does not independently re-verify the filing publication timestamp or its EOD cutoff eligibility.

## Output files

After the scheduled/manual workflow run, the report artifact will contain:

- `outputs/xbrl_financial_fact_audit/xbrl_financial_fact_audit.json`
- `outputs/xbrl_financial_fact_audit/xbrl_financial_fact_candidates.csv`
- `outputs/xbrl_financial_fact_audit/xbrl_financial_fact_audit_summary.csv`

Every extracted fact is marked `CANDIDATE_ONLY_NOT_VERIFIED`.

## Safety and scope

- Does not write or update `data/inputs/fundamental_metrics.csv`.
- Does not calculate TTM or convert YTD into standalone quarters.
- Does not choose between the two Cash Flow tags.
- Does not mark any financial fact, metric, filing, or TTM result `VERIFIED`.
- Does not change `fundamental_data_provider.py`, Fundamental Score, RVOL, Delivery A/B, Liquidity, scanner behavior, cache refresh policy, or master specification.
- Diagnostic/audit workflow steps are non-blocking; inspect their reports rather than treating a green scanner run as proof of accounting verification.

## Validation performed against the uploaded source snapshot

- Focused regression tests: **67 passed**.
- Python compile checks: **54 files compiled successfully**.
- Workflow YAML parsed successfully.
- Real XML dry-run: **5/5 XML parsed**, **5/5 symbol identities matched**, **97 candidate facts extracted**.
- No live NSE network request was performed in the local dry-run; it used the XMLs already present in the uploaded GitHub Actions artifact.

## Apply instructions

The uploaded source ZIP does not contain `.git` metadata or a commit SHA. Before applying, compare these three patch files with the latest GitHub `main` branch and resolve any workflow edits rather than overwriting newer changes.

Files to add/update:
1. `nse_xbrl_financial_fact_audit.py` (new)
2. `test_nse_xbrl_financial_fact_audit.py` (new)
3. `.github/workflows/nse-test-scheduled.yml` (updated)

No push or deployment has been performed by this patch preparation.

