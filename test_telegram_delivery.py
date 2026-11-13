import news_catalyst


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "result": {"message_id": 123}}


def test_telegram_digest_confirms_api_delivery(monkeypatch):
    sent = []
    monkeypatch.setattr(news_catalyst, "build_marathi_digest", lambda *args: ["NSE V8 report", "Scan complete"])
    monkeypatch.setattr(news_catalyst.requests, "post", lambda url, data, timeout, files=None: (sent.append((url, data, files)) or FakeResponse()))
    monkeypatch.setenv("NEWS_SCAN_MODE", "EOD")
    news_catalyst.send_marathi_telegram(None, "2026-11-05", None, {}, "token", "chat")
    assert len(sent) == 2
    assert sent[0][1]["chat_id"] == "chat"
    assert "NSE V8 report" in sent[0][1]["text"]
    assert sent[0][0].endswith("/sendMessage")
    assert sent[1][0].endswith("/sendDocument")
    assert sent[1][2]["document"][0] == "v8_telegram_full_report.zip"


def test_telegram_missing_secrets_fails_loudly():
    try:
        news_catalyst.send_marathi_telegram(None, "2026-11-05", None, {}, None, None)
    except RuntimeError as exc:
        assert "TELEGRAM_BOT_TOKEN" in str(exc)
    else:
        raise AssertionError("Missing Telegram secrets must fail the scan")


def test_telegram_retries_failed_delivery(monkeypatch):
    calls = []
    monkeypatch.setattr(news_catalyst, "build_marathi_digest", lambda *args: ["NSE V8 report"])
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
