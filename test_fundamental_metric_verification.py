import hashlib
import json
from pathlib import Path

import pandas as pd

from fundamental_metric_verification import (
    DIRECT_FACT_TAGS,
    EVIDENCE_COLUMNS,
    build_metric_verification,
    _generated_ocf_evidence,
    run_audit,
)

NS = 'http://www.nseindia.com/xbrl/test'
URL = 'https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_TEST_WEB.xml'


def _metric(**overrides):
    row = {
        'TckrSymb': 'AAA', 'Source': 'Yahoo Finance via yfinance',
        'FinancialPeriodEnd': '2026-03-31', 'PublicationDate': '2026-05-20',
        'PublicationDateStatus': 'VERIFIED', 'MetricCalculationBasis': 'ANNUAL_ALIGNED_STATEMENTS',
        'MetricPeriodAlignmentStatus': 'VERIFIED', 'OfficialFilingURL': URL,
        'RevenueGrowthPct': 12.5, 'OperatingCashFlowINR': 12.5,
    }
    row.update(overrides)
    return row


def _filings():
    return pd.DataFrame([{
        'TckrSymb': 'AAA', 'FinancialPeriodEnd': '2026-03-31',
        'PublicationDate': '2026-05-20', 'PublicationDateStatus': 'VERIFIED',
        'OfficialFilingURL': URL,
    }])


def _xml(path: Path, value='12.5', dimensions='', cash_change=None, decimals=None, entity_scheme='https://www.nseindia.com'):
    cash_change = float(value) + 7.0 if cash_change is None else float(cash_change)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns="{NS}" xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <xbrli:context id="FY2026">
    <xbrli:entity><xbrli:identifier scheme="{entity_scheme}">INE000A01000</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period>
    {dimensions}
  </xbrli:context>
  <xbrli:unit id="INR"><xbrli:measure>INR</xbrli:measure></xbrli:unit>
  <CashFlowsFromUsedInOperatingActivities contextRef="FY2026" unitRef="INR"{f' decimals="{decimals}"' if decimals is not None else ''}>{value}</CashFlowsFromUsedInOperatingActivities>
  <CashFlowsFromUsedInInvestingActivities contextRef="FY2026" unitRef="INR">3</CashFlowsFromUsedInInvestingActivities>
  <CashFlowsFromUsedInFinancingActivities contextRef="FY2026" unitRef="INR">4</CashFlowsFromUsedInFinancingActivities>
  <IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges contextRef="FY2026" unitRef="INR">{cash_change}</IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges>
</xbrl>''', encoding='utf-8')
    return path


def _evidence(xml_path: Path, **overrides):
    digest = hashlib.sha256(xml_path.read_bytes()).hexdigest()
    row = {
        'TckrSymb': 'AAA', 'MetricName': 'OperatingCashFlowINR',
        'ProviderMetricValue': '12.5', 'OfficialMetricValue': '12.5', 'Tolerance': '0.0001',
        'FinancialPeriodEnd': '2026-03-31', 'PublicationDate': '2026-05-20',
        'MetricCalculationBasis': 'ANNUAL_ALIGNED_STATEMENTS', 'OfficialFilingURL': URL,
        'XbrlFactTag': 'CashFlowsFromUsedInOperatingActivities', 'XbrlContextRef': 'FY2026',
        'EntityIdentifier': 'INE000A01000', 'EntityIdentifierScheme': 'https://www.nseindia.com',
        'UnitMeasure': 'INR', 'TaxonomyNamespace': NS,
        'PeriodStart': '2025-04-01', 'PeriodEnd': '2026-03-31', 'DimensionsJSON': '[]',
        'EvidenceFilePath': str(xml_path.relative_to(Path.cwd())), 'EvidenceSHA256': digest,
        'VerificationMethod': 'DIRECT_FACT_MATCH', 'EvidenceDetailsJSON': json.dumps({'review': 'fact/context checked'}),
    }
    row.update(overrides)
    return pd.DataFrame([row], columns=EVIDENCE_COLUMNS)


def _approve_test_cashflow_mapping(monkeypatch):
    # Explicitly pin the selected annual operating-cash-flow concept in this
    # validator test. Production uses the same tag only after exact XML/context
    # checks and a same-context CFO + CFI + CFF cross-foot pass.
    monkeypatch.setitem(DIRECT_FACT_TAGS, 'OperatingCashFlowINR',
                        {'CashFlowsFromUsedInOperatingActivities'})


def test_official_filing_metadata_does_not_verify_provider_metric(tmp_path):
    metrics = pd.DataFrame([_metric()])
    detail, _, _ = build_metric_verification(metrics, _filings(), pd.DataFrame(columns=EVIDENCE_COLUMNS), tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['FilingMetadataStatus'] == 'OFFICIAL_FILING_METADATA_MATCHED'
    assert row['MetricValueVerificationStatus'] == 'PROVIDER_ONLY'
    assert 'does not verify metric values' in row['FilingMetadataReason']


def test_direct_fact_verification_requires_xml_hash_context_and_value_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _approve_test_cashflow_mapping(monkeypatch)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml')
    evidence = _evidence(xml_path)
    detail, _, _ = build_metric_verification(pd.DataFrame([_metric()]), _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'OFFICIAL_XBRL_VERIFIED'


def test_provider_value_mismatch_cannot_be_verified(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _approve_test_cashflow_mapping(monkeypatch)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml', value='12.6')
    evidence = _evidence(xml_path, OfficialMetricValue='12.6')
    detail, _, _ = build_metric_verification(pd.DataFrame([_metric()]), _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'PROVIDER_VALUE_MISMATCH'


def test_hash_mismatch_cannot_be_verified(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _approve_test_cashflow_mapping(monkeypatch)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml')
    evidence = _evidence(xml_path, EvidenceSHA256='0' * 64)
    detail, _, _ = build_metric_verification(pd.DataFrame([_metric()]), _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'EVIDENCE_SHA256_MISMATCH'


def test_derived_metric_is_not_promoted_by_direct_fact_rule(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _approve_test_cashflow_mapping(monkeypatch)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml')
    evidence = _evidence(xml_path, VerificationMethod='DERIVED_FROM_COMPONENT_FACTS')
    detail, _, _ = build_metric_verification(pd.DataFrame([_metric()]), _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'DERIVED_RECONCILIATION_REQUIRED'


def test_dimension_conflict_is_not_verified(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _approve_test_cashflow_mapping(monkeypatch)
    dim = '<xbrli:scenario><xbrldi:explicitMember dimension="ns:SegmentAxis">ns:RetailMember</xbrldi:explicitMember></xbrli:scenario>'
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml', dimensions=dim)
    evidence = _evidence(xml_path, DimensionsJSON='[]')
    detail, _, _ = build_metric_verification(pd.DataFrame([_metric()]), _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'XBRL_DIMENSIONS_MISMATCH'


def test_audit_creates_empty_evidence_template_and_does_not_modify_cache(tmp_path):
    metrics_path = tmp_path / 'data/inputs/fundamental_metrics.csv'
    filings_path = tmp_path / 'outputs/v8_official_financial_results_filings.csv'
    metrics_path.parent.mkdir(parents=True)
    filings_path.parent.mkdir(parents=True)
    source = pd.DataFrame([_metric()])
    source.to_csv(metrics_path, index=False)
    _filings().to_csv(filings_path, index=False)
    before = metrics_path.read_bytes()
    detail, summary, filing_summary = run_audit(metrics_path, filings_path, tmp_path / 'data/inputs/fundamental_metric_verification_evidence.csv',
                                                tmp_path / 'outputs', repo_root=tmp_path)
    assert len(detail) == 2
    ocf = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert ocf['MetricValueVerificationStatus'] == 'PROVIDER_ONLY'
    assert not summary.empty
    assert not filing_summary.empty
    assert (tmp_path / 'outputs/v8_fundamental_filing_metadata_summary.csv').exists()
    assert metrics_path.read_bytes() == before
    assert (tmp_path / 'data/inputs/fundamental_metric_verification_evidence.csv').exists()


def test_growth_metric_cannot_be_marked_verified_by_single_direct_fact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml')
    evidence = _evidence(xml_path)
    evidence.loc[0, 'MetricName'] = 'RevenueGrowthPct'
    detail, _, _ = build_metric_verification(pd.DataFrame([_metric()]), _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('RevenueGrowthPct')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'DERIVED_RECONCILIATION_REQUIRED'


def test_operating_cashflow_tag_is_approved_only_with_crossfoot_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml')
    evidence = _evidence(xml_path)
    detail, _, _ = build_metric_verification(pd.DataFrame([_metric()]), _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'OFFICIAL_XBRL_VERIFIED'
    assert 'cross-foot reconciled' in row['MetricValueVerificationReason']


def test_operating_cashflow_requires_statement_crossfoot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _approve_test_cashflow_mapping(monkeypatch)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml', cash_change=22.5)
    evidence = _evidence(xml_path)
    detail, _, _ = build_metric_verification(pd.DataFrame([_metric()]), _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'XBRL_CASHFLOW_CROSSFOOT_FAILED'
    assert 'does not reconcile' in row['MetricValueVerificationReason']


def test_generated_ocf_evidence_uses_official_filing_and_xml_crossfoot(tmp_path, monkeypatch):
    import nse_xbrl_fetch
    source = _xml(tmp_path / 'source.xml')
    fetches = []

    def fake_fetch(url, destination):
        assert url == URL
        fetches.append(url)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        return destination

    monkeypatch.setattr(nse_xbrl_fetch, 'fetch_official_xbrl_xml', fake_fetch)
    metrics = pd.DataFrame([_metric()])
    generated, diagnostics = _generated_ocf_evidence(
        metrics, _filings(), pd.DataFrame(columns=EVIDENCE_COLUMNS), tmp_path, {'AAA'})
    assert len(generated) == 1
    assert generated.loc[0, 'XbrlFactTag'] == 'CashFlowsFromUsedInOperatingActivities'
    assert generated.loc[0, 'VerificationMethod'] == 'DIRECT_FACT_MATCH'
    assert generated.loc[0, 'EvidenceSHA256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert diagnostics.empty
    assert fetches == [URL]


def test_generated_ocf_evidence_does_not_touch_manual_ledger_or_fetch_unrequested_symbols(tmp_path, monkeypatch):
    import nse_xbrl_fetch
    monkeypatch.setattr(nse_xbrl_fetch, 'fetch_official_xbrl_xml',
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('unexpected fetch')))
    generated, diagnostics = _generated_ocf_evidence(
        pd.DataFrame([_metric()]), _filings(), pd.DataFrame(columns=EVIDENCE_COLUMNS), tmp_path, {'BBB'})
    assert generated.empty
    assert diagnostics.empty


def test_metric_verification_is_blocked_when_exact_filing_metadata_does_not_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml')
    evidence = _evidence(xml_path)
    wrong_filings = _filings().iloc[0:0]
    detail, _, _ = build_metric_verification(pd.DataFrame([_metric()]), wrong_filings, evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'FILING_METADATA_NOT_CONFIRMED'





def test_provider_value_inside_xbrl_decimals_interval_is_not_false_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _approve_test_cashflow_mapping(monkeypatch)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml', value='12.5', decimals='0')
    evidence = _evidence(xml_path, ProviderMetricValue='12.8', OfficialMetricValue='12.5')
    metric = pd.DataFrame([_metric(OperatingCashFlowINR=12.8)])
    detail, _, _ = build_metric_verification(metric, _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'PROVIDER_VALUE_WITHIN_XBRL_ACCURACY'
    assert 'exact fact equality is not established' in row['MetricValueVerificationReason']


def test_provider_value_outside_xbrl_decimals_interval_remains_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _approve_test_cashflow_mapping(monkeypatch)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml', value='12.5', decimals='0')
    evidence = _evidence(xml_path, ProviderMetricValue='13.1', OfficialMetricValue='12.5')
    metric = pd.DataFrame([_metric(OperatingCashFlowINR=13.1)])
    detail, _, _ = build_metric_verification(metric, _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'PROVIDER_VALUE_MISMATCH'


def test_xbrl_inf_decimals_requires_exact_provider_fact_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _approve_test_cashflow_mapping(monkeypatch)
    xml_path = _xml(tmp_path / 'data/cache/xbrl_samples/aaa.xml', value='12.5', decimals='INF')
    evidence = _evidence(xml_path, ProviderMetricValue='12.5001', OfficialMetricValue='12.5')
    metric = pd.DataFrame([_metric(OperatingCashFlowINR=12.5001)])
    detail, _, _ = build_metric_verification(metric, _filings(), evidence, tmp_path)
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['MetricValueVerificationStatus'] == 'PROVIDER_VALUE_MISMATCH'


def _annual_growth_xml(path: Path, period_end: str, revenue_ops: float,
                       other_income: float, profit_continuing: float,
                       discontinued: float = 0.0, associates: float = 0.0,
                       entity_scheme: str = "https://www.nseindia.com"):
    year = int(period_end[:4])
    period_start = f"{year - 1}-04-01"
    total_income = revenue_ops + other_income
    total_profit = profit_continuing + discontinued + associates
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns="{NS}" xmlns:xbrli="http://www.xbrl.org/2003/instance">
  <xbrli:context id="FY">
    <xbrli:entity><xbrli:identifier scheme="https://www.nseindia.com">INE000A01000</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>{period_start}</xbrli:startDate><xbrli:endDate>{period_end}</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:unit id="INR"><xbrli:measure>INR</xbrli:measure></xbrli:unit>
  <RevenueFromOperations contextRef="FY" unitRef="INR">{revenue_ops}</RevenueFromOperations>
  <OtherIncome contextRef="FY" unitRef="INR">{other_income}</OtherIncome>
  <Income contextRef="FY" unitRef="INR">{total_income}</Income>
  <ProfitLossForPeriodFromContinuingOperations contextRef="FY" unitRef="INR">{profit_continuing}</ProfitLossForPeriodFromContinuingOperations>
  <ProfitLossFromDiscontinuedOperationsAfterTax contextRef="FY" unitRef="INR">{discontinued}</ProfitLossFromDiscontinuedOperationsAfterTax>
  <ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod contextRef="FY" unitRef="INR">{associates}</ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod>
  <ProfitLossForPeriod contextRef="FY" unitRef="INR">{total_profit}</ProfitLossForPeriod>
</xbrl>''', encoding="utf-8")
    return path


def test_generated_annual_growth_evidence_reconciles_two_official_fy_filings(tmp_path, monkeypatch):
    import nse_xbrl_fetch
    from fundamental_metric_verification import _generated_growth_evidence

    current_url = URL
    prior_url = "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_PRIOR_TEST_WEB.xml"
    current_xml = _annual_growth_xml(
        tmp_path / "source_current.xml", "2026-03-31",
        revenue_ops=120.0, other_income=10.0, profit_continuing=25.0,
        discontinued=1.0, associates=2.0,
        entity_scheme="http://www.sebi.gov.in/in-capmkt/ScripCode",
    )
    prior_xml = _annual_growth_xml(
        tmp_path / "source_prior.xml", "2025-03-31",
        revenue_ops=100.0, other_income=5.0, profit_continuing=20.0,
        discontinued=0.0, associates=0.0,
        entity_scheme="http://www.bseindia.com/in-capmkt/ScripCode",
    )
    source_by_url = {current_url: current_xml, prior_url: prior_xml}
    fetches = []

    def fake_fetch(url, destination):
        fetches.append(url)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_by_url[url].read_bytes())
        return destination

    monkeypatch.setattr(nse_xbrl_fetch, "fetch_official_xbrl_xml", fake_fetch)
    metrics = pd.DataFrame([_metric(RevenueGrowthPct=20.0, ProfitGrowthPct=40.0)])
    filings = pd.DataFrame([
        {
            "TckrSymb": "AAA", "FinancialPeriodEnd": "2026-03-31",
            "PublicationDate": "2026-05-20", "PublicationDateStatus": "VERIFIED",
            "OfficialFilingURL": current_url, "FilingDescription": "Audited Standalone Financial Results",
        },
        {
            "TckrSymb": "AAA", "FinancialPeriodEnd": "2025-03-31",
            "PublicationDate": "2025-05-22", "PublicationDateStatus": "VERIFIED",
            "OfficialFilingURL": prior_url, "FilingDescription": "Audited Standalone Financial Results",
        },
    ])
    generated, diagnostics = _generated_growth_evidence(
        metrics, filings, pd.DataFrame(columns=EVIDENCE_COLUMNS), tmp_path, {"AAA"}
    )

    assert set(generated["MetricName"]) == {"RevenueGrowthPct", "ProfitGrowthPct"}
    assert set(generated["VerificationMethod"]) == {"DERIVED_COMPONENT_FACTS"}
    assert generated.set_index("MetricName").loc["RevenueGrowthPct", "OfficialMetricValue"] == "20.0"
    assert generated.set_index("MetricName").loc["ProfitGrowthPct", "OfficialMetricValue"] == "40.0"
    assert diagnostics.empty
    assert set(fetches) == {current_url, prior_url}

    detail, _, _ = build_metric_verification(metrics, filings, generated, repo_root=tmp_path)
    growth = detail[detail["MetricName"].isin(["RevenueGrowthPct", "ProfitGrowthPct"])]
    assert set(growth["MetricValueVerificationStatus"]) == {"OFFICIAL_XBRL_VERIFIED"}


def test_generated_annual_growth_evidence_keeps_provider_mismatch_unverified(tmp_path, monkeypatch):
    import nse_xbrl_fetch
    from fundamental_metric_verification import _generated_growth_evidence

    current_url = URL
    prior_url = "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_PRIOR_TEST_WEB.xml"
    current_xml = _annual_growth_xml(
        tmp_path / "source_current.xml", "2026-03-31",
        revenue_ops=120.0, other_income=10.0, profit_continuing=25.0,
    )
    prior_xml = _annual_growth_xml(
        tmp_path / "source_prior.xml", "2025-03-31",
        revenue_ops=100.0, other_income=5.0, profit_continuing=20.0,
    )
    source_by_url = {current_url: current_xml, prior_url: prior_xml}

    def fake_fetch(url, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_by_url[url].read_bytes())
        return destination

    monkeypatch.setattr(nse_xbrl_fetch, "fetch_official_xbrl_xml", fake_fetch)
    metrics = pd.DataFrame([_metric(RevenueGrowthPct=21.0, ProfitGrowthPct=25.0)])
    filings = pd.DataFrame([
        {
            "TckrSymb": "AAA", "FinancialPeriodEnd": "2026-03-31",
            "PublicationDate": "2026-05-20", "PublicationDateStatus": "VERIFIED",
            "OfficialFilingURL": current_url, "FilingDescription": "Audited Standalone Financial Results",
        },
        {
            "TckrSymb": "AAA", "FinancialPeriodEnd": "2025-03-31",
            "PublicationDate": "2025-05-22", "PublicationDateStatus": "VERIFIED",
            "OfficialFilingURL": prior_url, "FilingDescription": "Audited Standalone Financial Results",
        },
    ])
    generated, diagnostics = _generated_growth_evidence(
        metrics, filings, pd.DataFrame(columns=EVIDENCE_COLUMNS), tmp_path, {"AAA"}
    )
    detail, _, _ = build_metric_verification(metrics, filings, generated, repo_root=tmp_path)
    revenue = detail[detail["MetricName"].eq("RevenueGrowthPct")].iloc[0]
    profit = detail[detail["MetricName"].eq("ProfitGrowthPct")].iloc[0]
    assert revenue["MetricValueVerificationStatus"] == "PROVIDER_VALUE_MISMATCH"
    assert profit["MetricValueVerificationStatus"] == "OFFICIAL_XBRL_VERIFIED"
    assert diagnostics.empty

def test_filing_metadata_rejects_lookalike_archive_hosts(tmp_path):
    lookalike = 'https://nsearchives.nseindia.in.evil.example/corporate/xbrl/INTEGRATED_FILING_TEST_WEB.xml'
    metrics = pd.DataFrame([_metric(OfficialFilingURL=lookalike)])
    filings = _filings()
    filings.loc[0, 'OfficialFilingURL'] = lookalike
    detail, _, _ = build_metric_verification(
        metrics, filings, pd.DataFrame(columns=EVIDENCE_COLUMNS), tmp_path,
    )
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['FilingMetadataStatus'] == 'FILING_URL_NOT_OFFICIAL_XBRL_HOST'


def test_filing_metadata_rejects_wrong_nse_archive_domain(tmp_path):
    wrong_domain = 'https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_TEST_WEB.xml'
    metrics = pd.DataFrame([_metric(OfficialFilingURL=wrong_domain)])
    filings = _filings()
    filings.loc[0, 'OfficialFilingURL'] = wrong_domain
    detail, _, _ = build_metric_verification(
        metrics, filings, pd.DataFrame(columns=EVIDENCE_COLUMNS), tmp_path,
    )
    row = detail[detail.MetricName.eq('OperatingCashFlowINR')].iloc[0]
    assert row['FilingMetadataStatus'] == 'FILING_URL_NOT_OFFICIAL_XBRL_HOST'
