    detail, _, _ = build_metric_verification(metrics, filings, generated, repo_root=tmp_path)
    revenue = detail[detail["MetricName"].eq("RevenueGrowthPct")].iloc[0]
    profit = detail[detail["MetricName"].eq("ProfitGrowthPct")].iloc[0]
    assert revenue["MetricValueVerificationStatus"] == "PROVIDER_VALUE_MISMATCH"
    assert profit["MetricValueVerificationStatus"] == "OFFICIAL_XBRL_VERIFIED"
    assert diagnostics.empty



def test_growth_accepts_scheme_migration_only_with_matching_official_symbol_and_scripcode(tmp_path, monkeypatch):
    import nse_xbrl_fetch
    from fundamental_metric_verification import _generated_growth_evidence

    current_url = URL
    prior_url = "https://nsearchives.nseindia.in/corporate/xbrl/INTEGRATED_FILING_PRIOR_CROSSWALK.xml"
    current_xml = _annual_growth_xml(
        tmp_path / "source_current_crosswalk.xml", "2026-03-31",
        revenue_ops=120.0, other_income=10.0, profit_continuing=25.0,
        entity_scheme="http://www.sebi.gov.in/in-capmkt/ScripCode",
        entity_identifier="532768", issuer_symbol="AAA", issuer_scrip_code="532768", issuer_company_name="AAA Limited",
    )
    prior_xml = _annual_growth_xml(
        tmp_path / "source_prior_crosswalk.xml", "2025-03-31",
        revenue_ops=100.0, other_income=5.0, profit_continuing=20.0,
        entity_scheme="http://www.bseindia.com/in-capmkt/Symbol",
        entity_identifier="AAA", issuer_symbol="AAA", issuer_scrip_code="000000", issuer_company_name="AAA Limited",
    )
    source_by_url = {current_url: current_xml, prior_url: prior_xml}

    def fake_fetch(url, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_by_url[url].read_bytes())
        return destination

    monkeypatch.setattr(nse_xbrl_fetch, "fetch_official_xbrl_xml", fake_fetch)
    metrics = pd.DataFrame([_metric(RevenueGrowthPct=20.0, ProfitGrowthPct=25.0)])
    filings = pd.DataFrame([
        {"TckrSymb": "AAA", "FinancialPeriodEnd": "2026-03-31",
         "PublicationDate": "2026-05-20", "PublicationDateStatus": "VERIFIED",
         "OfficialFilingURL": current_url, "FilingDescription": "Audited Standalone Financial Results"},
        {"TckrSymb": "AAA", "FinancialPeriodEnd": "2025-03-31",
         "PublicationDate": "2025-05-22", "PublicationDateStatus": "VERIFIED",
         "OfficialFilingURL": prior_url, "FilingDescription": "Audited Standalone Financial Results"},
    ])
    generated, diagnostics = _generated_growth_evidence(
        metrics, filings, pd.DataFrame(columns=EVIDENCE_COLUMNS), tmp_path, {"AAA"}
    )
    assert set(generated["MetricName"]) == {"RevenueGrowthPct", "ProfitGrowthPct"}
    assert diagnostics.empty
    detail, _, _ = build_metric_verification(metrics, filings, generated, repo_root=tmp_path)
    growth = detail[detail["MetricName"].isin(["RevenueGrowthPct", "ProfitGrowthPct"])]
    assert set(growth["MetricValueVerificationStatus"]) == {"OFFICIAL_XBRL_VERIFIED"}


def test_growth_scheme_migration_rejects_mismatched_scripcode(tmp_path, monkeypatch):
    import nse_xbrl_fetch
    from fundamental_metric_verification import _generated_growth_evidence

    current_url = URL
    prior_url = "https://nsearchives.nseindia.in/corporate/xbrl/INTEGRATED_FILING_PRIOR_WRONG_CODE.xml"
    current_xml = _annual_growth_xml(
        tmp_path / "source_current_wrong_code.xml", "2026-03-31",
        revenue_ops=120.0, other_income=10.0, profit_continuing=25.0,
        entity_scheme="http://www.sebi.gov.in/in-capmkt/ScripCode",
        entity_identifier="532768", issuer_symbol="AAA", issuer_scrip_code="532768", issuer_company_name="AAA Limited",
    )
    prior_xml = _annual_growth_xml(
        tmp_path / "source_prior_wrong_code.xml", "2025-03-31",
        revenue_ops=100.0, other_income=5.0, profit_continuing=20.0,
        entity_scheme="http://www.bseindia.com/in-capmkt/Symbol",
        entity_identifier="AAA", issuer_symbol="AAA", issuer_scrip_code="532769", issuer_company_name="AAA Limited",
    )
    source_by_url = {current_url: current_xml, prior_url: prior_xml}

    def fake_fetch(url, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_by_url[url].read_bytes())
        return destination

    monkeypatch.setattr(nse_xbrl_fetch, "fetch_official_xbrl_xml", fake_fetch)
    metrics = pd.DataFrame([_metric(RevenueGrowthPct=20.0, ProfitGrowthPct=25.0)])
    filings = pd.DataFrame([
        {"TckrSymb": "AAA", "FinancialPeriodEnd": "2026-03-31",
         "PublicationDate": "2026-05-20", "PublicationDateStatus": "VERIFIED",