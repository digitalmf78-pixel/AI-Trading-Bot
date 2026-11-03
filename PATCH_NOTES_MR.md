# NSE V8 — XBRL FX cash-flow reconciliation + Q4 CFO audit integration

**Target base:** GitHub `main` commit `e6464c1` (from the uploaded 2026-11-03 Workflow log). Verify `main` has not advanced before applying.

## Why this patch is needed

### 1) SETCO consolidated cash-flow mismatch may be a false mismatch

The 2026-11-03 workflow's XBRL statement report shows the SETCO consolidated annual context:

- `CFO + CFI + CFF` (LeftValue): `212,200,000` INR
- `IncreaseDecreaseInCashAndCashEquivalents` (RightValue): `201,000,000` INR
- Difference: `11,200,000` INR

The current code compares the sum of operating, investing and financing cash flows directly to the **post-FX** net cash movement. The same parser already recognizes `IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges`, but the reconciliation did not use it, and it did not extract the exchange-rate effect fact.

Under the cash-flow statement structure, the correct two checks are:

1. `CFO + CFI + CFF = net cash movement BEFORE FX effects`
2. `net movement BEFORE FX + FX effect = net movement AFTER FX`

The 11,200,000 INR gap is therefore a **possible FX bridge**, not yet a confirmed FX amount. The workflow log does not include the raw pre-FX and FX-effect fact values, so this patch does not claim the SETCO discrepancy is resolved. It adds the correct checks so the next workflow run can confirm or reject that explanation from the actual XML facts.

### 2) Q4 CFO derivation must fail closed when 9M CFO is absent

The official NSE SETCO Q3 FY26 filing for 31-Dec-2025 identifies the 9M YTD period (01-Apr-2025 to 31-Dec-2025), but the page leaves the cash-flow-statement-applicable and cash-flow-type fields blank. The Q4 audit must therefore require an actual, unique 9M YTD CFO fact in the XML; otherwise it returns `WAIT_FOR_DATA` and must not calculate or promote a Q4 CFO value.

Official NSE filing page:
https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_142943_13022026170253_iXBRL_WEB.html

The existing `nse_xbrl_ytd_cashflow_reconciliation.py` is retained as an audit-only module. This patch adds it to the scheduled workflow, its compile check and its focused test batch. It does not write to the Fundamental Cache.

## Files included

- `nse_xbrl_statement_reconciliation.py` — separates pre-FX cash-flow cross-foot from post-FX bridge.
- `nse_xbrl_financial_fact_audit.py` — exposes the FX-effect fact as a candidate-only fact category.
- `tests/test_nse_xbrl_statement_reconciliation.py` — tests zero and non-zero FX bridges, including a synthetic SETCO-shaped 11.2m difference, and proves missing pre-FX data does not fall back to post-FX.
- `tests/test_nse_xbrl_financial_fact_audit.py` — checks FX-effect extraction remains candidate-only.
- `tests/test_nse_xbrl_ytd_cashflow_reconciliation.py` — adds a no-9M-CFO fail-closed test.
- `.github/workflows/nse-test-scheduled.yml` — adds the Q4 CFO audit step and its test/compile coverage.

## Safety boundaries

- No change to the Master Specification.
- No change to RVOL, Delivery A/B, liquidity, technical, or selection rules.
- No change to `fundamental_metrics.csv`, historical snapshots, or cache persistence.
- No financial fact is marked `VERIFIED` by these changes.
- Q4 CFO remains `DERIVED_CANDIDATE_ONLY_NOT_VERIFIED` only when both exact-period facts are present and all identity/basis/unit/taxonomy checks pass; otherwise `WAIT_FOR_DATA`.
- Q4 audit workflow step is `continue-on-error: true` and does not block the scanner.

## Local validation performed

- Mainboard tests: 3 passed
- Delivery / Liquidity / Fundamental / Pipeline tests: 97 passed
- XBRL / Q4 CFO / Fundamental verification focused tests: 62 passed
- V8 regression script: all 27 passed
- Python compile check: passed
- Workflow YAML parse: passed
- Full repository pytest suite: not run as a full-suite result is not claimed.

No GitHub push, merge, or deployment was performed as part of this patch creation.
