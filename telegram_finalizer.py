"""Send the scanner's saved Telegram digest only after the workflow's required steps succeed."""
from __future__ import annotations

import argparse
import json
import os
from io import StringIO
from pathlib import Path

import pandas as pd

from news_catalyst import send_marathi_telegram


def _frame(payload: dict, key: str) -> pd.DataFrame:
    raw = payload.get(key)
    if not isinstance(raw, str):
        raise RuntimeError(f"Deferred Telegram payload is missing {key}.")
    try:
        return pd.read_json(StringIO(raw), orient="records")
    except ValueError as exc:
        raise RuntimeError(f"Deferred Telegram payload has invalid {key}.") from exc


def send_pending(payload_path: str | Path = "outputs/telegram_pending/payload.json") -> None:
    path = Path(payload_path)
    if not path.is_file():
        raise RuntimeError(f"Deferred Telegram payload not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    eod_date = payload.get("eod_date")
    feed_status = payload.get("feed_status")
    if not eod_date or not isinstance(feed_status, dict):
        raise RuntimeError("Deferred Telegram payload is incomplete: date/feed_status missing.")

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Telegram final notification requires both bot token and chat ID.")

    result = _frame(payload, "result_json")
    news = _frame(payload, "news_json")
    observation = _frame(payload, "observation_report_json")
    send_marathi_telegram(
        result,
        eod_date,
        news,
        {str(k): str(v) for k, v in feed_status.items()},
        token,
        chat_id,
        observation_report=observation,
    )
    print(f"TELEGRAM_FINAL_NOTIFICATION=SUCCESS EOD_DATE={eod_date}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", default="outputs/telegram_pending/payload.json")
    args = parser.parse_args()
    send_pending(args.payload)


if __name__ == "__main__":
    main()
