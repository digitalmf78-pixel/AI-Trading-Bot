import news_catalyst


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "result": {"message_id": 123}}


def test_telegram_digest_confirms_api_delivery(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "outputs"
    out.mkdir()
    pd.DataFrame([
        {"TckrSymb":"AAA","LiquidityFilterStatus":"PASS","LiquidityTier":"STRONG","AvgDailyTradedValue20D":50000000},
        {"TckrSymb":"BBB","LiquidityFilterStatus":"FILTERED_OUT_BELOW_MINIMUM","LiquidityTier":"WAIT_FOR_DATA"},
    ]).to_csv(out / "v8_liquidity_first_audit.csv", index=False)
    sent = []
    monkeypatch.setattr(news_catalyst, "_read_equity_master", lambda: {"AAA":"AAA INDUSTRIES LIMITED"})
    monkeypatch.setattr(news_catalyst.requests, "post", lambda url, data, timeout, files=None: (sent.append((url, data, files)) or FakeResponse()))
    monkeypatch.setenv("NEWS_SCAN_MODE", "EOD")
    news_catalyst.send_marathi_telegram(None, "2026-11-05", None, {}, "token", "chat")
    assert len(sent) == 2
    assert sent[0][1]["chat_id"] == "chat"
    assert "NSE V8" in sent[0][1]["text"]
    assert len(sent[0][1]["text"]) < 1000
    assert sent[0][0].endswith("/sendMessage")
    assert sent[1][0].endswith("/sendDocument")
    assert sent[1][2]["document"][0] == "v8_telegram_liquidity_passed.csv"
    exported = pd.read_csv(out / "v8_telegram_liquidity_passed.csv")
    assert exported["TckrSymb"].tolist() == ["AAA"]
    assert exported.loc[0, "CompanyName"] == "AAA INDUSTRIES LIMITED"
    assert "AvgDailyTradedValue20D" in exported.columns


def test_telegram_missing_secrets_fails_loudly():
    try:
        news_catalyst.send_marathi_telegram(None, "2026-11-05", None, {}, None, None)
    except RuntimeError as exc:
        assert "TELEGRAM_BOT_TOKEN" in str(exc)
    else:
        raise AssertionError("Missing Telegram secrets must fail the scan")


def test_telegram_retries_failed_delivery(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "outputs"
    out.mkdir()
    pd.DataFrame([{"TckrSymb":"AAA","LiquidityFilterStatus":"PASS"}]).to_csv(out / "v8_liquidity_first_audit.csv", index=False)
    monkeypatch.setattr(news_catalyst, "_read_equity_master", lambda: {})
    calls = []
    def fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("temporary network failure")
        return FakeResponse()
    monkeypatch.setattr(news_catalyst.requests, "post", fake_post)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setenv("NEWS_SCAN_MODE", "EOD")
    news_catalyst.send_marathi_telegram(None, "2026-11-05", None, {}, "token", "chat")
    assert len(calls) == 3

def test_telegram_digest_lists_every_liquidity_passed_stock_and_all_confirmation_layers(monkeypatch):
    report = __import__("pandas").DataFrame([
        {
            "TckrSymb": "STRONG1", "LiquidityFilterStatus": "PASS", "LiquidityTier": "STRONG",
            "AvgDailyTradedValue20D": 50000000, "DeliveryCategoryAStatus": "PASS_AVG_GE_60_PERCENT",
            "DeliveryCategoryBStatus": "FAIL_DAY", "AvgDelivery30D": 65.0, "RVOL": 2.1,
            "FundamentalStatus": "COMPLETE", "FundamentalScore": 72.0,
            "CoreTechnicalScreenStatus": "PASS", "SetupType": "Breakout",
            "TrendClassification": "Bullish", "EMA44SignalStatus": "ABOVE_EMA44",
        },
        {
            "TckrSymb": "MEDIUM1", "LiquidityFilterStatus": "PASS", "LiquidityTier": "MEDIUM",
            "AvgDailyTradedValue20D": 30000000, "DeliveryCategoryAStatus": "PASS_AVG_GE_60_PERCENT",
            "DeliveryCategoryBStatus": "PASS_EACH_DAY_GE_60_PERCENT", "AvgDelivery30D": 68.0, "RVOL": 1.2,
            "FundamentalStatus": "PARTIAL_DATA", "FundamentalScore": 51.0,
            "CoreTechnicalScreenStatus": "REJECT", "SetupType": "No Clear Setup",
            "TrendClassification": "Bearish", "EMA44SignalStatus": "BELOW_EMA44",
        },
        {
            "TckrSymb": "LOW1", "LiquidityFilterStatus": "PASS", "LiquidityTier": "LOW",
            "AvgDailyTradedValue20D": 16000000, "DeliveryCategoryAStatus": "PASS_AVG_GE_60_PERCENT",
            "DeliveryCategoryBStatus": "FAIL_DAY", "AvgDelivery30D": 61.0, "RVOL": 0.8,
            "FundamentalStatus": "WAIT_FOR_DATA", "FundamentalScore": None,
            "CoreTechnicalScreenStatus": "WAIT_FOR_DATA", "SetupType": "WAIT_FOR_DATA",
            "TrendClassification": "WAIT_FOR_DATA", "EMA44SignalStatus": "WAIT_FOR_DATA",
        },
    ])
    result = __import__("pandas").DataFrame([
        {
            "TckrSymb": "STRONG1", "Sector": "Nifty Bank", "SectorStrengthStatus": "PASS",
            "NewsEvidenceStatus": "PRIMARY_CONFIRMED", "NewsPrimarySourceVerified": True,
            "Confirmation3Plus1": True, "MandatoryConfirmationStatus": "PASS",
            "RiskRewardStatus": "PASS", "RiskReward": 2.4, "ChaseStatus": "CLEAR",
            "RiskControlStatus": "PASS", "EODWatchlistStatus": "WATCH",
            "RiskControlReason": "RISK_LIMITS_PASSED",
        },
        {
            "TckrSymb": "MEDIUM1", "Sector": "Nifty IT", "SectorStrengthStatus": "FAIL",
            "NewsEvidenceStatus": "UNVERIFIED", "NewsPrimarySourceVerified": False,
            "Confirmation3Plus1": False, "MandatoryConfirmationStatus": "FAIL",
            "RiskRewardStatus": "FAIL", "RiskReward": 0.8, "ChaseStatus": "CHASE",
            "RiskControlStatus": "REJECT", "EODWatchlistStatus": "SKIP",
            "RiskControlReason": "STOP_DISTANCE_EXCEEDS_LIMIT",
        },
        {
            "TckrSymb": "LOW1", "Sector": "Unknown", "SectorStrengthStatus": "WAIT_FOR_DATA",
            "NewsEvidenceStatus": "NO_DATA", "NewsPrimarySourceVerified": False,
            "Confirmation3Plus1": False, "MandatoryConfirmationStatus": "WAIT_FOR_DATA",
            "RiskRewardStatus": "WAIT_FOR_DATA", "RiskReward": None, "ChaseStatus": "CLEAR",
            "RiskControlStatus": "WAIT_FOR_DATA", "EODWatchlistStatus": "WAIT_FOR_DATA",
            "RiskControlReason": "SECTOR_REQUIRED_FOR_CONCENTRATION_CHECK",
        },
    ])
    monkeypatch.setattr(news_catalyst, "_read_equity_master", lambda: {"STRONG1": "STRONG ONE LIMITED", "MEDIUM1": "MEDIUM ONE LIMITED", "LOW1": "LOW ONE LIMITED"})
    lines = news_catalyst.build_marathi_digest(result, "2026-11-06", None, {}, observation_report=report)
    digest = "\n".join(lines)
    for symbol in ("STRONG1", "MEDIUM1", "LOW1"):
        assert symbol in digest
    assert "Company: STRONG ONE LIMITED" in digest
    assert "NSE: STRONG1" in digest
    for status in ("Technical:PASS", "Technical:REJECT", "Sector:FAIL", "PRIMARY_CONFIRMED",
                   "3+1:True/PASS", "3+1:False/FAIL", "Risk:REJECT", "FINAL:WATCH",
                   "FINAL:SKIP", "FINAL:WAIT_FOR_DATA"):
        assert status in digest
    assert "CORE TECHNICAL PASS: STRONG1" in digest



def test_research_digest_has_delivery_5_10_20_news_links_events_and_watchlist_export(tmp_path, monkeypatch):
    import pandas as pd
    import telegram_research_digest as research
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "outputs"
    out.mkdir()
    pd.DataFrame([{
        "TckrSymb":"ABC","DeliveryQty5DStatus":"COMPLETE","DeliveryQty5DChangePct":20,
        "DeliveryQty5DDeliveryPctAverage":64,"DeliveryQty5DCloseChangePct":3,
        "DeliveryQty10DStatus":"WAIT_FOR_DATA","DeliveryQty20DStatus":"WAIT_FOR_DATA"
    }]).to_csv(out/"v8_delivery_quantity_observations_20261111.csv",index=False)
    pd.DataFrame([{"TckrSymb":"ABC","WatchlistStatus":"ACCUMULATION_WATCH",
        "WatchlistReason":"OBSERVATION_ONLY_NOT_MEASURED","HighDeliverySessionCount":4,
        "HighDeliveryUpDayCount":3,"HighDeliveryDownDayCount":1}]).to_csv(out/"v8_hybrid_potential_accumulation_watchlist.csv",index=False)
    pd.DataFrame([{"TckrSymb":"ABC","EventDate":"2026-11-20","EventType":"BOARD_MEETING",
        "Status":"OFFICIAL_DATE_CONFIRMED","Headline":"Board meeting","Source":"NSE",
        "URL":"https://example.test/nse"}]).to_csv(out/"v8_upcoming_corporate_events.csv",index=False)
    news=pd.DataFrame([{"TckrSymb":"ABC","PublishedAt":"2026-11-11T10:00:00Z",
        "Headline":"ABC announces order","Impact":"positive","SourceType":"official",
        "URL":"https://example.test/news"}])
    digest="\\n".join(research.build_telegram_research_sections(pd.DataFrame([{"TckrSymb":"ABC"}]),news,"2026-11-11",{"ABC":"ABC INDUSTRIES LIMITED"}))
    assert "ABC INDUSTRIES LIMITED | NSE: ABC" in digest
    assert "5D Qty Δ 20.0%" in digest and "10D WAIT_FOR_DATA" in digest
    assert "ACCUMULATION_WATCH" in digest and "BOARD_MEETING" in digest
    assert "https://example.test/news" in digest
    saved=pd.read_csv(out/"v8_telegram_research_watchlist.csv")
    assert saved.loc[0,"TckrSymb"]=="ABC" and "UpcomingEvents20D" in saved.columns
    assert saved.loc[0,"ResearchWatchlistCategories"] == "ACCUMULATION"
    assert (out/"research_watchlists"/"v8_telegram_research_watchlist_20261111.csv").is_file()

def test_telegram_delivery_line_uses_compact_a_b_counts():
    import pandas as pd

    report = pd.DataFrame([{
        "TckrSymb": "COMPACT",
        "LiquidityFilterStatus": "PASS",
        "LiquidityTier": "STRONG",
        "DeliveryCategoryAStatus": "PASS_AVG_GE_60_PERCENT",
        "DeliveryCategoryBStatus": "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT",
        "DeliveryARolling5DPassCount30D": 7,
        "DeliveryDailyPassCount": 5,
        "DeliveryACount30DStatus": "PASS",
        "DeliveryBCount30DStatus": "PASS",
        "AvgDelivery30D": 63.0,
    }])
    digest = "\\n".join(news_catalyst._observation_digest_lines(report, pd.DataFrame()))
    assert "Delivery: A 7/30 PASS | B 5/30 PASS" in digest


def test_summary_selects_only_final_stocks_sorted_entry_then_v8score(monkeypatch):
    import pandas as pd
    rows = pd.DataFrame([
        {"TckrSymb":"WATCH_HIGH","EODWatchlistStatus":"WATCH","V8Score":95},
        {"TckrSymb":"ENTRY_LOW","EODWatchlistStatus":"ENTRY_CANDIDATE","V8Score":50},
        {"TckrSymb":"ENTRY_HIGH","EODWatchlistStatus":"ENTRY_CANDIDATE","V8Score":90},
        {"TckrSymb":"SKIP","EODWatchlistStatus":"SKIP","V8Score":100},
        {"TckrSymb":"WATCH_LOW","EODWatchlistStatus":"WATCH","V8Score":20},
    ])
    from telegram_research_digest import select_summary_stocks
    selected = select_summary_stocks(rows, max_stocks=3)
    assert selected["TckrSymb"].tolist() == ["ENTRY_HIGH", "ENTRY_LOW", "WATCH_HIGH"]


def test_summary_message_is_short_and_reports_required_counts(monkeypatch):
    import pandas as pd
    report = pd.DataFrame([
        {"TckrSymb":"AAA","LiquidityFilterStatus":"PASS","LiquidityTier":"STRONG",
         "DeliveryACount30DStatus":"PASS","DeliveryBCount30DStatus":"FAIL",
         "CoreTechnicalScreenStatus":"PASS","EODWatchlistStatus":"ENTRY_CANDIDATE","V8Score":88},
        {"TckrSymb":"BBB","LiquidityFilterStatus":"PASS","LiquidityTier":"MEDIUM",
         "DeliveryACount30DStatus":"FAIL","DeliveryBCount30DStatus":"PASS",
         "CoreTechnicalScreenStatus":"REJECT","EODWatchlistStatus":"WATCH","V8Score":70},
        {"TckrSymb":"CCC","LiquidityFilterStatus":"PASS","LiquidityTier":"LOW",
         "DeliveryACount30DStatus":"FAIL","DeliveryBCount30DStatus":"FAIL",
         "CoreTechnicalScreenStatus":"PASS","EODWatchlistStatus":"SKIP","V8Score":99},
    ])
    monkeypatch.setattr(news_catalyst, "_read_equity_master", lambda: {})
    monkeypatch.setenv("TELEGRAM_MAX_STOCKS", "10")
    monkeypatch.setenv("TELEGRAM_MODE", "SUMMARY")
    lines = news_catalyst._telegram_summary_lines(pd.DataFrame(), "2026-11-13", report, pd.DataFrame(), "EOD")
    message = "\n".join(lines)
    assert len(message) <= 3500
    assert "Liquidity PASS: 3" in message
    assert "Delivery A/B eligible: 2" in message
    assert "Core PASS: 2" in message
    assert "Final WATCH: 1" in message and "ENTRY_CANDIDATE: 1" in message
    assert "AAA" in message and "BBB" in message and "CCC" not in message



def test_summary_shows_research_stages_when_final_entry_list_is_empty(tmp_path, monkeypatch):
    import pandas as pd

    monkeypatch.chdir(tmp_path)
    out = tmp_path / "outputs"
    out.mkdir()
    pd.DataFrame([
        {"TckrSymb": "BRK1", "WatchlistStatus": "BREAKOUT_OBSERVATION_CONFIRMED", "WatchlistReason": "Breakout event observed"},
        {"TckrSymb": "PBK1", "WatchlistStatus": "PULLBACK_OBSERVATION_CONFIRMED", "WatchlistReason": "Pullback observation confirmed"},
        {"TckrSymb": "OBS1", "WatchlistStatus": "BREAKOUT_PULLBACK_OBSERVATION", "WatchlistReason": "Setup observation only"},
        {"TckrSymb": "CHASE1", "WatchlistStatus": "CHASED", "WatchlistReason": "Chase guard"},
    ]).to_csv(out / "v8_hybrid_breakout_ready_watchlist.csv", index=False)
    pd.DataFrame([
        {"TckrSymb": "BASE1", "WatchlistStatus": "BASE_FORMING", "WatchlistReason": "Two contractions observed; NOT_VCP_CONFIRMED"},
        {"TckrSymb": "WAITBASE", "WatchlistStatus": "WAIT_FOR_DATA"},
    ]).to_csv(out / "v8_hybrid_base_vcp_watchlist.csv", index=False)
    pd.DataFrame([
        {"TckrSymb": "ACC1", "WatchlistStatus": "ACCUMULATION_WATCH", "EvidenceStatus": "OBSERVATIONS_AVAILABLE"},
        {"TckrSymb": "ACCWAIT", "WatchlistStatus": "WAIT_FOR_DATA"},
    ]).to_csv(out / "v8_hybrid_potential_accumulation_watchlist.csv", index=False)
    pd.DataFrame([
        {"TckrSymb": "WAITENTRY", "WatchlistStatus": "WAIT_FOR_DATA"},
    ]).to_csv(out / "v8_hybrid_confirmed_entry_watchlist.csv", index=False)

    report = pd.DataFrame([{
        "TckrSymb": "SKIP1",
        "DeliveryACount30DStatus": "PASS",
        "DeliveryBCount30DStatus": "FAIL",
        "CoreTechnicalScreenStatus": "REJECT",
        "EODWatchlistStatus": "SKIP",
    }])
    monkeypatch.setattr(news_catalyst, "_telegram_observation_rows", lambda *args, **kwargs: report.copy())
    monkeypatch.setattr(news_catalyst, "_read_equity_master", lambda: {
        "BRK1": "BREAKOUT ONE", "PBK1": "PULLBACK ONE", "OBS1": "OBSERVATION ONE",
        "BASE1": "BASE ONE", "ACC1": "ACCUMULATION ONE",
    })
    monkeypatch.setenv("TELEGRAM_MAX_STOCKS", "10")
    monkeypatch.setenv("TELEGRAM_MODE", "SUMMARY")

    message = "\\n".join(news_catalyst._telegram_summary_lines(
        pd.DataFrame(), "2026-11-17", report, pd.DataFrame(), "EOD"
    ))

    assert "Final WATCH: 0" in message and "ENTRY_CANDIDATE: 0" in message
    assert "Research-only candidates (NOT BUY / NOT ENTRY)" in message
    for symbol in ("BRK1", "PBK1", "OBS1", "BASE1", "ACC1"):
        assert symbol in message
    for excluded in ("CHASE1", "WAITBASE", "ACCWAIT", "WAITENTRY", "SKIP1"):
        assert excluded not in message
    assert "Accumulation 1" in message and "Base/VCP 1" in message
    assert "Breakout 1" in message and "Pullback 1" in message



def test_premarket_sends_only_new_catalysts_then_skips_unchanged(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NEWS_SCAN_MODE", "PREMARKET")
    calls = []
    monkeypatch.setattr(news_catalyst.requests, "post",
        lambda url, data, timeout, files=None: (calls.append(data["text"]) or FakeResponse()))
    news = pd.DataFrame([{
        "TckrSymb":"ABC","PublishedAt":"2026-11-13T03:00:00Z",
        "Headline":"ABC receives a new order","SourceType":"primary",
        "Impact":"positive","URL":"https://example.test/abc"
    }])
    news_catalyst.send_marathi_telegram(None, "2026-11-13", news, {"NSE":"available"}, "token", "chat")
    news_catalyst.send_marathi_telegram(None, "2026-11-13", news, {"NSE":"available"}, "token", "chat")
    assert len(calls) == 1
    assert "New catalysts: 1" in calls[0]
    assert "ABC receives a new order" in calls[0]
    assert "Full audit" not in calls[0]


def test_premarket_batches_more_than_five_new_catalysts_without_losing_remainder(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NEWS_SCAN_MODE", "PREMARKET")
    sent = []
    monkeypatch.setattr(news_catalyst.requests, "post",
        lambda url, data, timeout, files=None: (sent.append(data["text"]) or FakeResponse()))
    news = pd.DataFrame([{
        "TckrSymb":f"SYM{i}","PublishedAt":f"2026-11-13T0{i}:00:00Z",
        "Headline":f"New issuer catalyst {i}","SourceType":"primary",
        "Impact":"neutral","URL":f"https://example.test/{i}"
    } for i in range(6)])
    for _ in range(3):
        news_catalyst.send_marathi_telegram(None, "2026-11-13", news, {"NSE":"available"}, "token", "chat")
    assert len(sent) == 2
    assert "New catalysts: 6" in sent[0]
    assert "New catalysts: 1" in sent[1]
    assert "New issuer catalyst 0" in sent[1]



def test_liquidity_passed_csv_joins_all_stock_sidecars_and_keeps_one_row_per_stock(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "outputs"
    out.mkdir()
    pd.DataFrame([
        {"TckrSymb":"AAA","LiquidityFilterStatus":"PASS","AvgDailyTradedValue20D":50000000},
        {"TckrSymb":"BBB","LiquidityFilterStatus":"WAIT_FOR_DATA","AvgDailyTradedValue20D":None},
    ]).to_csv(out / "v8_liquidity_first_audit.csv", index=False)
    pd.DataFrame([
        {"TckrSymb":"AAA","DeliveryACount30DStatus":"PASS","DeliveryACount30DDisplay":"6/30","RVOL":2.1},
        {"TckrSymb":"BBB","DeliveryACount30DStatus":"WAIT_FOR_DATA","DeliveryACount30DDisplay":"0/30","RVOL":None},
    ]).to_csv(out / "v8_delivery_dual_category_audit.csv", index=False)
    pd.DataFrame([
        {"TckrSymb":"AAA","Headline":"Order announced","Source":"NSE"},
        {"TckrSymb":"AAA","Headline":"Board meeting","Source":"NSE"},
        {"TckrSymb":"BBB","Headline":"Should not enter","Source":"NSE"},
    ]).to_csv(out / "v8_upcoming_corporate_events.csv", index=False)
    monkeypatch.setattr(news_catalyst, "_read_equity_master", lambda: {"AAA":"AAA LIMITED"})
    path = news_catalyst._build_liquidity_passed_csv("2026-11-21")
    exported = pd.read_csv(path)
    assert exported["TckrSymb"].tolist() == ["AAA"]
    assert exported.loc[0, "CompanyName"] == "AAA LIMITED"
    assert exported.loc[0, "AvgDailyTradedValue20D"] == 50000000
    assert exported.loc[0, "DeliveryACount30DDisplay"] == "6/30"
    assert "Headline" in exported.columns
    assert "Order announced || Board meeting" == exported.loc[0, "Headline"]
