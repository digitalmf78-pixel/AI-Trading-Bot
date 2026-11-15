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
        # Simulate a persistent ECMS workspace containing an older symbol
        # that is not on the current Volume Gainers page.
        pd.DataFrame([
            {"TckrSymb": "AAA", "RevenueGrowthPct": 20},
            {"TckrSymb": "OLD", "RevenueGrowthPct": 99},
        ]).to_csv(path, index=False)
        filings = Path("outputs/v8_official_financial_results_filings.csv")
        filings.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([
            {"TckrSymb": "AAA", "FinancialPeriodEnd": "2026-03-31"},
            {"TckrSymb": "OLD", "FinancialPeriodEnd": "2026-03-31"},
        ]).to_csv(filings, index=False)
        evidence = Path("data/inputs/fundamental_metric_verification_evidence.csv")
        evidence.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([
            {"TckrSymb": "AAA", "EvidenceFilePath": ""},
            {"TckrSymb": "OLD", "EvidenceFilePath": ""},
        ]).to_csv(evidence, index=False)
        diagnostics = Path("outputs/v8_fundamental_provider_diagnostics.csv")
        diagnostics.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([
            {"TckrSymb": "AAA", "ProviderStatus": "PASS"},
            {"TckrSymb": "OLD", "ProviderStatus": "STALE"},
        ]).to_csv(diagnostics, index=False)

    fake_provider = types.ModuleType("fundamental_data_provider")
    fake_provider.collect_missing_fundamentals = fake_collect
    monkeypatch.setitem(sys.modules, "fundamental_data_provider", fake_provider)

    def fake_audit(**kwargs):
        # Audit inputs must be scoped to the current page candidate, even
        # though the persistent cache still contains the older OLD symbol.
        assert set(pd.read_csv(kwargs["metrics_path"])["TckrSymb"]) == {"AAA"}
        assert set(pd.read_csv(kwargs["filings_path"])["TckrSymb"]) == {"AAA"}
        assert set(pd.read_csv(kwargs["evidence_path"])["TckrSymb"]) == {"AAA"}
        verification = pd.DataFrame([{
            "TckrSymb": "AAA",
            "MetricName": "RevenueGrowthPct",
            "MetricValueVerificationStatus": "OFFICIAL_XBRL_VERIFIED",
        }])
        return verification, pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(scanner, "run_fundamental_xbrl_audit", fake_audit)

    def fake_debt_equity_audit(**kwargs):
        assert set(kwargs["metrics"]["TckrSymb"]) == {"AAA"}
        assert set(kwargs["filings"]["TckrSymb"]) == {"AAA"}
        return pd.DataFrame([{
            "TckrSymb": "AAA",
            "DebtToEquityAuditStatus": "PROVIDER_DEBT_TO_EQUITY_MISSING",
            "DebtToEquityAuditReason": "Provider ratio missing",
        }])

    monkeypatch.setattr(scanner, "audit_ecms_debt_to_equity", fake_debt_equity_audit)

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
    # Keep stale cache rows for future safe reuse, but exclude them from this
    # run's audit inputs and all candidate-facing artifact snapshots.
    assert set(pd.read_csv(workspace_metrics)["TckrSymb"]) == {"AAA", "OLD"}
    assert not (tmp_path / "data/inputs/production_metrics.csv").exists()
    assert result.iloc[0]["FundamentalShortlistStatus"] == "PASS"
    out = tmp_path / "outputs/ecms"
    assert set(pd.read_csv(out / "fundamental_metrics_ecms.csv")["TckrSymb"]) == {"AAA"}
    assert set(pd.read_csv(out / "fundamental_filings_ecms.csv")["TckrSymb"]) == {"AAA"}
    assert set(pd.read_csv(out / "fundamental_evidence_ecms.csv")["TckrSymb"]) == {"AAA"}
    assert set(pd.read_csv(out / "fundamental_provider_diagnostics.csv")["TckrSymb"]) == {"AAA"}
    debt_equity_report = pd.read_csv(out / "fundamental_debt_equity_xbrl_audit.csv")
    assert debt_equity_report.iloc[0]["TckrSymb"] == "AAA"
    assert debt_equity_report.iloc[0]["DebtToEquityAuditStatus"] == "PROVIDER_DEBT_TO_EQUITY_MISSING"



def test_ecms_free_source_budget_expands_to_cover_every_current_candidate(tmp_path, monkeypatch):
    import os
    import sys
    import types
    from pathlib import Path
    import strategies.ecms.volume_gainers as scanner

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(scanner, "OUTPUT_DIR", Path("outputs/ecms"))
    monkeypatch.setattr(scanner, "STATE_DIR", Path("data/cache/ecms"))
    monkeypatch.setattr(scanner, "METRICS_PATH", Path("data/inputs/production_metrics.csv"))
    monkeypatch.setenv("FREE_FUNDAMENTAL_MAX_SYMBOLS_PER_RUN", "1")

    def fake_collect(candidates, **kwargs):
        assert len(candidates) == 2
        assert os.environ["FREE_FUNDAMENTAL_MAX_SYMBOLS_PER_RUN"] == "2"
        raise RuntimeError("stop after verifying ECMS-scoped budget")

    fake_provider = types.ModuleType("fundamental_data_provider")
    fake_provider.collect_missing_fundamentals = fake_collect
    monkeypatch.setitem(sys.modules, "fundamental_data_provider", fake_provider)

    result = scanner.assess_page_fundamentals(
        pd.DataFrame([
            {"TckrSymb": "AAA", "CompanyName": "AAA Limited"},
            {"TckrSymb": "BBB", "CompanyName": "BBB Limited"},
        ]),
        __import__("datetime").date(2026, 11, 13),
    )

    assert set(result["TckrSymb"]) == {"AAA", "BBB"}
    assert result["FundamentalShortlistStatus"].eq("WAIT_FOR_DATA").all()
    assert os.environ["FREE_FUNDAMENTAL_MAX_SYMBOLS_PER_RUN"] == "1"
    assert (tmp_path / "outputs/ecms/fundamental_collection_error.csv").exists()


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


def test_ecms_free_source_evidence_preserves_historical_alternates_when_latest_attempt_empty():
    from strategies.ecms.volume_gainers import _ecms_free_source_evidence

    row = pd.Series({
        "FreeSourcesStatus": "EMPTY_OR_UNMAPPED",
        "FreeSourcesAlternatesJSON": (
            '{"GrossMarginPct":[{"source":"Moneycontrol","value":42.5}],'
            '"OperatingMarginPct":[{"source":"Moneycontrol","value":18.2}]}'
        ),
    })
    result = _ecms_free_source_evidence(row)
    assert result["ECMSFreeSourcesEvidenceStatus"] == "HISTORICAL_ALTERNATES_PRESENT_NO_CURRENT_METRICS"
    assert result["ECMSFreeSourcesObservedMetricCount"] == 2
    assert result["ECMSFreeSourcesObservedMetrics"] == "GrossMarginPct;OperatingMarginPct"
    # Do not change the source cache's original status: this is an ECMS audit overlay.
    assert row["FreeSourcesStatus"] == "EMPTY_OR_UNMAPPED"


def test_ecms_free_source_evidence_reports_no_alternates_without_inventing_data():
    from strategies.ecms.volume_gainers import _ecms_free_source_evidence

    result = _ecms_free_source_evidence(pd.Series({
        "FreeSourcesStatus": "EMPTY_OR_UNMAPPED",
        "FreeSourcesAlternatesJSON": "{}",
    }))
    assert result["ECMSFreeSourcesEvidenceStatus"] == "EMPTY_OR_UNMAPPED"
    assert result["ECMSFreeSourcesObservedMetricCount"] == 0
    assert result["ECMSFreeSourcesObservedMetrics"] == ""


def test_ecms_debt_equity_exact_xbrl_audit_bridges_into_strict_verification_only():
    from strategies.ecms.volume_gainers import _merge_ecms_debt_equity_verification

    verification = pd.DataFrame([
        {"TckrSymb": "AAA", "MetricName": "DebtToEquity",
         "MetricValueVerificationStatus": "DERIVED_RECONCILIATION_REQUIRED"},
        {"TckrSymb": "AAA", "MetricName": "RevenueGrowthPct",
         "MetricValueVerificationStatus": "OFFICIAL_XBRL_VERIFIED"},
        {"TckrSymb": "BBB", "MetricName": "DebtToEquity",
         "MetricValueVerificationStatus": "DERIVED_RECONCILIATION_REQUIRED"},
    ])
    debt_audit = pd.DataFrame([
        {"TckrSymb": "AAA", "DebtToEquityAuditStatus": "OFFICIAL_XBRL_VERIFIED",
         "ProviderDebtToEquity": 0.5, "OfficialDebtToEquity": 0.5,
         "EvidenceFilePath": "data/cache/ecms_debt_equity_xbrl/a.xml",
         "EvidenceSHA256": "a" * 64,
         "DebtToEquityAuditReason": "Exact same-context XBRL match"},
        {"TckrSymb": "BBB", "DebtToEquityAuditStatus": "PROVIDER_VALUE_MISMATCH",
         "ProviderDebtToEquity": 0.8, "OfficialDebtToEquity": 0.5},
    ])

    result = _merge_ecms_debt_equity_verification(verification, debt_audit)
    aaa_de = result[(result["TckrSymb"] == "AAA") & (result["MetricName"] == "DebtToEquity")]
    bbb_de = result[(result["TckrSymb"] == "BBB") & (result["MetricName"] == "DebtToEquity")]

    assert len(aaa_de) == 1
    assert aaa_de.iloc[0]["MetricValueVerificationStatus"] == "OFFICIAL_XBRL_VERIFIED"
    assert aaa_de.iloc[0]["OfficialMetricValue"] == 0.5
    assert len(bbb_de) == 1
    assert bbb_de.iloc[0]["MetricValueVerificationStatus"] == "DERIVED_RECONCILIATION_REQUIRED"
    assert len(result[(result["TckrSymb"] == "AAA") & (result["MetricName"] == "RevenueGrowthPct")]) == 1
