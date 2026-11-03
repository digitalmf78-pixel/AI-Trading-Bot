import json
import pandas as pd

import nse_xbrl_sample_diagnostic as diag


XML = b"""<?xml version='1.0'?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:in-gaap="http://example.com/gaap">
 <xbrli:context id="Q1"><xbrli:entity><xbrli:identifier scheme="x">INE001</xbrli:identifier><xbrli:segment><xbrldi:explicitMember xmlns:xbrldi="http://xbrl.org/2006/xbrldi" dimension="in-gaap:StatementTypeAxis">in-gaap:StandaloneMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
  <xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
 <in-gaap:NetCashFlowsFromUsedInOperatingActivities contextRef="Q1" unitRef="INR" decimals="0">1234</in-gaap:NetCashFlowsFromUsedInOperatingActivities>
 <in-gaap:RevenueFromOperations contextRef="Q1" unitRef="INR">5000</in-gaap:RevenueFromOperations>
</xbrli:xbrl>"""


def test_inspect_xbrl_xml_extracts_context_units_and_cashflow(tmp_path):
    path = tmp_path / "sample.xml"
    path.write_bytes(XML)
    result = diag.inspect_xbrl_xml(path)
    assert result["context_count"] == 1
    assert result["unit_count"] == 1
    assert result["fact_count"] == 2
    assert result["cashflow_candidate_fact_count"] == 1
    fact = result["cashflow_facts"][0]
    assert fact["value"] == "1234"
    assert fact["context"]["period"]["endDate"] == "2026-06-30"
    assert fact["context"]["entity_identifier"] == "INE001"
    assert fact["context"]["dimensions"][0]["member"] == "in-gaap:StandaloneMember"


def test_select_samples_only_allows_official_xml_and_deduplicates(tmp_path):
    path = tmp_path / "metrics.csv"
    pd.DataFrame([
        {"TckrSymb": "AAA", "PublicationDate": "2026-10-01", "OfficialFilingURL": "https://nsearchives.nseindia.com/a.xml"},
        {"TckrSymb": "AAA", "PublicationDate": "2026-10-01", "OfficialFilingURL": "https://nsearchives.nseindia.com/a.xml"},
        {"TckrSymb": "BBB", "PublicationDate": "2026-10-02", "OfficialFilingURL": "https://example.com/b.xml"},
        {"TckrSymb": "CCC", "PublicationDate": "2026-10-03", "OfficialFilingURL": "http://nsearchives.nseindia.com/c.xml"},
        {"TckrSymb": "DDD", "PublicationDate": "2026-10-04", "OfficialFilingURL": "https://nsearchives.nseindia.com/d.xml"},
    ]).to_csv(path, index=False)
    rows = diag.select_samples(path, limit=5)
    assert [r["TckrSymb"] for r in rows] == ["DDD", "AAA"]


def test_run_diagnostic_writes_machine_readable_report(tmp_path, monkeypatch):
    metrics = tmp_path / "metrics.csv"
    pd.DataFrame([{
        "TckrSymb": "AAA", "PublicationDate": "2026-10-01",
        "FinancialPeriodEnd": "2026-06-30",
        "OfficialFilingURL": "https://nsearchives.nseindia.com/a.xml",
    }]).to_csv(metrics, index=False)

    def fake_fetch(url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(XML)
        return destination

    monkeypatch.setattr(diag, "fetch_official_xbrl_xml", fake_fetch)
    out = tmp_path / "out"
    report = diag.run_diagnostic(metrics, out, tmp_path / "cache", limit=1)
    assert report["status"] == "SUCCESS"
    assert report["success_count"] == 1
    saved = json.loads((out / "xbrl_sample_diagnostic.json").read_text())
    assert saved["results"][0]["context_count"] == 1
    assert (out / "xbrl_sample_diagnostic_summary.csv").exists()
