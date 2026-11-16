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
        return result, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
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
    result = scanner._attach_same_day_morning_confirmation(eod, date(2026, 11, 16)).set_index("TckrSymb")

    assert result.loc["AAA", "MorningSeenSameDay"]
    assert result.loc["AAA", "MorningToEODStatus"] == "MORNING_AND_EOD_REPEAT"
    assert result.loc["AAA", "MorningPageVolume"] == 120000
    assert result.loc["AAA", "MorningScanTimeIST"] == "2026-11-16T09:20:04+05:30"
    assert result.loc["AAA", "MorningFundamentalStatus"] == "PASS"
    assert result.loc["AAA", "MorningNewsContext"] == "Morning news A"
    assert result.loc["CCC", "MorningToEODStatus"] == "EOD_NEW_ENTRY"


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
        "PageVolumeDataStatus": ["DATA_FOUND"],
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

    def fake_morning_match(frame, morning_date):
        captured["comparison_date"] = morning_date
        result = frame.copy()
        result["MorningSeenSameDay"] = [True]
        result["MorningToEODStatus"] = ["MORNING_AND_EOD_REPEAT"]
        return result

    monkeypatch.setattr(scanner, "attach_page_rvol", fake_rvol)
    monkeypatch.setattr(scanner, "assess_page_fundamentals", fake_fundamentals)
    monkeypatch.setattr(scanner, "attach_information", fake_information)
    monkeypatch.setattr(scanner, "_attach_same_day_morning_confirmation", fake_morning_match)

    summary = scanner.run_eod()

    assert captured == {
        "rvol_date": date(2026, 11, 13),
        "fundamental_date": date(2026, 11, 16),
        "information_date": date(2026, 11, 16),
        "comparison_date": date(2026, 11, 16),
    }
    assert summary["scan_date_ist"] == "2026-11-16"
    assert summary["data_as_of_date_ist"] == "2026-11-13"
    assert summary["morning_repeat_count"] == 1
