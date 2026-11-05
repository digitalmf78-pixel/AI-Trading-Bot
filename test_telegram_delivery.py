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
