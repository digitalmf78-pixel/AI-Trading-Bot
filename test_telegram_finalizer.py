import json

import pandas as pd

import telegram_finalizer


def test_finalizer_sends_saved_scanner_payload_only_when_invoked(tmp_path, monkeypatch):
    pending = tmp_path / "payload.json"
    payload = {
        "eod_date": "2026-11-18",
        "feed_status": {"NSE": "PASS"},
        "result_json": pd.DataFrame([{"TckrSymb": "ABC"}]).to_json(orient="records"),
        "news_json": pd.DataFrame([{"Headline": "Test"}]).to_json(orient="records"),
        "observation_report_json": pd.DataFrame().to_json(orient="records"),
    }
    pending.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    sent = {}

    def fake_send(result, eod_date, news, feed_status, token, chat_id, observation_report=None):
        sent.update(
            result=result,
            eod_date=eod_date,
            news=news,
            feed_status=feed_status,
            token=token,
            chat_id=chat_id,
            observation_report=observation_report,
        )

    monkeypatch.setattr(telegram_finalizer, "send_marathi_telegram", fake_send)
    telegram_finalizer.send_pending(pending)

    assert sent["eod_date"] == "2026-11-18"
    assert sent["result"].loc[0, "TckrSymb"] == "ABC"
    assert sent["news"].loc[0, "Headline"] == "Test"
    assert sent["feed_status"] == {"NSE": "PASS"}
    assert sent["token"] == "test-token"
    assert sent["chat_id"] == "test-chat"


def test_finalizer_refuses_missing_payload(tmp_path):
    import pytest

    with pytest.raises(RuntimeError, match="payload not found"):
        telegram_finalizer.send_pending(tmp_path / "missing.json")


def test_finalizer_refuses_missing_telegram_secrets(tmp_path, monkeypatch):
    import pytest

    pending = tmp_path / "payload.json"
    pending.write_text(
        json.dumps({
            "eod_date": "2026-11-18",
            "feed_status": {},
            "result_json": "[]",
            "news_json": "[]",
            "observation_report_json": "[]",
        }),
        encoding="utf-8",
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(RuntimeError, match="requires both"):
        telegram_finalizer.send_pending(pending)
