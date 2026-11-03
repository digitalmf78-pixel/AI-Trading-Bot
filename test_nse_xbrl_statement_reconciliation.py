from pathlib import Path

from nse_xbrl_statement_reconciliation import inspect_statement


def _xml(path: Path):
    path.write_text('''<?xml version="1.0"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:g="urn:sebi:test">
 <context id="Q4"><entity><identifier scheme="urn:scrip">123</identifier></entity><period><startDate>2026-01-01</startDate><endDate>2026-03-31</endDate></period></context>
 <context id="FY"><entity><identifier scheme="urn:scrip">123</identifier></entity><period><startDate>2025-04-01</startDate><endDate>2026-03-31</endDate></period></context>
 <context id="Q4_DIM"><entity><identifier scheme="urn:scrip">123</identifier><segment><explicitMember dimension="g:AuditAxis">g:AuditedMember</explicitMember></segment></entity><period><startDate>2026-01-01</startDate><endDate>2026-03-31</endDate></period></context>
 <unit id="INR"><measure>iso4217:INR</measure></unit>
 <g:Symbol contextRef="Q4">TEST</g:Symbol><g:NatureOfReportStandaloneConsolidated contextRef="Q4">Standalone</g:NatureOfReportStandaloneConsolidated>
 <g:NatureOfReportStandaloneConsolidated contextRef="FY">Standalone</g:NatureOfReportStandaloneConsolidated>
 <g:RevenueFromOperations contextRef="Q4" unitRef="INR" decimals="-3">1000</g:RevenueFromOperations>
 <g:OtherIncome contextRef="Q4" unitRef="INR" decimals="-3">200</g:OtherIncome>
 <g:Income contextRef="Q4" unitRef="INR" decimals="-3">1200</g:Income>
 <g:ProfitBeforeExceptionalItemsAndTax contextRef="Q4" unitRef="INR" decimals="-3">500</g:ProfitBeforeExceptionalItemsAndTax>
 <g:ExceptionalItemsBeforeTax contextRef="Q4" unitRef="INR" decimals="-3">100</g:ExceptionalItemsBeforeTax>
 <g:ProfitBeforeTax contextRef="Q4" unitRef="INR" decimals="-3">600</g:ProfitBeforeTax>
 <g:TaxExpense contextRef="Q4" unitRef="INR" decimals="-3">100</g:TaxExpense>
 <g:ProfitLossForPeriodFromContinuingOperations contextRef="Q4" unitRef="INR" decimals="-3">500</g:ProfitLossForPeriodFromContinuingOperations>
 <g:ProfitLossForPeriod contextRef="Q4" unitRef="INR" decimals="-3">500</g:ProfitLossForPeriod>
 <g:ProfitLossFromDiscontinuedOperationsAfterTax contextRef="Q4" unitRef="INR" decimals="-3">0</g:ProfitLossFromDiscontinuedOperationsAfterTax>
 <g:ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod contextRef="Q4" unitRef="INR" decimals="-3">0</g:ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod>
 <g:NetProfitAfterTax contextRef="Q4_DIM" unitRef="INR" decimals="-3">900</g:NetProfitAfterTax>
 <g:CurrentTax contextRef="Q4" unitRef="INR" decimals="-3">100</g:CurrentTax>
 <g:DeferredTax contextRef="Q4" unitRef="INR" decimals="-3">0</g:DeferredTax>
 <g:CashFlowsFromUsedInOperations contextRef="FY" unitRef="INR" decimals="-3">900</g:CashFlowsFromUsedInOperations>
 <g:CashFlowsFromUsedInOperatingActivities contextRef="FY" unitRef="INR" decimals="-3">700</g:CashFlowsFromUsedInOperatingActivities>
 <g:CashFlowsFromUsedInInvestingActivities contextRef="FY" unitRef="INR" decimals="-3">-200</g:CashFlowsFromUsedInInvestingActivities>
 <g:CashFlowsFromUsedInFinancingActivities contextRef="FY" unitRef="INR" decimals="-3">-100</g:CashFlowsFromUsedInFinancingActivities>
 <g:IncreaseDecreaseInCashAndCashEquivalents contextRef="FY" unitRef="INR" decimals="-3">400</g:IncreaseDecreaseInCashAndCashEquivalents>
</xbrl>''', encoding="utf-8")


def test_statement_reconciliation_and_quarterly_cashflow_absence(tmp_path):
    path = tmp_path / "sample.xml"
    _xml(path)
    result = inspect_statement(path, symbol="TEST")
    checks = {row["Check"]: row for row in result["ReconciliationChecks"]}
    assert checks["INCOME_EQUALS_REVENUE_PLUS_OTHER_INCOME"]["Status"] == "PASS_WITHIN_XBRL_ROUNDING"
    assert checks["PBT_EQUALS_PRE_EXCEPTIONAL_PLUS_EXCEPTIONAL"]["Status"] == "PASS_WITHIN_XBRL_ROUNDING"
    assert checks["CONTINUING_PROFIT_EQUALS_PBT_LESS_TAX"]["Status"] == "PASS_WITHIN_XBRL_ROUNDING"
    assert checks["TOTAL_PROFIT_EQUALS_CONTINUING_PLUS_DISCONTINUED_PLUS_ASSOCIATES"]["Status"] == "PASS_WITHIN_XBRL_ROUNDING"
    assert checks["TAX_EXPENSE_EQUALS_CURRENT_PLUS_DEFERRED"]["Status"] == "PASS_WITHIN_XBRL_ROUNDING"
    assert checks["CFO_PLUS_CFI_PLUS_CFF_EQUALS_NET_CASH_CHANGE"]["Status"] == "PASS_WITHIN_XBRL_ROUNDING"
    assert result["QuarterlyOperatingCashFlowAvailability"] == "NO_Q4_CFO_FACT_IN_SAMPLE"
    assert result["AnnualOperatingCashFlowContexts"] == ["FY"]
    assert result["CFOArithmeticEvidence"] == "ANNUAL_CFO_TAG_RECONCILES_TO_NET_CASH_CHANGE"
    assert result["Anomalies"][0]["Code"] == "DIMENSIONED_NET_PROFIT_AFTER_TAX_CONFLICT"
    assert result["Anomalies"][0]["Status"] == "REQUIRES_DIMENSIONAL_AND_STATEMENT_RECONCILIATION"
    assert all(f["VerificationStatus"] == "CANDIDATE_ONLY_NOT_VERIFIED" for f in result["Facts"])


def test_unknown_identity_does_not_get_promoted(tmp_path):
    path = tmp_path / "sample.xml"
    _xml(path)
    result = inspect_statement(path, symbol="OTHER")
    assert result["IdentityStatus"] == "IDENTITY_NOT_CONFIRMED"
    assert result["QuarterlyOperatingCashFlowAvailability"] == "NO_Q4_CFO_FACT_IN_SAMPLE"
