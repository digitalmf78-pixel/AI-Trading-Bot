"""Fetch and verify the ECMS U-Turn sample's official NSE UDiFF archives.

Research-only utility. Downloads only URLs listed in the checked-in NSE
session manifests. It never changes production data or sends Telegram output.
"""
from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import io
import json
import os
import sys
import time
import zipfile
import threading
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.ecms.uturn_nse_ohlc import (
    build_nse_symbol_ohlc_window,
    extract_nse_eq_ohlc_row,
)

RESEARCH = ROOT / "research" / "ecms_uturn"
OUTPUT = Path(os.environ.get("UTURN_OUTPUT_DIR", "uturn_nse_audit_output"))
USER_AGENT = "Mozilla/5.0 (compatible; ECMS-U-Turn-Research/1.0; +https://github.com/digitalmf78-pixel/AI-Trading-Bot)"
CONNECT_TIMEOUT_SECONDS = 15
READ_TIMEOUT_SECONDS = 35
MAX_ATTEMPTS = 2
_thread_local = threading.local()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _nse_session() -> requests.Session:
    """Create one warmed NSE session per worker thread.

    NSE archive hosts can stall requests that arrive without a fresh website
    session. Prime cookies on the public NSE site before requesting archives.
    """
    session = getattr(_thread_local, "session", None)
    if session is not None:
        return session

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/zip,application/octet-stream,*/*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.nseindia.com/all-reports",
    })
    # Establish the public-site session first; no login or credentials used.
    warm = session.get(
        "https://www.nseindia.com/",
        headers={"Accept": "text/html,application/xhtml+xml"},
        timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
    )
    warm.raise_for_status()
    _thread_local.session = session
    return session


def fetch_archive(url: str) -> tuple[bytes, pd.DataFrame]:
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            session = _nse_session()
            with session.get(
                url,
                stream=True,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            ) as response:
                response.raise_for_status()
                chunks = []
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        chunks.append(chunk)
                payload = b"".join(chunks)

            if not payload.startswith(b"PK"):
                preview = payload[:160].decode("utf-8", errors="replace")
                raise ValueError(
                    f"Response is not a ZIP archive; bytes={len(payload)}, preview={preview!r}"
                )
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if len(csv_names) != 1:
                    raise ValueError(f"Expected one CSV in archive, found {len(csv_names)}")
                with archive.open(csv_names[0]) as stream:
                    table = pd.read_csv(stream, dtype=str)

            required = {
                "TradDt", "Sgmt", "FinInstrmTp", "TckrSymb",
                "SctySrs", "HghPric", "ClsPric", "ISIN",
            }
            if not required.issubset(table.columns):
                raise ValueError(f"UDiFF columns missing: {sorted(required - set(table.columns))}")
            return payload, table
        except Exception as exc:
            last_error = exc
            # A stale/bad cookie session is discarded before the one retry.
            if hasattr(_thread_local, "session"):
                del _thread_local.session
            if attempt < MAX_ATTEMPTS:
                time.sleep(3 * attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")
