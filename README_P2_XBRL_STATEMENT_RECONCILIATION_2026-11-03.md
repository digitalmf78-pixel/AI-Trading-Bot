# P2 – NSE XBRL Statement Reconciliation Audit (2026-11-03)

## Scope

This patch adds a read-only audit layer after the existing official NSE XBRL sample download and candidate extraction steps. It checks arithmetic relationships inside the submitted XBRL financial statements. It does **not** change `fundamental_metrics.csv`, the Fundamental Provider, TTM calculations, Fundamental Score, scanner selection, liquidity, RVOL, Delivery A/B, risk controls, or the master specification.

## Findings from the five supplied official NSE XML samples

The report artifact for run `41610810465` contains five XML samples: SETCO, LAL, DONEAR, DNAMEDIA, and NIRAJ. All five XML documents parse, their reported symbols match the selected symbols, and each has a Q4 (`2026-01-01` to `2026-03-31`) and FY (`2025-04-01` to `2026-03-31`) income-statement context.

The following checks were run against the actual XML facts, preserving the filing's unit, decimals, scale, sign, context, dimensions, namespace, and reporting-basis declaration:

- `Income = RevenueFromOperations + OtherIncome`
- `ProfitBeforeTax = ProfitBeforeExceptionalItemsAndTax + ExceptionalItemsBeforeTax`
- `TaxExpense = CurrentTax + DeferredTax`
- `ProfitLossForPeriodFromContinuingOperations = ProfitBeforeTax - TaxExpense`
- `ProfitLossForPeriod = continuing profit + discontinued-operation after-tax result + share of profit/loss of associates and joint ventures`
- `CashFlowsFromUsedInOperatingActivities + CashFlowsFromUsedInInvestingActivities + CashFlowsFromUsedInFinancingActivities = IncreaseDecreaseInCashAndCashEquivalents`

Results on these five samples: **55 of 55 arithmetic checks passed within the XBRL-reported rounding precision**. DONEAR's total-profit reconciliation required including the separately reported share of profit/loss of associates and joint ventures; omitting this line produced a false mismatch, so the audit explicitly includes it.

## Cash-flow interpretation supported by the samples

For all five samples, `CashFlowsFromUsedInOperatingActivities` is the value that cross-foots with investing cash flow, financing cash flow, and the reported net change in cash. `CashFlowsFromUsedInOperations` is a separate intermediate subtotal and must not be substituted for the net operating cash-flow total.

All five samples contain the operating-cash-flow fact only in the FY context (`2025-04-01` to `2026-03-31`). **No Q4 standalone operating-cash-flow fact is present in these five XML samples.** The script does not derive Q4 cash flow from annual values. A verified nine-month comparison fact or other explicit source is required before any annual-minus-YTD conversion can be considered.

## Important anomaly retained for manual review

DNAMEDIA has `NetProfitAfterTax` facts in two dimensioned contexts (`AuditedMember` and `AdjustedMember`) with no standalone/consolidated declaration attached to those contexts. These facts conflict with the undimensioned Q4 `ProfitLossForPeriod` fact. The new audit preserves dimensions and does not select either `NetProfitAfterTax` fact as canonical.

## Additional conflict surfaced

DNAMEDIA reports two `NetProfitAfterTax` facts in dimensioned `D_Audited` and `D_Adjusted` contexts (both INR 88,754,000), while the undimensioned Q4 `ProfitLossForPeriod` is INR -60,237,000. Those dimensioned contexts do not carry the filing's `NatureOfReportStandaloneConsolidated` declaration. The audit emits `DIMENSIONED_NET_PROFIT_AFTER_TAX_CONFLICT` and deliberately selects neither figure.

## Outputs

The workflow writes:

- `outputs/xbrl_statement_reconciliation/xbrl_statement_reconciliation.json`
- `outputs/xbrl_statement_reconciliation/xbrl_statement_reconciliation_summary.csv`
- `outputs/xbrl_statement_reconciliation/xbrl_statement_reconciliation_checks.csv`
- `outputs/xbrl_statement_reconciliation/xbrl_statement_facts.csv`
- `outputs/xbrl_statement_reconciliation/xbrl_statement_contexts.csv`
- `outputs/xbrl_statement_reconciliation/xbrl_statement_anomalies.csv`

## Safety and verification status

All extracted facts remain `CANDIDATE_ONLY_NOT_VERIFIED`. Arithmetic consistency is supporting evidence, not proof of taxonomy correctness, publication-date eligibility, source-period alignment, or accounting verification. No values are written back into the Fundamental Cache. The workflow step is non-blocking for the scanner and must be reviewed independently; a green workflow is not proof that the XBRL facts are verified.

## Local validation against supplied source and report artifact

- Actual five-XML reconciliation: 5/5 XML audited, 55/55 checks passed within XBRL precision, 0 arithmetic mismatches.
- Actual sample anomalies: two dimensioned DNAMEDIA `NetProfitAfterTax` conflicts; no other conflicts emitted by this audit's defined checks.
- Quarterly operating cash flow: absent in all five sampled filings; annual CFO cross-foot succeeds in all five.
- New focused tests: 6 passed (statement reconciliation plus existing XBRL financial audit tests).
- Broader pytest selection: 114 passed.
- Existing V8 regression script: 27 checks passed.
- Existing sector/news/cache unittest group: 39 tests passed.
- Python compile: 56 files passed.
- Workflow YAML parsed successfully.

These are local results against the user-supplied source snapshot and report artifact. The patch has not been pushed to GitHub or run in GitHub Actions.
