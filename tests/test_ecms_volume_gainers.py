import pandas as pd
from strategies.ecms.volume_gainers import _find_records, _number, _get, ALIASES, attach_page_rvol

def test_find_records_supports_nested_nse_payload():
    rows = _find_records({"data": {"volumeGainers": [{"symbol": "ABC", "ltp": 100}]}})
    assert len(rows) == 1 and rows[0]["symbol"] == "ABC"

def test_find_records_rejects_payload_without_symbol_rows():
    assert _find_records({"data": [{"name": "not a stock"}]}) == []

def test_number_parses_nse_formatted_values():
    assert _number("1,23,456") == 123456.0
    assert _number("12.5%") == 12.5
    assert _number("-") is None

def test_alias_lookup_ignores_case_and_punctuation():
    row = {"pChange": "4.25", "totalTradedVolume": "12345"}
    assert _number(_get(row, ALIASES["change_pct"])) == 4.25
    assert _number(_get(row, ALIASES["volume"])) == 12345.0


def test_attach_page_rvol_keeps_nse_page_universe_when_bhavcopy_is_unavailable(monkeypatch):
    import strategies.ecms.volume_gainers as scanner

    def unavailable():
        raise RuntimeError("Bhavcopy cache unavailable")

    monkeypatch.setattr(scanner, "discover_latest_session", unavailable)
    page = pd.DataFrame({
        "TckrSymb": ["AAA", "BBB"],
        "PageVolume": [100000, 80000],
    })
    result = scanner.attach_page_rvol(page, __import__("datetime").date(2026, 11, 13))
    assert set(result["TckrSymb"]) == {"AAA", "BBB"}
    assert result["RVOL"].isna().all()
    assert result["RVOLDataStatus"].str.startswith("WAIT_FOR_DATA").all()


def test_fundamental_collection_uses_ecms_workspace_not_production_cache(tmp_path, monkeypatch):
    import sys
    import types
    from pathlib import Path
    import strategies.ecms.volume_gainers as scanner

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(scanner, "OUTPUT_DIR", Path("outputs/ecms"))
    monkeypatch.setattr(scanner, "STATE_DIR", Path("data/cache/ecms"))
    monkeypatch.setattr(scanner, "METRICS_PATH", Path("data/inputs/production_metrics.csv"))
    monkeypatch.setattr(scanner, "FILINGS_PATH", Path("outputs/production_filings.csv"))
    monkeypatch.setattr(scanner, "EVIDENCE_PATH", Path("data/inputs/production_evidence.csv"))
    monkeypatch.setattr(scanner, "THRESHOLDS_PATH", Path("data/inputs/thresholds.json"))

    def fake_collect(candidates, metrics_path, enabled, asof_date, free_source_fetcher=None, force_retry_incomplete=False):
        assert enabled is True
        assert callable(free_source_fetcher)
        assert force_retry_incomplete is True
        assert set(candidates["TckrSymb"]) == {"AAA"}
        path = Path(metrics_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{"TckrSymb": "AAA", "RevenueGrowthPct": 20}]).to_csv(path, index=False)
        diagnostics = Path("outputs/v8_fundamental_provider_diagnostics.csv")
        diagnostics.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{"TckrSymb": "AAA", "ProviderStatus": "PASS"}]).to_csv(diagnostics, index=False)

    fake_provider = types.ModuleType("fundamental_data_provider")
    fake_provider.collect_missing_fundamentals = fake_collect
    monkeypatch.setitem(sys.modules, "fundamental_data_provider", fake_provider)

    def fake_audit(**kwargs):
        verification = pd.DataFrame([{
            "TckrSymb": "AAA",
            "MetricName": "RevenueGrowthPct",
            "MetricValueVerificationStatus": "OFFICIAL_XBRL_VERIFIED",
        }])
        return verification, pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(scanner, "run_fundamental_xbrl_audit", fake_audit)

    def fake_shortlist(joined, *args, **kwargs):
        out = joined.copy()
        out["FundamentalShortlistStatus"] = "PASS"
        out["FundamentalShortlistReason"] = "TEST_PASS"
        out["FundamentalAssessmentStatus"] = "PASS"
        out["FundamentalAssessmentReason"] = "TEST_PASS"
        return out

    monkeypatch.setattr(scanner, "build_fundamental_shortlist", fake_shortlist)
    result = scanner.assess_page_fundamentals(
        pd.DataFrame([{"TckrSymb": "AAA", "CompanyName": "AAA Limited"}]),
        __import__("datetime").date(2026, 11, 13),
    )

    workspace_metrics = (
        tmp_path / "data/cache/ecms/fundamental_workspace/data/inputs/fundamental_metrics.csv"
    )
    assert workspace_metrics.exists()
    assert not (tmp_path / "data/inputs/production_metrics.csv").exists()
    assert result.iloc[0]["FundamentalShortlistStatus"] == "PASS"
    assert (tmp_path / "outputs/ecms/fundamental_metrics_ecms.csv").exists()



def test_strong_fundamental_mask_requires_strict_pass_strong_and_80pct_coverage():
    from strategies.ecms.volume_gainers import _strong_fundamental_mask

    frame = pd.DataFrame({
        "FundamentalShortlistStatus": ["PASS", "PASS", "FAIL", "PASS"],
        "FundamentalResearchClassification": ["STRONG", "GOOD", "STRONG", "STRONG"],
        "FundamentalResearchCoveragePct": [80, 95, 90, 79.9],
    })
    assert _strong_fundamental_mask(frame).tolist() == [True, False, False, False]


def test_confirmation_status_distinguishes_double_confirmed_and_morning_only():
    from strategies.ecms.volume_gainers import _confirmation_status

    assert _confirmation_status(True, True, True) == "DOUBLE_CONFIRMED_EOD_MORNING"
    assert _confirmation_status(False, True, True) == "UNDER_OBSERVATION_MORNING"
    assert _confirmation_status(True, True, False) == "EOD_STRONG_MORNING_NOT_CONFIRMED"
    assert _confirmation_status(True, False, False) == "STRONG_EOD_DISAPPEARED_MORNING"



def test_morning_reassesses_every_current_candidate_and_marks_double_confirmation(tmp_path, monkeypatch):
    import json
    from datetime import date
    from pathlib import Path
    import strategies.ecms.volume_gainers as scanner

    state_path = tmp_path / "state" / "volume_gainers_previous_eod.csv"
    output_dir = tmp_path / "outputs" / "ecms"
    state_path.parent.mkdir(parents=True)
    pd.DataFrame([{
        "TckrSymb": "AAA", "CompanyName": "AAA Ltd", "PageVolume": 100,
        "LTP": 10, "EODDate": "2026-11-13",
        "EODFundamentalShortlistStatus": "PASS",
        "EODFundamentalResearchClassification": "STRONG",
        "EODFundamentalResearchScore": 82,
        "EODFundamentalResearchCoveragePct": 90,
        "EODStrongFundamentalStatus": "STRONG_EOD",
    }]).to_csv(state_path, index=False)

    monkeypatch.setattr(scanner, "STATE_FILE", state_path)
    monkeypatch.setattr(scanner, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(scanner, "is_trading_session", lambda _day: True)
    monkeypatch.setattr(scanner, "expected_latest_completed_session", lambda: date(2026, 11, 13))
    monkeypatch.setattr(scanner, "fetch_volume_gainers", lambda: pd.DataFrame([
        {"TckrSymb": "AAA", "CompanyName": "AAA Ltd", "PageVolume": 120, "LTP": 11, "ChangePct": 5},
        {"TckrSymb": "BBB", "CompanyName": "BBB Ltd", "PageVolume": 90, "LTP": 8, "ChangePct": 3},
    ]))
    monkeypatch.setattr(scanner, "load_official_mainboard_symbols", lambda: ({"AAA", "BBB"}, "test-mainboard"))
    assessed_symbols = []

    def fake_assess(candidates, asof_date):
        assessed_symbols.extend(candidates["TckrSymb"].tolist())
        result = candidates.copy()
        result["FundamentalShortlistStatus"] = "PASS"
        result["FundamentalResearchClassification"] = "STRONG"
        result["FundamentalResearchScore"] = 80.0
        result["FundamentalResearchCoveragePct"] = 85.0
        return result

    monkeypatch.setattr(scanner, "assess_page_fundamentals", fake_assess)
    summary = scanner.run_morning()

    assert set(assessed_symbols) == {"AAA", "BBB"}
    report = pd.read_csv(output_dir / "volume_gainers_morning_recheck.csv").set_index("TckrSymb")
    assert report.loc["AAA", "ConfirmationStatus"] == "DOUBLE_CONFIRMED_EOD_MORNING"
    assert report.loc["BBB", "ConfirmationStatus"] == "UNDER_OBSERVATION_MORNING"
    assert summary["double_confirmed"] == 1
    assert summary["under_observation"] == 1
    saved_summary = json.loads((output_dir / "volume_gainers_morning_summary.json").read_text())
    assert saved_summary["morning_strong"] == 2
