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
    monkeypatch.setattr(news_catalyst.requests, "post", lambda url, data, timeout: (sent.append(data) or FakeResponse()))
    news_catalyst.send_marathi_telegram(None, "2026-11-05", None, {}, "token", "chat")
    assert len(sent) == 1
    assert sent[0]["chat_id"] == "chat"
    assert "NSE V8 report" in sent[0]["text"]


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
    news_catalyst.send_marathi_telegram(None, "2026-11-05", None, {}, "token", "chat")
    assert len(calls) == 2

def test_telegram_digest_lists_every_liquidity_passed_stock_and_all_confirmation_layers():
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
    lines = news_catalyst.build_marathi_digest(result, "2026-11-06", None, {}, observation_report=report)
    digest = "\n".join(lines)
    for symbol in ("STRONG1", "MEDIUM1", "LOW1"):
        assert symbol in digest
    for status in ("Technical:PASS", "Technical:REJECT", "Sector:FAIL", "PRIMARY_CONFIRMED",
                   "3+1:True/PASS", "3+1:False/FAIL", "Risk:REJECT", "FINAL:WATCH",
                   "FINAL:SKIP", "FINAL:WAIT_FOR_DATA"):
        assert status in digest
    assert "CORE TECHNICAL PASS: STRONG1" in digest

