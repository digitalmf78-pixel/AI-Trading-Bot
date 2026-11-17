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
        # Preserve provider cooldown so cached incomplete rows are not refetched every scan.
        assert force_retry_incomplete is False
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


def test_fundamental_pass_indicator_is_not_the_overall_morning_gate():
    from strategies.ecms.volume_gainers import _strong_fundamental_mask

    frame = pd.DataFrame({
        "FundamentalShortlistStatus": ["PASS", "PASS", "FAIL", "WAIT_FOR_DATA"],
        "FundamentalResearchClassification": ["WEAK", "INSUFFICIENT_DATA", "STRONG", "STRONG"],
        "FundamentalResearchCoveragePct": [0, 1, 100, 100],
        "RVOL": [0.1, None, 10, 20],
        "CatalystStatus": ["NEGATIVE", "WAIT_FOR_DATA", "FOUND", "FOUND"],
    })
    # This mask reports only the fundamental layer's PASS state.
    assert _strong_fundamental_mask(frame).tolist() == [True, True, False, False]


def test_incomplete_fundamentals_continue_to_balanced_research():
    from strategies.ecms.volume_gainers import _fundamental_decision_fields

    passed = _fundamental_decision_fields("PASS")
    failed = _fundamental_decision_fields("FAIL")
    waiting = _fundamental_decision_fields("WAIT_FOR_DATA")
    collection_error = _fundamental_decision_fields("")

    assert passed["ResearchContinuationStatus"] == "CONTINUE_BALANCED_RESEARCH"
    assert passed["StrongFundamentalHandOffStatus"] == "FORWARDED_TO_BALANCED_RESEARCH"
    assert failed["ResearchContinuationStatus"] == "FUNDAMENTAL_REJECTION_GATE"
    assert failed["StrongFundamentalHandOffStatus"] == "REJECTED_BY_VERIFIED_FUNDAMENTALS"
    assert waiting["FundamentalDecisionRole"] == "FUNDAMENTAL_PENDING_OTHER_RESEARCH_CONTINUES"
    assert waiting["ResearchContinuationStatus"] == "CONTINUE_BALANCED_RESEARCH"
    assert waiting["StrongFundamentalHandOffStatus"] == "FORWARDED_PENDING_FUNDAMENTAL_DATA"
    assert waiting["StrongFundamentalNotForwardedReason"] == ""
    assert collection_error["ResearchContinuationStatus"] == "CONTINUE_BALANCED_RESEARCH"


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
    morning_state_path = tmp_path / "state" / "volume_gainers_same_day_morning.csv"
    consumed_marker_path = tmp_path / "state" / "volume_gainers_previous_eod_consumed.json"
    output_dir = tmp_path / "outputs" / "ecms"
    state_path.parent.mkdir(parents=True)
    pd.DataFrame([{
        "TckrSymb": "AAA", "CompanyName": "AAA Ltd", "PageVolume": 100,
        "LTP": 10, "EODDate": "2026-11-13",
        "EODFundamentalShortlistStatus": "PASS",
        "EODStrongFundamentalStatus": "EOD_FUNDAMENTAL_PASS",
    }]).to_csv(state_path, index=False)

    monkeypatch.setattr(scanner, "STATE_FILE", state_path)
    monkeypatch.setattr(scanner, "STATE_DIR", state_path.parent)
    monkeypatch.setattr(scanner, "MORNING_STATE_FILE", morning_state_path)
    monkeypatch.setattr(scanner, "CONSUMED_EOD_MARKER_FILE", consumed_marker_path)
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
        return result, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    monkeypatch.setattr(scanner, "attach_information", fake_information)
    summary = scanner.run_morning()

    assert set(assessed_symbols) == {"AAA", "BBB"}
    report = pd.read_csv(output_dir / "volume_gainers_morning_recheck.csv").set_index("TckrSymb")
    assert report.loc["AAA", "ConfirmationStatus"] == "DOUBLE_CONFIRMED_EOD_MORNING"
    assert report.loc["BBB", "ConfirmationStatus"] == "MORNING_FUNDAMENTAL_PASS"
    assert report.loc["AAA", "MorningStatus"] == "EOD_AND_MORNING_PAGE_REPEAT"
    assert report.loc["AAA", "PagePresenceConfirmationStatus"] == "DOUBLE_CONFIRMED_EOD_MORNING"
    assert report.loc["AAA", "FundamentalConfirmationStatus"] == "DOUBLE_CONFIRMED_EOD_MORNING"
    assert report.loc["BBB", "MorningStatus"] == "NEW_MORNING_ENTRY"
    assert report.loc["AAA", "PagePresenceConfirmationStatus"] == "DOUBLE_CONFIRMED_EOD_MORNING"
    assert report.loc["BBB", "PagePresenceConfirmationStatus"] == "NEW_MORNING_ENTRY"
    assert report.loc["AAA", "PagePresenceDoubleConfirmed"]
    assert summary["page_presence_double_confirmed"] == 1
    assert summary["previous_eod_reference_consumed"] is True
    assert json.loads(consumed_marker_path.read_text())["consumed_eod_date"] == "2026-11-13"
    assert summary["same_day_morning_snapshot_saved"] is True
    assert morning_state_path.exists()
    assert not state_path.exists()
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


def test_attach_information_researches_every_symbol_regardless_of_fundamental_status(monkeypatch):
    import strategies.ecms.volume_gainers as scanner

    calls = {"news": [], "events": [], "deals": [], "corporate_actions": []}

    def fake_news(candidates, as_of_date):
        calls["news"] = candidates["TckrSymb"].tolist()
        news = pd.DataFrame([{
            "TckrSymb": "AAA", "PublishedDate": "2026-11-14",
            "Headline": "AAA announces dividend record date", "Source": "NSE", "SourceType": "OFFICIAL",
        }])
        audit = pd.DataFrame([
            {"TckrSymb": symbol, "NewsWindowStart": "2026-11-10",
             "NewsWindowEnd": "2026-11-14", "OfficialStatus": "AVAILABLE",
             "SecondaryStatus": "AVAILABLE",
             "CatalystStatus": "CATALYST_FOUND" if symbol == "AAA" else "NO_NEWS_FOUND",
             "CatalystSignalStatus": "NEWS_FOUND_NO_STRONG_CATALYST",
             "StrongCatalystCount": 0, "NegativeRiskCount": 0,
             "OfficialCount": 1 if symbol == "AAA" else 0, "SecondaryCount": 0}
            for symbol in calls["news"]
        ])
        return news, audit

    def fake_events(symbols, as_of_date):
        calls["events"] = list(symbols)
        return pd.DataFrame(), pd.DataFrame([
            {"TckrSymb": symbol, "UpcomingEventsStatus": "AVAILABLE" if symbol == "AAA" else "NO_CONFIRMED_UPCOMING_EVENTS",
             "UpcomingEvents": "2026-11-20: Investor Meet" if symbol == "AAA" else "",
             "NextResultDate": "NOT ANNOUNCED", "NextResultDetails": "",
             "EventCalendarSourceURL": "https://www.nseindia.com/"}
            for symbol in symbols
        ])

    def fake_deals(symbols, as_of_date):
        calls["deals"] = list(symbols)
        return pd.DataFrame(), pd.DataFrame([
            {"TckrSymb": symbol, "BulkBlockDealStatus": "NO_DISCLOSED_DEALS_IN_LOOKBACK",
             "BulkDealCount": 0, "BlockDealCount": 0,
             "BulkDealCountLast5Days": 0, "BlockDealCountLast5Days": 0,
             "BulkBlockSummaryLast5Days": "",
             "BulkBuyers": "", "BulkSellers": "", "BlockBuyers": "", "BlockSellers": "",
             "BulkBlockDealSummary": "", "BulkBlockLookbackStart": "2026-10-16",
             "BulkBlockLookbackEnd": "2026-11-14", "BulkBlockSourceURL": "https://www.nseindia.com/"}
            for symbol in symbols
        ])

    monkeypatch.setattr(scanner, "collect_catalysts", fake_news)
    monkeypatch.setattr(scanner, "collect_upcoming_events", fake_events)
    monkeypatch.setattr(scanner, "collect_bulk_block_deals", fake_deals)
    def fake_corporate_actions(symbols, as_of_date):
        calls["corporate_actions"] = list(symbols)
        audit = pd.DataFrame([
            {"TckrSymb": symbol, "CorporateActionsStatus": "DATA_FOUND" if symbol == "AAA" else "NO_DATA_FOUND",
             "CorporateActionCount": 1 if symbol == "AAA" else 0,
             "CorporateActionSummary": "2026-11-20: Dividend" if symbol == "AAA" else "",
             "CorporateActionWindowStart": "2026-11-10", "CorporateActionWindowEnd": "2027-02-12",
             "CorporateActionSourceURL": "https://www.nseindia.com/"}
            for symbol in symbols
        ])
        return pd.DataFrame(), audit
    monkeypatch.setattr(scanner, "collect_corporate_actions", fake_corporate_actions)
    monkeypatch.setattr(scanner, "attach_valuation", lambda frame: frame.assign(
        ValuationLabel="FAIR", ValuationBasis="TEST"
    ))

    result, news, events, deals, corporate_actions = scanner.attach_information(pd.DataFrame([
        {"TckrSymb": "AAA", "FundamentalShortlistStatus": "PASS"},
        {"TckrSymb": "BBB", "FundamentalShortlistStatus": "FAIL"},
        {"TckrSymb": "CCC", "FundamentalShortlistStatus": "WAIT_FOR_DATA"},
    ]), __import__("datetime").date(2026, 11, 14))

    assert calls == {"news": ["AAA", "BBB", "CCC"],
                     "events": ["AAA", "BBB", "CCC"],
                     "deals": ["AAA", "BBB", "CCC"],
                     "corporate_actions": ["AAA", "BBB", "CCC"]}
    rows = result.set_index("TckrSymb")
    assert rows.loc["AAA", "UpcomingEventsStatus"] == "AVAILABLE"
    assert rows.loc["AAA", "NewsResearchStatus"] == "DATA_FOUND"
    assert rows.loc["AAA", "CorporateActionResearchStatus"] == "DATA_FOUND"
    assert rows.loc["AAA", "CorporateActionCount"] == 1
    assert rows.loc["BBB", "CorporateActionResearchStatus"] == "NO_DATA_FOUND"
    assert rows.loc["BBB", "NewsResearchStatus"] == "NO_DATA_FOUND"
    assert rows.loc["BBB", "UpcomingEventsResearchStatus"] == "NO_DATA_FOUND"
    assert rows.loc["CCC", "BulkBlockDealsResearchStatus"] == "NO_DATA_FOUND"
    assert rows.loc["AAA", "Last5DayNews"].startswith("2026-11-14:")
    assert rows.loc["BBB", "Last5DayNews"] == "NO_NEWS_FOUND"
    assert rows["FundamentalShortlistStatus"].tolist() == ["PASS", "FAIL", "WAIT_FOR_DATA"]


def test_attach_information_still_collects_all_sources_when_no_fundamental_pass(monkeypatch):
    import strategies.ecms.volume_gainers as scanner
    calls = {"news": 0, "events": 0, "deals": 0, "corporate_actions": 0}

    def fake_news(candidates, as_of_date):
        calls["news"] += len(candidates)
        return pd.DataFrame(), pd.DataFrame([
            {"TckrSymb": symbol, "CatalystStatus": "NO_NEWS_FOUND",
             "NewsWindowStart": "2026-11-09", "NewsWindowEnd": "2026-11-13",
             "OfficialStatus": "AVAILABLE", "SecondaryStatus": "AVAILABLE",
             "CatalystSignalStatus": "NO_CATALYST", "StrongCatalystCount": 0,
             "NegativeRiskCount": 0, "OfficialCount": 0, "SecondaryCount": 0}
            for symbol in candidates["TckrSymb"]
        ])

    def fake_events(symbols, as_of_date):
        calls["events"] += len(symbols)
        return pd.DataFrame(), pd.DataFrame([
            {"TckrSymb": symbol, "UpcomingEventsStatus": "NO_CONFIRMED_UPCOMING_EVENTS",
             "UpcomingEvents": "", "NextResultDate": "NOT ANNOUNCED",
             "NextResultDetails": "", "EventCalendarSourceURL": ""}
            for symbol in symbols
        ])

    def fake_deals(symbols, as_of_date):
        calls["deals"] += len(symbols)
        return pd.DataFrame(), pd.DataFrame([
            {"TckrSymb": symbol, "BulkBlockDealStatus": "NO_DISCLOSED_DEALS_IN_LOOKBACK",
             "BulkDealCount": 0, "BlockDealCount": 0,
             "BulkBuyers": "", "BulkSellers": "", "BlockBuyers": "", "BlockSellers": "",
             "BulkBlockDealSummary": "", "BulkBlockLookbackStart": "",
             "BulkBlockLookbackEnd": "", "BulkBlockSourceURL": ""}
            for symbol in symbols
        ])

    monkeypatch.setattr(scanner, "collect_catalysts", fake_news)
    monkeypatch.setattr(scanner, "collect_upcoming_events", fake_events)
    monkeypatch.setattr(scanner, "collect_bulk_block_deals", fake_deals)
    def fake_corporate_actions(symbols, as_of_date):
        calls["corporate_actions"] += len(symbols)
        return pd.DataFrame(), pd.DataFrame([
            {"TckrSymb": symbol, "CorporateActionsStatus": "NO_DATA_FOUND",
             "CorporateActionCount": 0, "CorporateActionSummary": "",
             "CorporateActionWindowStart": "", "CorporateActionWindowEnd": "",
             "CorporateActionSourceURL": ""}
            for symbol in symbols
        ])
    monkeypatch.setattr(scanner, "collect_corporate_actions", fake_corporate_actions)
    monkeypatch.setattr(scanner, "attach_valuation", lambda frame: frame.assign(
        ValuationLabel="NOT AVAILABLE", ValuationBasis="INSUFFICIENT_DATA"
    ))
    assessed = pd.DataFrame([
        {"TckrSymb": "AAA", "FundamentalShortlistStatus": "FAIL"},
        {"TckrSymb": "BBB", "FundamentalShortlistStatus": "WAIT_FOR_DATA"},
    ])
    result, news, events, deals, corporate_actions = scanner.attach_information(
        assessed, __import__("datetime").date(2026, 11, 13)
    )
    assert calls == {"news": 2, "events": 2, "deals": 2, "corporate_actions": 2}
    assert result["NewsResearchStatus"].eq("NO_DATA_FOUND").all()
    assert result["UpcomingEventsResearchStatus"].eq("NO_DATA_FOUND").all()
    assert result["BulkBlockDealsResearchStatus"].eq("NO_DATA_FOUND").all()
    assert result["FundamentalShortlistStatus"].tolist() == ["FAIL", "WAIT_FOR_DATA"]
    assert news.empty and events.empty and deals.empty


def test_same_day_morning_snapshot_is_reused_for_eod_confirmation(tmp_path, monkeypatch):
    import strategies.ecms.volume_gainers as scanner
    from datetime import date

    monkeypatch.setattr(scanner, "STATE_DIR", tmp_path)
    monkeypatch.setattr(scanner, "MORNING_STATE_FILE", tmp_path / "volume_gainers_same_day_morning.csv")
    monkeypatch.setenv("GITHUB_RUN_ID", "test-morning-run-123")
    morning = pd.DataFrame({
        "TckrSymb": ["AAA", "BBB"],
        "PageVolume": [120000, 90000],
        "MorningPageCapturedAtIST": ["2026-11-16T09:20:04+05:30", "2026-11-16T09:20:04+05:30"],
        "FundamentalShortlistStatus": ["PASS", "WAIT_FOR_DATA"],
        "Last5DayNews": ["Morning news A", "Morning news B"],
        "UpcomingEvents": ["AGM", "NOT AVAILABLE"],
        "NextResultDate": ["2026-11-25", "NOT ANNOUNCED"],
    })
    saved = scanner._save_same_day_morning_snapshot(morning, date(2026, 11, 16))
    assert saved["MorningRunId"].eq("test-morning-run-123").all()
    assert saved["MorningSnapshotStatus"].eq("VALID").all()

    eod = pd.DataFrame({
        "TckrSymb": ["AAA", "CCC"],
        "PageVolume": [300000, 50000],
        # The completed-session data date can differ from today's scan date
        # when an EOD-mode manual check runs before market close.
        "EODDate": ["2026-11-13", "2026-11-13"],
        "EODScanDate": ["2026-11-16", "2026-11-16"],
    })
    # Friday's completed data captured on Monday must not be compared with
    # Monday Morning, even though a valid Monday Morning snapshot exists.
    result = scanner._attach_same_day_morning_confirmation(
        eod, date(2026, 11, 16), eod_data_date=date(2026, 11, 13)
    ).set_index("TckrSymb")

    assert not result.loc["AAA", "MorningSeenSameDay"]
    assert result.loc["AAA", "MorningToEODStatus"] == "EOD_DATA_DATE_MISMATCH_NOT_COMPARED"
    assert result.loc["AAA", "MorningComparisonStatus"] == "STALE_EOD_DATA_NOT_COMPARED"
    assert result.loc["AAA", "MorningPageVolume"] == ""

    # Once the page reflects the current session date, the same snapshot is
    # eligible for a real same-day comparison.
    current = scanner._attach_same_day_morning_confirmation(
        eod, date(2026, 11, 16), eod_data_date=date(2026, 11, 16)
    ).set_index("TckrSymb")
    assert current.loc["AAA", "MorningSeenSameDay"]
    assert current.loc["AAA", "MorningToEODStatus"] == "MORNING_AND_EOD_REPEAT"
    assert current.loc["AAA", "MorningComparisonStatus"] == "COMPLETED"
    assert current.loc["AAA", "MorningPageVolume"] == 120000
    assert current.loc["AAA", "MorningScanTimeIST"] == "2026-11-16T09:20:04+05:30"
    assert current.loc["AAA", "MorningFundamentalStatus"] == "PASS"
    assert current.loc["AAA", "MorningNewsContext"] == "Morning news A"
    assert current.loc["CCC", "MorningToEODStatus"] == "EOD_NEW_ENTRY"


def test_same_day_morning_snapshot_rejects_wrong_date_and_bad_symbols(tmp_path, monkeypatch):
    import strategies.ecms.volume_gainers as scanner
    from datetime import date

    path = tmp_path / "volume_gainers_same_day_morning.csv"
    monkeypatch.setattr(scanner, "MORNING_STATE_FILE", path)
    monkeypatch.setattr(scanner, "STATE_DIR", tmp_path)
    scanner._save_same_day_morning_snapshot(
        pd.DataFrame({"TckrSymb": ["AAA"], "PageVolume": [100]}),
        date(2026, 11, 16),
    )
    assert scanner._load_same_day_morning_snapshot(date(2026, 11, 17)).empty

    pd.DataFrame({"TckrSymb": ["AAA", "AAA"], "MorningDate": ["2026-11-16"] * 2}).to_csv(path, index=False)
    assert scanner._load_same_day_morning_snapshot(date(2026, 11, 16)).empty


def test_morning_rejects_consumed_eod_resurrected_by_actions_cache(tmp_path, monkeypatch):
    import json
    from datetime import date
    import pytest
    import strategies.ecms.volume_gainers as scanner

    state_dir = tmp_path / "ecms"
    state_dir.mkdir()
    eod_state = state_dir / "volume_gainers_previous_eod.csv"
    consumed_marker = state_dir / "volume_gainers_previous_eod_consumed.json"
    pd.DataFrame([{
        "TckrSymb": "AAA", "EODDate": "2026-11-13",
        "SnapshotType": "EOD", "SnapshotStatus": "VALID",
    }]).to_csv(eod_state, index=False)
    consumed_marker.write_text(json.dumps({
        "consumed_eod_date": "2026-11-13",
        "status": "CONSUMED",
    }))
    monkeypatch.setattr(scanner, "STATE_FILE", eod_state)
    monkeypatch.setattr(scanner, "CONSUMED_EOD_MARKER_FILE", consumed_marker)
    monkeypatch.setattr(scanner, "is_trading_session", lambda _day: True)
    monkeypatch.setattr(scanner, "expected_latest_completed_session", lambda: date(2026, 11, 13))

    with pytest.raises(RuntimeError, match="already consumed"):
        scanner.run_morning()

def test_nse_calendar_special_weekend_session_and_unknown_year_fail_closed():
    import pytest
    from datetime import date
    from nse_trading_calendar import CalendarCoverageError, calendar_coverage_warnings, expected_scan_time, is_trading_session

    # The configured 2026 Muhurat session overrides the normal Sunday closure,
    # but uses its own scan times rather than regular 09:20/17:00 times.
    assert is_trading_session(date(2026, 11, 8))
    assert expected_scan_time(date(2026, 11, 8), "morning") == "14:25"
    assert expected_scan_time(date(2026, 11, 8), "eod") == "17:00"
    assert expected_scan_time(date(2026, 11, 16), "morning") == "09:20"
    assert expected_scan_time(date(2026, 11, 16), "eod") == "17:00"
    assert expected_scan_time(date(2026, 11, 10), "eod") is None
    assert any("2027" in warning for warning in calendar_coverage_warnings(date(2026, 11, 16)))
    with pytest.raises(CalendarCoverageError, match="not configured"):
        is_trading_session(date(2027, 1, 1))


def test_main_skips_special_session_scan_at_regular_clock_time(monkeypatch, capsys):
    import sys
    from datetime import datetime as real_datetime
    import strategies.ecms.volume_gainers as scanner

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 11, 8, 9, 20, tzinfo=tz)

    monkeypatch.setattr(scanner, "datetime", FixedDateTime)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    monkeypatch.setattr(sys, "argv", ["ecms-volume-gainers", "--mode", "morning"])
    scanner.main()
    output = capsys.readouterr().out
    assert '"status": "SKIPPED"' in output
    assert '"reason": "NOT_OFFICIAL_NSE_SESSION_SCAN_SLOT"' in output
    assert '"expected_time_ist": "14:25"' in output


def test_main_skips_when_official_nse_calendar_coverage_is_unavailable(monkeypatch, capsys):
    import sys
    from datetime import datetime as real_datetime
    import strategies.ecms.volume_gainers as scanner

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2027, 1, 1, 9, 20, tzinfo=tz)

    def unavailable(_day):
        raise scanner.CalendarCoverageError("WAIT_FOR_DATA: official NSE calendar not configured")

    monkeypatch.setattr(scanner, "datetime", FixedDateTime)
    monkeypatch.setattr(scanner, "is_trading_session", unavailable)
    monkeypatch.setattr(sys, "argv", ["ecms-volume-gainers", "--mode", "morning"])
    scanner.main()
    output = capsys.readouterr().out
    assert '"status": "SKIPPED"' in output
    assert '"reason": "OFFICIAL_NSE_CALENDAR_UNAVAILABLE"' in output


def test_main_skips_holiday_without_running_scan(monkeypatch, capsys):
    import sys
    from datetime import datetime as real_datetime
    import strategies.ecms.volume_gainers as scanner

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 11, 14, 9, 20, tzinfo=tz)

    monkeypatch.setattr(scanner, "datetime", FixedDateTime)
    monkeypatch.setattr(scanner, "is_trading_session", lambda day: False)
    monkeypatch.setattr(sys, "argv", ["ecms-volume-gainers", "--mode", "morning"])

    def unexpected_scan():
        raise AssertionError("scanner must not run on an NSE holiday")

    monkeypatch.setattr(scanner, "run_morning", unexpected_scan)
    scanner.main()
    output = capsys.readouterr().out
    assert '"status": "SKIPPED"' in output
    assert '"reason": "OFFICIAL_NSE_NON_TRADING_DAY"' in output
    assert '"mode": "MORNING"' in output


def test_eligible_page_equities_keeps_only_official_mainboard_symbols(monkeypatch):
    import strategies.ecms.volume_gainers as scanner

    monkeypatch.setattr(
        scanner,
        "load_official_mainboard_symbols",
        lambda: ({"MAIN1", "MAIN2"}, "official-nse-mainboard-minus-sme"),
    )
    page = pd.DataFrame({
        "TckrSymb": ["MAIN1", "SME1", "ETF1", "INDEX1", "MAIN2"],
        "Series": ["EQ", "SM", "ETF", "INDEX", "EQ"],
    })

    eligible, source = scanner._eligible_page_equities(page)

    assert eligible["TckrSymb"].tolist() == ["MAIN1", "MAIN2"]
    assert eligible["PageUniverseStatus"].eq("PASS_MAIN_BOARD_EQUITY").all()
    assert source == "official-nse-mainboard-minus-sme"



def test_volume_gainer_nse_sample_fields_are_mapped_to_correct_units():
    from strategies.ecms.volume_gainers import ALIASES, _get, _number

    row = {
        "volume": 35273385,
        "week1AvgVolume": 643349,
        "week1volChange": 54.82776067111319,
        "week2AvgVolume": 619266,
        "week2volChange": 56.959989729776865,
    }
    assert _number(_get(row, ALIASES["volume"])) == 35273385
    assert _number(_get(row, ALIASES["avg_volume_1w"])) == 643349
    assert _number(_get(row, ALIASES["change_pct_1w"])) == 54.82776067111319
    assert _number(_get(row, ALIASES["avg_volume_2w"])) == 619266
    assert _number(_get(row, ALIASES["change_pct_2w"])) == 56.959989729776865


def test_eod_uses_scan_date_for_research_and_morning_match_but_completed_date_for_rvol(tmp_path, monkeypatch):
    import strategies.ecms.volume_gainers as scanner
    from datetime import date, datetime as real_datetime

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 11, 16, 13, 7, tzinfo=tz)

    monkeypatch.setattr(scanner, "datetime", FixedDateTime)
    monkeypatch.setattr(scanner, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(scanner, "expected_latest_completed_session", lambda: date(2026, 11, 13))
    monkeypatch.setattr(scanner, "is_trading_session", lambda day: True)
    monkeypatch.setattr(scanner, "fetch_volume_gainers", lambda: pd.DataFrame({
        "TckrSymb": ["AAA"], "CompanyName": ["Alpha"], "PageVolume": [100],
        "PageVolumeDataStatus": ["DATA_FOUND"], "NSEServerDateIST": ["2026-11-16"],
    }))
    monkeypatch.setattr(scanner, "_eligible_page_equities", lambda page: (page.copy(), "TEST_MAINBOARD"))
    monkeypatch.setattr(scanner, "_save_eod_snapshot", lambda frame, day: frame)
    captured = {}

    def fake_rvol(frame, data_date):
        captured["rvol_date"] = data_date
        result = frame.copy()
        result["RVOL"] = [1.5]
        result["RVOLDataStatus"] = ["DATA_FOUND"]
        return result

    def fake_fundamentals(frame, as_of_date):
        captured["fundamental_date"] = as_of_date
        result = frame.copy()
        result["FundamentalShortlistStatus"] = ["WAIT_FOR_DATA"]
        return result

    def fake_information(frame, as_of_date):
        captured["information_date"] = as_of_date
        empty = pd.DataFrame()
        return frame.copy(), empty, empty, empty, empty

    def fake_morning_match(frame, morning_date, eod_data_date=None):
        captured["comparison_date"] = morning_date
        captured["comparison_data_date"] = eod_data_date
        result = frame.copy()
        current_data = eod_data_date == morning_date
        result["MorningSeenSameDay"] = [current_data]
        result["MorningToEODStatus"] = [
            "MORNING_AND_EOD_REPEAT" if current_data else "EOD_DATA_DATE_MISMATCH_NOT_COMPARED"
        ]
        return result

    monkeypatch.setattr(scanner, "attach_page_rvol", fake_rvol)
    monkeypatch.setattr(scanner, "assess_page_fundamentals", fake_fundamentals)
    monkeypatch.setattr(scanner, "attach_information", fake_information)
    monkeypatch.setattr(scanner, "_attach_same_day_morning_confirmation", fake_morning_match)
    monkeypatch.setattr(scanner, "_load_same_day_morning_snapshot", lambda day: pd.DataFrame({"TckrSymb": ["AAA"]}))

    summary = scanner.run_eod()

    assert captured == {
        "rvol_date": date(2026, 11, 13),
        "fundamental_date": date(2026, 11, 16),
        "information_date": date(2026, 11, 16),
        "comparison_date": date(2026, 11, 16),
        "comparison_data_date": date(2026, 11, 16),
    }
    assert summary["scan_date_ist"] == "2026-11-16"
    assert summary["page_session_date_ist"] == "2026-11-16"
    assert summary["bhavcopy_date_ist"] == "2026-11-13"
    assert summary["data_as_of_date_ist"] == "2026-11-13"
    assert summary["eod_data_current_for_scan_date"] is True
    assert summary["page_freshness_evidence"] == "NSE_API_HTTP_DATE_HEADER_MATCH"
    assert summary["data_freshness_status"] == "CURRENT_SESSION_PAGE_VERIFIED"
    assert summary["morning_comparison_status"] == "COMPLETED"
    assert summary["morning_comparison_performed"] is True



def test_verified_nse_page_session_date_requires_matching_server_date():
    import pytest
    from datetime import date
    from strategies.ecms.volume_gainers import _verified_nse_page_session_date

    page = pd.DataFrame({"NSEServerDateIST": ["2026-11-16", "2026-11-16"]})
    assert _verified_nse_page_session_date(page, date(2026, 11, 16)) == date(2026, 11, 16)
    with pytest.raises(RuntimeError, match="does not match scan date"):
        _verified_nse_page_session_date(
            pd.DataFrame({"NSEServerDateIST": ["2026-11-13"]}), date(2026, 11, 16)
        )
    with pytest.raises(RuntimeError, match="no verifiable server Date header"):
        _verified_nse_page_session_date(pd.DataFrame({"TckrSymb": ["AAA"]}), date(2026, 11, 16)
        )

def test_fetch_volume_gainers_maps_additional_quantity_alias_and_exposes_payload_schema():
    import strategies.ecms.volume_gainers as scanner

    class Response:
        def __init__(self, payload=None):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Session:
        def __init__(self):
            self.headers = {}
            self.calls = 0

        def get(self, url, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return Response({})
            return Response({"data": [{
                "symbol": "AAA",
                "companyName": "Alpha Limited",
                "totalTradedQuantity": "1,23,456",
                "week1AvgVolume": 12000,
                "week1volChange": 35.5,
            }]})

    result = scanner.fetch_volume_gainers(session=Session()).iloc[0]
    assert result["PageVolume"] == 123456
    assert result["PageVolumeSourceField"] == "totalTradedQuantity"
    assert "week1AvgVolume" in result["NSEPayloadKeys"]
    assert result["NSEPayloadVolumeLikeFields"] == "totalTradedQuantity|week1AvgVolume"



def test_nse_compact_page_volume_units_are_normalized_to_share_quantity():
    from strategies.ecms.volume_gainers import _volume_number

    assert _volume_number("23.91 L") == 2_391_000
    assert _volume_number("1.25 lakh") == 125_000
    assert _volume_number("0.42 Cr") == 4_200_000
    assert _volume_number("1.5K") == 1_500
    assert _volume_number("2,391,000") == 2_391_000
    assert _volume_number("-") is None
    assert _volume_number("not-a-number") is None


def test_fetch_volume_gainers_normalizes_compact_volume_and_keeps_raw_value():
    import strategies.ecms.volume_gainers as scanner

    class Response:
        def __init__(self, payload=None):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Session:
        def __init__(self):
            self.headers = {}
            self.calls = 0

        def get(self, url, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return Response({})
            return Response({"data": [{
                "symbol": "AAA",
                "companyName": "Alpha Limited",
                "volume": "23.91 L",
                "week1AvgVolume": "6.43 L",
            }]})

    row = scanner.fetch_volume_gainers(session=Session()).iloc[0]
    assert row["PageVolume"] == 2_391_000
    assert row["PageVolumeDataStatus"] == "DATA_FOUND"
    assert row["PageVolumeSourceField"] == "volume"
    assert row["PageVolumeRawValue"] == "23.91 L"



def test_eod_snapshot_marker_records_both_scan_date_and_data_date(tmp_path, monkeypatch):
    import json
    from datetime import date
    import strategies.ecms.volume_gainers as scanner

    state_dir = tmp_path / "ecms-state"
    monkeypatch.setattr(scanner, "STATE_DIR", state_dir)
    monkeypatch.setattr(scanner, "STATE_FILE", state_dir / "volume_gainers_previous_eod.csv")
    frame = pd.DataFrame({
        "TckrSymb": ["AAA"],
        "CompanyName": ["Alpha Limited"],
        "EODScanDate": ["2026-11-16"],
        "PageVolume": [2_391_000],
    })

    scanner._save_eod_snapshot(frame, date(2026, 11, 13))

    marker = json.loads((state_dir / "eod_snapshot_run_marker.json").read_text(encoding="utf-8"))
    assert marker["scan_date"] == "2026-11-16"
    assert marker["eod_date"] == "2026-11-13"


def test_eod_snapshot_cache_guard_accepts_only_same_session_current_run():
    from strategies.ecms.volume_gainers import _is_current_run_eod_snapshot_cacheable

    row = {
        "TckrSymb": "AAA",
        "EODDate": "2026-11-13",
        "SnapshotType": "EOD",
        "SnapshotStatus": "VALID",
    }
    marker = {
        "snapshot_type": "EOD",
        "snapshot_status": "VALID",
        "github_run_id": "run-13",
        "symbol_count": 1,
        "eod_date": "2026-11-13",
        "scan_date": "2026-11-13",
    }
    assert _is_current_run_eod_snapshot_cacheable(marker, [row], "run-13")

    # Monday's pre-close page can still show Friday's completed data, but it
    # must not replace Friday's valid EOD snapshot for the next Morning.
    stale_preclose = {**marker, "github_run_id": "run-16", "scan_date": "2026-11-16"}
    assert not _is_current_run_eod_snapshot_cacheable(stale_preclose, [row], "run-16")
    assert not _is_current_run_eod_snapshot_cacheable(marker, [row], "different-run")
    assert not _is_current_run_eod_snapshot_cacheable(
        {**marker, "symbol_count": 2}, [row], "run-13"
    )
    assert not _is_current_run_eod_snapshot_cacheable(
        {**marker, "snapshot_status": "INVALID"}, [row], "run-13"
    )


def test_ecms_three_step_eod_morning_eod_next_morning_state_loop(tmp_path, monkeypatch):
    import json
    import pytest
    from datetime import date
    import strategies.ecms.volume_gainers as scanner

    state_dir = tmp_path / "data" / "cache" / "ecms"
    eod_state = state_dir / "volume_gainers_previous_eod.csv"
    morning_state = state_dir / "volume_gainers_same_day_morning.csv"
    consumed_marker = state_dir / "volume_gainers_previous_eod_consumed.json"
    monkeypatch.setattr(scanner, "STATE_DIR", state_dir)
    monkeypatch.setattr(scanner, "STATE_FILE", eod_state)
    monkeypatch.setattr(scanner, "MORNING_STATE_FILE", morning_state)
    monkeypatch.setattr(scanner, "CONSUMED_EOD_MARKER_FILE", consumed_marker)

    # Friday EOD is the active reference for Monday Morning.
    scanner._save_eod_snapshot(pd.DataFrame([{
        "TckrSymb": "AAA", "PageVolume": 100, "EODScanDate": "2026-11-13",
    }]), date(2026, 11, 13))
    assert set(pd.read_csv(eod_state)["EODDate"]) == {"2026-11-13"}

    # Failed/mismatched consumption must preserve Friday active reference.
    with pytest.raises(RuntimeError, match="refusing to consume"):
        scanner._consume_previous_eod_snapshot(date(2026, 11, 16))
    assert eod_state.exists()

    # Monday Morning is stored separately; Friday EOD remains until comparison succeeds.
    scanner._save_same_day_morning_snapshot(pd.DataFrame([{
        "TckrSymb": "AAA", "PageVolume": 120,
        "MorningPageCapturedAtIST": "2026-11-16T09:20:00+05:30",
        "FundamentalShortlistStatus": "PASS",
    }, {
        "TckrSymb": "BBB", "PageVolume": 80,
        "MorningPageCapturedAtIST": "2026-11-16T09:20:00+05:30",
        "FundamentalShortlistStatus": "WAIT_FOR_DATA",
    }]), date(2026, 11, 16))
    assert eod_state.exists()
    assert set(pd.read_csv(morning_state)["MorningDate"]) == {"2026-11-16"}

    # Successful Monday Morning comparison consumes Friday EOD only.
    assert scanner._consume_previous_eod_snapshot(date(2026, 11, 13))
    assert not eod_state.exists()
    assert json.loads(consumed_marker.read_text())["consumed_eod_date"] == "2026-11-13"
    assert morning_state.exists()

    # Monday EOD compares with Monday Morning, never Friday EOD.
    monday_eod_page = pd.DataFrame([
        {"TckrSymb": "AAA", "PageVolume": 150},
        {"TckrSymb": "CCC", "PageVolume": 70},
    ])
    compared = scanner._attach_same_day_morning_confirmation(
        monday_eod_page, date(2026, 11, 16), eod_data_date=date(2026, 11, 16)
    ).set_index("TckrSymb")
    assert compared.loc["AAA", "MorningToEODStatus"] == "MORNING_AND_EOD_REPEAT"
    assert compared.loc["CCC", "MorningToEODStatus"] == "EOD_NEW_ENTRY"
    assert compared.loc["AAA", "MorningPageVolume"] == 120
    assert compared.loc["AAA", "MorningFundamentalStatus"] == "PASS"

    # Valid Monday EOD becomes the next trading session active reference.
    scanner._save_eod_snapshot(pd.DataFrame([{
        "TckrSymb": "AAA", "PageVolume": 150, "EODScanDate": "2026-11-16",
    }, {
        "TckrSymb": "CCC", "PageVolume": 70, "EODScanDate": "2026-11-16",
    }]), date(2026, 11, 16))
    next_morning_reference = pd.read_csv(eod_state, dtype={"TckrSymb": str})
    assert set(next_morning_reference["EODDate"]) == {"2026-11-16"}
    assert set(next_morning_reference["TckrSymb"]) == {"AAA", "CCC"}
    assert set(pd.read_csv(morning_state)["MorningDate"]) == {"2026-11-16"}

    # Tuesday Morning consumes Monday EOD and keeps Tuesday Morning for same-day EOD.
    scanner._save_same_day_morning_snapshot(pd.DataFrame([{
        "TckrSymb": "AAA", "PageVolume": 160,
        "MorningPageCapturedAtIST": "2026-11-17T09:20:00+05:30",
        "FundamentalShortlistStatus": "PASS",
    }]), date(2026, 11, 17))
    assert scanner._consume_previous_eod_snapshot(date(2026, 11, 16))
    assert not eod_state.exists()
    assert json.loads(consumed_marker.read_text())["consumed_eod_date"] == "2026-11-16"
    assert set(pd.read_csv(morning_state)["MorningDate"]) == {"2026-11-17"}


def test_metric_value_provenance_keeps_provider_and_official_sources_separate():
    from strategies.ecms.volume_gainers import _metric_value_provenance

    row = {
        "MetricSourcesJSON": '{"RevenueGrowthPct":"Yahoo Finance via yfinance"}',
        "MetricSourceURLsJSON": '{"RevenueGrowthPct":"https://provider.example/financials"}',
        "MetricSourcePeriodsJSON": '{"RevenueGrowthPct":"2026-03-31"}',
        "MetricCalculationBasesJSON": '{"RevenueGrowthPct":"ANNUAL_ALIGNED_STATEMENTS"}',
        "MetricSourceCurrenciesJSON": '{"RevenueGrowthPct":"INR"}',
        "Source": "NSE_OFFICIAL_XBRL_AUDIT",
        "FinancialPeriodEnd": "2026-03-31",
        "MetricCalculationBasis": "UNVERIFIED",
    }
    result = _metric_value_provenance(row, "RevenueGrowthPct")

    assert result["ValueSource"] == "Yahoo Finance via yfinance"
    assert result["ValueSourceURL"] == "https://provider.example/financials"
    assert result["ValuePeriodEnd"] == "2026-03-31"
    assert result["ValueBasis"] == "ANNUAL_ALIGNED_STATEMENTS"
    assert result["ValueCurrency"] == "INR"
    assert result["ValueUnit"] == "PERCENT"


def test_nse_page_download_preserves_all_rows_and_marks_mainboard_eligibility():
    from strategies.ecms.volume_gainers import _build_nse_page_download

    page = pd.DataFrame({
        "TckrSymb": ["AAA", "BBB", "CCC"],
        "CompanyName": ["A Ltd", "B Ltd", "C Ltd"],
        "PageVolume": [1000, 2000, 3000],
    })
    result = _build_nse_page_download(
        page, {"AAA", "CCC"}, "morning", "2026-11-17",
        "2026-11-17T09:20:00+05:30", "official-mainboard.csv",
    )
    assert result["TckrSymb"].tolist() == ["AAA", "BBB", "CCC"]
    assert result["MainBoardEligible"].tolist() == [True, False, True]
    assert result["PageUniverseStatus"].tolist() == [
        "PASS_MAIN_BOARD_EQUITY",
        "PAGE_ROW_NOT_IN_OFFICIAL_MAIN_BOARD_UNIVERSE",
        "PASS_MAIN_BOARD_EQUITY",
    ]
    assert result["ScanMode"].eq("MORNING").all()


def test_main_persists_explicit_skipped_execution_status(tmp_path, monkeypatch):
    import json
    import strategies.ecms.volume_gainers as scanner

    monkeypatch.setattr(scanner, "OUTPUT_DIR", tmp_path)
    monkeypatch.setenv("GITHUB_RUN_ID", "test-run-42")
    payload = scanner._write_execution_status(
        "morning", "SKIPPED", "NOT_OFFICIAL_NSE_SESSION_SCAN_SLOT",
        expected_time_ist="09:20", actual_time_ist="10:05",
    )

    saved = json.loads((tmp_path / "ecms_execution_status.json").read_text(encoding="utf-8"))
    assert payload["status"] == "SKIPPED"
    assert saved["reason"] == "NOT_OFFICIAL_NSE_SESSION_SCAN_SLOT"
    assert saved["mode"] == "MORNING"
    assert saved["github_run_id"] == "test-run-42"
    assert saved["expected_time_ist"] == "09:20"


def test_manual_auto_mode_after_market_close_runs_eod(monkeypatch):
    import sys
    from datetime import datetime as real_datetime
    import strategies.ecms.volume_gainers as scanner

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 11, 17, 15, 31, tzinfo=tz)

    calls = []
    monkeypatch.setattr(scanner, "datetime", FixedDateTime)
    monkeypatch.setattr(scanner, "is_trading_session", lambda _day: True)
    monkeypatch.setattr(scanner, "calendar_coverage_warnings", lambda _day: [])
    monkeypatch.setattr(scanner, "run_eod", lambda: calls.append("eod") or {})
    monkeypatch.setattr(scanner, "run_morning", lambda: calls.append("morning") or {})
    monkeypatch.setattr(scanner, "_write_execution_status", lambda mode, status, reason, **kw: {"mode": mode})
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setattr(sys, "argv", ["ecms-volume-gainers", "--mode", "auto"])

    scanner.main()

    assert calls == ["eod"]


def test_manual_auto_mode_before_market_close_is_skipped(monkeypatch):
    import sys
    from datetime import datetime as real_datetime
    import strategies.ecms.volume_gainers as scanner

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 11, 17, 15, 29, tzinfo=tz)

    calls = []
    statuses = []
    monkeypatch.setattr(scanner, "datetime", FixedDateTime)
    monkeypatch.setattr(scanner, "is_trading_session", lambda _day: True)
    monkeypatch.setattr(scanner, "calendar_coverage_warnings", lambda _day: [])
    monkeypatch.setattr(scanner, "run_eod", lambda: calls.append("eod") or {})
    monkeypatch.setattr(scanner, "run_morning", lambda: calls.append("morning") or {})
    monkeypatch.setattr(scanner, "_write_execution_status", lambda mode, status, reason, **kw: statuses.append((mode, status, reason)))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setattr(sys, "argv", ["ecms-volume-gainers", "--mode", "auto"])

    scanner.main()

    assert calls == []
    assert statuses == [("auto", "SKIPPED", "OUTSIDE_ECMS_SCAN_WINDOW")]



def test_manual_auto_mode_resolves_eod_snapshot_reuse_until_0759():
    from datetime import datetime as real_datetime
    import strategies.ecms.volume_gainers as scanner

    assert scanner._resolve_manual_scan_mode(real_datetime(2026, 11, 17, 7, 59)) == "eod-reuse"
    assert scanner._resolve_manual_scan_mode(real_datetime(2026, 11, 17, 0, 0)) == "eod-reuse"


def test_manual_auto_mode_resolves_morning_from_0915_to_1159():
    from datetime import datetime as real_datetime
    import strategies.ecms.volume_gainers as scanner

    assert scanner._resolve_manual_scan_mode(real_datetime(2026, 11, 17, 9, 15)) == "morning"
    assert scanner._resolve_manual_scan_mode(real_datetime(2026, 11, 17, 9, 20)) == "morning"
    assert scanner._resolve_manual_scan_mode(real_datetime(2026, 11, 17, 11, 59)) == "morning"


def test_manual_auto_mode_skips_locked_and_intraday_windows():
    from datetime import datetime as real_datetime
    import strategies.ecms.volume_gainers as scanner

    assert scanner._resolve_manual_scan_mode(real_datetime(2026, 11, 17, 8, 0)) is None
    assert scanner._resolve_manual_scan_mode(real_datetime(2026, 11, 17, 9, 14)) is None
    assert scanner._resolve_manual_scan_mode(real_datetime(2026, 11, 17, 12, 0)) is None
    assert scanner._resolve_manual_scan_mode(real_datetime(2026, 11, 17, 15, 29)) is None
    assert scanner._resolve_manual_scan_mode(real_datetime(2026, 11, 17, 15, 30)) == "eod"



def test_reuse_previous_eod_snapshot_publishes_cached_data_without_live_fetch(tmp_path, monkeypatch):
    import pandas as pd
    import strategies.ecms.volume_gainers as scanner
    from datetime import date

    state = tmp_path / "state.csv"
    output = tmp_path / "out"
    pd.DataFrame([{
        "TckrSymb": "AAA",
        "EODDate": "2026-11-16",
        "SnapshotType": "EOD",
        "SnapshotStatus": "VALID",
        "SnapshotCapturedAtIST": "2026-11-16T17:01:00+05:30",
        "PageVolume": 1000,
    }]).to_csv(state, index=False)
    monkeypatch.setattr(scanner, "STATE_DIR", state.parent)
    monkeypatch.setattr(scanner, "STATE_FILE", state)
    monkeypatch.setattr(scanner, "OUTPUT_DIR", output)
    monkeypatch.setattr(scanner, "expected_latest_completed_session", lambda: date(2026, 11, 16))
    statuses = []
    monkeypatch.setattr(scanner, "_write_execution_status", lambda mode, status, reason, **kw: statuses.append((mode, status, reason)))
    result = scanner._reuse_previous_eod_snapshot()
    assert result["snapshot_refresh_performed"] is False
    assert result["eligible_mainboard_equities"] == 1
    saved = pd.read_csv(output / "volume_gainers_eod_nse_page.csv")
    assert saved.loc[0, "ScanMode"] == "EOD_REUSED"
    assert statuses == [("eod", "REUSED", "PREVIOUS_EOD_SNAPSHOT_REUSED")]


def test_reuse_previous_eod_snapshot_rejects_wrong_date(tmp_path, monkeypatch):
    import pandas as pd
    import strategies.ecms.volume_gainers as scanner
    from datetime import date

    state = tmp_path / "state.csv"
    pd.DataFrame([{
        "TckrSymb": "AAA",
        "EODDate": "2026-11-13",
        "SnapshotType": "EOD",
        "SnapshotStatus": "VALID",
        "SnapshotCapturedAtIST": "2026-11-13T17:01:00+05:30",
    }]).to_csv(state, index=False)
    monkeypatch.setattr(scanner, "STATE_DIR", state.parent)
    monkeypatch.setattr(scanner, "STATE_FILE", state)
    monkeypatch.setattr(scanner, "expected_latest_completed_session", lambda: date(2026, 11, 16))
    statuses = []
    monkeypatch.setattr(scanner, "_write_execution_status", lambda mode, status, reason, **kw: statuses.append((mode, status, reason)))
    assert scanner._reuse_previous_eod_snapshot() is None
    assert statuses[0][1:] == ("WAIT_FOR_DATA", "EOD_SNAPSHOT_DATE_MISMATCH_FOR_REUSE")
