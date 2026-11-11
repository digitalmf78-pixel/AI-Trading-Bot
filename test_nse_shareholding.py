import json
from datetime import datetime, timezone

from nse_shareholding import (
    NSE_SHAREHOLDING_API,
    fetch_nse_shareholding_metrics,
    parse_shareholding_xbrl,
)


NS = "http://www.xbrl.org/2003/instance"
XD = "http://xbrl.org/2006/xbrldi"
SHP = "http://www.nseindia.com/xbrl/2025-10-31/in-bse-shp"


def _xml_filing(values, period="2026-09-30", duplicate_promoter=None):
    rows = []
    facts = []
    items = list(values.items())
    if duplicate_promoter is not None:
        items.append(("PromoterHoldingPct__duplicate", duplicate_promoter))
    mapping = {
        "PromoterHoldingPct": "ShareholdingOfPromoterAndPromoterGroupMember",
        "PublicHoldingPct": "PublicShareholdingMember",
        "FIIHoldingPct": "InstitutionsForeignMember",
        "DIIHoldingPct": "InstitutionsDomesticMember",
        "PromoterHoldingPct__duplicate": "ShareholdingOfPromoterAndPromoterGroupMember",
    }
    for index, (metric, value) in enumerate(items):
        context_id = f"ctx{index}"
        rows.append(
            f'<xbrli:context id="{context_id}">'
            f'<xbrli:entity><xbrli:identifier scheme="https://www.nseindia.com">AAA</xbrli:identifier></xbrli:entity>'
            f'<xbrli:period><xbrli:instant>{period}</xbrli:instant></xbrli:period>'
            f'<xbrli:scenario><xbrldi:explicitMember dimension="in-bse-shp:ShareholdingCategoryAxis">'
            f'in-bse-shp:{mapping[metric]}</xbrldi:explicitMember></xbrli:scenario>'
            f'</xbrli:context>'
        )
        facts.append(
            f'<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="{context_id}">{value}</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>'
        )
    return (
        f'<xbrli:xbrl xmlns:xbrli="{NS}" xmlns:xbrldi="{XD}" xmlns:in-bse-shp="{SHP}">'
        + "".join(rows) + "".join(facts) + "</xbrli:xbrl>"
    ).encode("utf-8")


def test_parses_fraction_scale_v1_1_promoter_public_fii_dii():
    xml = _xml_filing({
        "PromoterHoldingPct": 0.50,
        "PublicHoldingPct": 0.50,
        "FIIHoldingPct": 0.15,
        "DIIHoldingPct": 0.10,
    })
    parsed = parse_shareholding_xbrl(xml, expected_period_end="2026-09-30")

    assert parsed["status"] == "DATA_FOUND"
    assert parsed["scale_factor"] == 100.0
    assert parsed["metrics"] == {
        "PromoterHoldingPct": 50.0,
        "PublicHoldingPct": 50.0,
        "FIIHoldingPct": 15.0,
        "DIIHoldingPct": 10.0,
    }
    assert parsed["promoter_public_total_check"] == "WITHIN_2PP_OF_100"


def test_parses_legacy_basis_point_scale_without_changing_fact_meaning():
    xml = _xml_filing({
        "PromoterHoldingPct": 5049.0,
        "PublicHoldingPct": 4951.0,
        "FIIHoldingPct": 1200.0,
        "DIIHoldingPct": 850.0,
    })
    parsed = parse_shareholding_xbrl(xml, expected_period_end="2026-09-30")

    assert parsed["status"] == "DATA_FOUND"
    assert parsed["scale_factor"] == 0.01
    assert parsed["metrics"]["PromoterHoldingPct"] == 50.49
    assert parsed["metrics"]["PublicHoldingPct"] == 49.51
    assert parsed["metrics"]["FIIHoldingPct"] == 12.0
    assert parsed["metrics"]["DIIHoldingPct"] == 8.5


def test_fails_closed_when_filing_period_does_not_match():
    xml = _xml_filing({
        "PromoterHoldingPct": 0.50,
        "PublicHoldingPct": 0.50,
    }, period="2026-06-30")
    parsed = parse_shareholding_xbrl(xml, expected_period_end="2026-09-30")

    assert parsed["status"] == "NO_MAPPED_SHAREHOLDING_FACTS"
    assert parsed["metrics"] == {}


def test_fails_closed_on_conflicting_rollup_facts():
    xml = _xml_filing({
        "PromoterHoldingPct": 0.50,
        "PublicHoldingPct": 0.50,
    }, duplicate_promoter=0.47)
    parsed = parse_shareholding_xbrl(xml, expected_period_end="2026-09-30")

    assert parsed["status"] == "AMBIGUOUS_DIMENSIONAL_FACTS"
    assert parsed["metrics"] == {}


def test_fails_closed_on_out_of_range_normalized_values():
    xml = _xml_filing({
        "PromoterHoldingPct": 1.10,
        "PublicHoldingPct": 0.50,
    })
    parsed = parse_shareholding_xbrl(xml, expected_period_end="2026-09-30")

    assert parsed["status"] == "INVALID_SHAREHOLDING_PERCENTAGE"
    assert parsed["metrics"] == {}


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        if url == NSE_SHAREHOLDING_API:
            return FakeResponse(self.payload)
        return FakeResponse({})


def test_fetches_official_nse_index_and_caches_latest_xbrl(tmp_path):
    xml = _xml_filing({
        "PromoterHoldingPct": 0.55,
        "PublicHoldingPct": 0.45,
        "FIIHoldingPct": 0.10,
        "DIIHoldingPct": 0.08,
    })
    filing = {
        "symbol": "AAA",
        "date": "30-SEP-2026",
        "submissionDate": "19-OCT-2026",
        "broadcastDate": "19-OCT-2026 16:00:00",
        "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/SHP_TEST_WEB.xml",
        "recordId": "12345",
        "revisedData": "N",
    }
    session = FakeSession([filing])
    calls = []

    def fake_xbrl_fetcher(url, destination, attempts=2):
        calls.append((url, attempts))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(xml)
        return destination

    now = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
    first = fetch_nse_shareholding_metrics(
        "AAA",
        cache_dir=tmp_path,
        session_factory=lambda: session,
        xbrl_fetcher=fake_xbrl_fetcher,
        now=now,
    )
    second = fetch_nse_shareholding_metrics(
        "AAA",
        cache_dir=tmp_path,
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("fresh index cache should avoid API call")),
        xbrl_fetcher=lambda *a, **k: (_ for _ in ()).throw(AssertionError("XML cache should be reused")),
        now=now,
    )

    assert first["provider"]["status"] == "DATA_FOUND"
    assert first["metrics"]["PromoterHoldingPct"] == 55.0
    assert first["metrics"]["FIIHoldingPct"] == 10.0
    assert first["metric_periods"]["PromoterHoldingPct"] == "2026-09-30"
    assert first["metric_sources"]["PromoterHoldingPct"] == "NSE Official Shareholding XBRL"
    assert first["provider"]["xbrl_cache_status"] == "DOWNLOADED"
    assert second["provider"]["status"] == "DATA_FOUND"
    assert second["provider"]["xbrl_cache_status"] == "REUSED_CACHE"
    assert len(calls) == 1
    assert len(session.calls) == 2  # homepage warm-up + one filing-index request
    cached_index = json.loads((tmp_path / "filing_index" / "AAA.json").read_text())
    assert cached_index["latest_filing"]["period_end"] == "2026-09-30"


def test_rejects_untrusted_or_non_official_xbrl_links(tmp_path):
    session = FakeSession([{
        "symbol": "AAA",
        "date": "30-SEP-2026",
        "xbrl": "https://evil.example/SHP_TEST.xml",
    }])
    result = fetch_nse_shareholding_metrics(
        "AAA", cache_dir=tmp_path, session_factory=lambda: session,
    )

    assert result["provider"]["status"] == "NO_FILING_FOUND"
    assert result["metrics"] == {}
