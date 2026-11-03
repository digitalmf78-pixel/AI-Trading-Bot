from pathlib import Path

from nse_xbrl_financial_fact_audit import inspect_filing, _period_class


def _write_xml(path: Path):
    path.write_text("""<?xml version="1.0"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrli="http://www.xbrl.org/2003/instance"
      xmlns:in-gaap="http://example.com/gaap">
  <context id="Q4">
    <entity>
      <identifier scheme="http://www.sebi.gov.in/in-capmkt/ScripCode">505075</identifier>
      <segment><explicitMember dimension="in-gaap:BusinessSegmentsAxis">in-gaap:TextilesMember</explicitMember></segment>
    </entity>
    <period><startDate>2026-01-01</startDate><endDate>2026-03-31</endDate></period>
  </context>
  <context id="FY">
    <entity><identifier scheme="http://www.sebi.gov.in/in-capmkt/ScripCode">505075</identifier></entity>
    <period><startDate>2025-04-01</startDate><endDate>2026-03-31</endDate></period>
  </context>
  <unit id="INR"><measure>iso4217:INR</measure></unit>
  <in-gaap:Symbol contextRef="Q4">SETCO</in-gaap:Symbol>
  <in-gaap:ScripCode contextRef="Q4">505075</in-gaap:ScripCode>
  <in-gaap:NatureOfReportStandaloneConsolidated contextRef="Q4">Standalone</in-gaap:NatureOfReportStandaloneConsolidated>
  <in-gaap:NatureOfReportStandaloneConsolidated contextRef="FY">Standalone</in-gaap:NatureOfReportStandaloneConsolidated>
  <in-gaap:RevenueFromOperations contextRef="Q4" unitRef="INR" decimals="-3">2900000</in-gaap:RevenueFromOperations>
  <in-gaap:ProfitLossForPeriod contextRef="Q4" unitRef="INR" decimals="-3">837500000</in-gaap:ProfitLossForPeriod>
  <in-gaap:CashFlowsFromUsedInOperatingActivities contextRef="FY" unitRef="INR" decimals="-3">5048000</in-gaap:CashFlowsFromUsedInOperatingActivities>
</xbrl>
""", encoding="utf-8")


def test_extracts_symbol_basis_quarter_and_annual_cashflow_as_candidates(tmp_path):
    path = tmp_path / "sample.xml"
    _write_xml(path)
    result = inspect_filing(
        path, expected_symbol="SETCO", expected_period_end="2026-03-31",
        official_filing_url="https://nsearchives.nseindia.com/sample.xml",
        publication_date="2026-05-01",
    )
    assert result["FilingIdentityStatus"] == "MATCH"
    assert result["XMLSymbols"] == ["SETCO"]
    by_tag = {(x["FactTag"], x["ContextRef"]): x for x in result["Facts"]}
    revenue = by_tag[("RevenueFromOperations", "Q4")]
    assert revenue["PeriodClass"] == "QUARTERLY_3M_CANDIDATE"
    assert revenue["ReportingBasis"] == "STANDALONE"
    assert revenue["ParsedNumericValue"] == "2900000"
    assert revenue["HasDimensions"] is True
    cash = by_tag[("CashFlowsFromUsedInOperatingActivities", "FY")]
    assert cash["PeriodClass"] == "ANNUAL_12M_CANDIDATE"
    assert cash["ReportingBasis"] == "STANDALONE"
    assert cash["FactVerificationStatus"] == "CANDIDATE_ONLY_NOT_VERIFIED"


def test_period_classification_is_fail_closed():
    assert _period_class({"startdate": "2026-01-01", "enddate": "2026-03-31"})[0] == "QUARTERLY_3M_CANDIDATE"
    assert _period_class({"startdate": "2025-04-01", "enddate": "2026-03-31"})[0] == "ANNUAL_12M_CANDIDATE"
    assert _period_class({"startdate": "2025-04-01", "enddate": "2025-12-31"})[0] == "YTD_9M_CANDIDATE"
    assert _period_class({"startdate": "2026-02-01", "enddate": "2026-04-30"})[0] == "OTHER_DURATION"
    assert _period_class({"instant": "2026-03-31"})[0] == "INSTANT"
    assert _period_class({"startdate": "bad", "enddate": "2026-03-31"})[0] == "UNKNOWN_PERIOD"


def test_symbol_and_period_mismatch_are_visible(tmp_path):
    path = tmp_path / "sample.xml"
    _write_xml(path)
    result = inspect_filing(path, expected_symbol="OTHER", expected_period_end="2025-03-31")
    assert "SYMBOL_MISMATCH" in result["FilingIdentityStatus"]
    assert "PERIOD_END_MISMATCH" in result["FilingIdentityStatus"]


def test_scale_and_sign_are_applied_only_when_explicit(tmp_path):
    path = tmp_path / "sample.xml"
    path.write_text("""<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:g="urn:g">
      <context id="Q"><entity><identifier scheme="urn:s">1</identifier></entity>
      <period><startDate>2026-01-01</startDate><endDate>2026-03-31</endDate></period></context>
      <unit id="INR"><measure>iso4217:INR</measure></unit>
      <g:RevenueFromOperations contextRef="Q" unitRef="INR" scale="2" sign="-">12.5</g:RevenueFromOperations>
    </xbrl>""", encoding="utf-8")
    result = inspect_filing(path)
    assert result["Facts"][0]["ParsedNumericValue"] == "-1250.0"
