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

    def fake_collect(candidates, metrics_path, enabled, asof_date, free_source_fetcher=None, force_retry_incomplete=False, free_source_audit_metrics=None):
        assert enabled is True
        assert callable(free_source_fetcher)
        assert force_retry_incomplete is True
        assert free_source_audit_metrics == [
            "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
            "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
        ]
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


def test_fundamental_pass_is_the_only_morning_gate_even_if_other_scores_are_weak():
    from strategies.ecms.volume_gainers import _strong_fundamental_mask

    frame = pd.DataFrame({
        "FundamentalShortlistStatus": ["PASS", "PASS", "FAIL", "WAIT_FOR_DATA"],
        "FundamentalResearchClassification": ["WEAK", "INSUFFICIENT_DATA", "STRONG", "STRONG"],
        "FundamentalResearchCoveragePct": [0, 1, 100, 100],
        "RVOL": [0.1, None, 10, 20],
        "CatalystStatus": ["NEGATIVE", "WAIT_FOR_DATA", "FOUND", "FOUND"],
    })
    assert _strong_fundamental_mask(frame).tolist() == [True, True, False, False]


def test_confirmation_status_uses_only_fundamental_pass_and_presence():
    from strategies.ecms.volume_gainers import _confirmation_status

    assert _confirmation_status(True, True, True) == "DOUBLE_CONFIRMED_EOD_MORNING"
    assert _confirmation_status(False, True, True) == "MORNING_FUNDAMENTAL_PASS"
    assert _confirmation_status(True, True, False) == "EOD_PASS_MORNING_NOT_PASS"
    assert _confirmation_status(True, False, False) == "EOD_PASS_NOT_ON_MORNING_PAGE"



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
        "EODStrongFundamentalStatus": "EOD_FUNDAMENTAL_PASS",
    }]).to_csv(state_path, index=False)
    original_eod_snapshot = state_path.read_bytes()

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
    def fake_information(frame, as_of_date):
        result = frame.copy()
        result["ValuationLabel"] = "NOT AVAILABLE"
        result["Last5DayNews"] = "NO_NEWS_FOUND"
        result["UpcomingEventsStatus"] = "NO_CONFIRMED_UPCOMING_EVENTS"
        result["UpcomingEvents"] = ""
        result["NextResultDate"] = "NOT ANNOUNCED"
        result["BulkBlockDealStatus"] = "NO_DISCLOSED_DEALS_IN_LOOKBACK"
        result["BulkDealCount"] = 0
        result["BlockDealCount"] = 0
        return result, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    monkeypatch.setattr(scanner, "attach_information", fake_information)
    summary = scanner.run_morning()

    assert set(assessed_symbols) == {"AAA", "BBB"}
    report = pd.read_csv(output_dir / "volume_gainers_morning_recheck.csv").set_index("TckrSymb")
    assert report.loc["AAA", "ConfirmationStatus"] == "DOUBLE_CONFIRMED_EOD_MORNING"
    assert report.loc["BBB", "ConfirmationStatus"] == "MORNING_FUNDAMENTAL_PASS"
    assert report.loc["AAA", "MorningStatus"] == "EOD_FUNDAMENTAL_PASS_REPEAT"
    assert report.loc["BBB", "MorningStatus"] == "NEW_MORNING_ENTRY"
    assert report.loc["AAA", "PagePresenceConfirmationStatus"] == "DOUBLE_CONFIRMED_EOD_MORNING"
    assert report.loc["BBB", "PagePresenceConfirmationStatus"] == "NEW_MORNING_ENTRY"
    assert report.loc["AAA", "PagePresenceDoubleConfirmed"]
    assert summary["page_presence_double_confirmed"] == 1
    assert state_path.read_bytes() == original_eod_snapshot
    assert summary["double_confirmed"] == 1
    assert summary["eod_fundamental_pass_repeats"] == 1
    saved_summary = json.loads((output_dir / "volume_gainers_morning_summary.json").read_text())
    assert saved_summary["morning_fundamental_pass"] == 2


def test_page_presence_confirmation_is_independent_of_fundamental_status():
    from strategies.ecms.volume_gainers import _page_presence_confirmation_status

    assert _page_presence_confirmation_status(True, True) == "DOUBLE_CONFIRMED_EOD_MORNING"
    assert _page_presence_confirmation_status(True, False) == "EOD_ONLY_NOT_ON_MORNING_PAGE"
    assert _page_presence_confirmation_status(False, True) == "NEW_MORNING_ENTRY"
    assert _page_presence_confirmation_status(False, False) == "NOT_PRESENT"


def test_eod_snapshot_is_atomically_saved_with_current_run_marker(tmp_path, monkeypatch):
    import json
    from datetime import date
    import strategies.ecms.volume_gainers as scanner

    state_dir = tmp_path / "data" / "cache" / "ecms"
    state_file = state_dir / "volume_gainers_previous_eod.csv"
    monkeypatch.setattr(scanner, "STATE_DIR", state_dir)
    monkeypatch.setattr(scanner, "STATE_FILE", state_file)
    monkeypatch.setenv("GITHUB_RUN_ID", "test-run-123")
    frame = pd.DataFrame([{
        "TckrSymb": "AAA", "CompanyName": "AAA Ltd", "PageVolume": 123,
        "LTP": 10.5, "ChangePct": 2.0,
    }])

    state = scanner._save_eod_snapshot(frame, date(2026, 11, 13))

    assert state_file.exists()
    saved = pd.read_csv(state_file, dtype={"TckrSymb": str})
    assert saved.loc[0, "TckrSymb"] == "AAA"
    assert saved.loc[0, "EODDate"] == "2026-11-13"
    assert saved.loc[0, "SnapshotType"] == "EOD"
    assert saved.loc[0, "SnapshotStatus"] == "VALID"
    assert saved.loc[0, "EODFundamentalShortlistStatus"] == "NOT_ASSESSED"
    marker = json.loads((state_dir / "eod_snapshot_run_marker.json").read_text())
    assert marker["github_run_id"] == "test-run-123"
    assert marker["symbol_count"] == 1
    assert marker["eod_date"] == "2026-11-13"


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


def test_attach_information_enriches_only_fundamental_pass_symbols(monkeypatch):
    import strategies.ecms.volume_gainers as scanner

    calls = {"news": [], "events": [], "deals": []}

    def fake_news(candidates, as_of_date):
        calls["news"] = candidates["TckrSymb"].tolist()
        news = pd.DataFrame([{
            "TckrSymb": "AAA", "PublishedDate": "2026-11-14",
            "Headline": "AAA announces contract", "Source": "NSE",
        }])
        audit = pd.DataFrame([{
            "TckrSymb": "AAA", "NewsWindowStart": "2026-11-10",
            "NewsWindowEnd": "2026-11-14", "OfficialStatus": "AVAILABLE",
            "SecondaryStatus": "AVAILABLE", "CatalystStatus": "CATALYST_FOUND",
            "CatalystSignalStatus": "NEWS_FOUND_NO_STRONG_CATALYST",
            "StrongCatalystCount": 0, "NegativeRiskCount": 0,
            "OfficialCount": 1, "SecondaryCount": 0,
        }])
        return news, audit

    def fake_events(symbols, as_of_date):
        calls["events"] = list(symbols)
        return pd.DataFrame(), pd.DataFrame([{
            "TckrSymb": "AAA", "UpcomingEventsStatus": "AVAILABLE",
            "UpcomingEvents": "2026-11-20: Investor Meet",
            "NextResultDate": "NOT ANNOUNCED", "NextResultDetails": "",
            "EventCalendarSourceURL": "https://www.nseindia.com/",
        }])

    def fake_deals(symbols, as_of_date):
        calls["deals"] = list(symbols)
        return pd.DataFrame(), pd.DataFrame([{
            "TckrSymb": "AAA", "BulkBlockDealStatus": "AVAILABLE",
            "BulkDealCount": 1, "BlockDealCount": 0,
            "BulkBuyers": "Fund Alpha", "BulkSellers": "",
            "BlockBuyers": "", "BlockSellers": "",
            "BulkBlockDealSummary": "BULK 2026-11-14 BUY Fund Alpha qty=100 price=10",
            "BulkBlockLookbackStart": "2026-10-16",
            "BulkBlockLookbackEnd": "2026-11-14",
            "BulkBlockSourceURL": "https://www.nseindia.com/",
        }])

    monkeypatch.setattr(scanner, "collect_catalysts", fake_news)
    monkeypatch.setattr(scanner, "collect_upcoming_events", fake_events)
    monkeypatch.setattr(scanner, "collect_bulk_block_deals", fake_deals)
    monkeypatch.setattr(scanner, "attach_valuation", lambda frame: frame.assign(
        ValuationLabel="FAIR", ValuationBasis="TEST"
    ))

    result, news, events, deals = scanner.attach_information(pd.DataFrame([
        {"TckrSymb": "AAA", "FundamentalShortlistStatus": "PASS"},
        {"TckrSymb": "BBB", "FundamentalShortlistStatus": "FAIL"},
    ]), __import__("datetime").date(2026, 11, 14))

    assert calls == {"news": ["AAA"], "events": ["AAA"], "deals": ["AAA"]}
    rows = result.set_index("TckrSymb")
    assert rows.loc["AAA", "UpcomingEventsStatus"] == "AVAILABLE"
    assert rows.loc["AAA", "BulkBlockDealStatus"] == "AVAILABLE"
    assert rows.loc["AAA", "Last5DayNews"].startswith("2026-11-14:")
    assert rows.loc["BBB", "CatalystStatus"] == "NOT_COLLECTED_FUNDAMENTAL_NOT_PASS"
    assert rows.loc["BBB", "BulkBlockDealStatus"] == "NOT_COLLECTED_FUNDAMENTAL_NOT_PASS"


def test_attach_information_handles_zero_fundamental_pass_without_missing_columns(monkeypatch):
    import strategies.ecms.volume_gainers as scanner

    def unexpected_call(*args, **kwargs):
        raise AssertionError("Informational feeds must not run when there are no Fundamental PASS stocks")

    monkeypatch.setattr(scanner, "collect_catalysts", unexpected_call)
    monkeypatch.setattr(scanner, "collect_upcoming_events", unexpected_call)
    monkeypatch.setattr(scanner, "collect_bulk_block_deals", unexpected_call)
    monkeypatch.setattr(scanner, "attach_valuation", lambda frame: frame.assign(
        ValuationLabel="NOT AVAILABLE", ValuationBasis="INSUFFICIENT_DATA"
    ))

    assessed = pd.DataFrame([
        {"TckrSymb": "AAA", "FundamentalShortlistStatus": "FAIL"},
        {"TckrSymb": "BBB", "FundamentalShortlistStatus": "WAIT_FOR_DATA"},
    ])
    result, news, events, deals = scanner.attach_information(
        assessed, __import__("datetime").date(2026, 11, 13)
    )

    assert result["UpcomingEventsStatus"].tolist() == [
        "NOT_COLLECTED_FUNDAMENTAL_NOT_PASS",
        "NOT_COLLECTED_FUNDAMENTAL_NOT_PASS",
    ]
    assert result["UpcomingEvents"].eq("NOT COLLECTED_FUNDAMENTAL_NOT_PASS").all()
    assert result["NextResultDate"].eq("NOT COLLECTED_FUNDAMENTAL_NOT_PASS").all()
    assert result["BulkBlockDealStatus"].eq("NOT_COLLECTED_FUNDAMENTAL_NOT_PASS").all()
    assert result["BulkDealCount"].eq(0).all()
    assert result["BlockDealCount"].eq(0).all()
    assert result["Last5DayNews"].eq("NOT COLLECTED_FUNDAMENTAL_NOT_PASS").all()
    assert result["FundamentalShortlistStatus"].tolist() == ["FAIL", "WAIT_FOR_DATA"]
    assert news.empty and events.empty and deals.empty
