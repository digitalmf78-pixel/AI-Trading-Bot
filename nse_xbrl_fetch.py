"""Resilient, allow-listed downloader for official NSE XBRL XML filings.

DNS failures are retried with bounded exponential backoff.  This is useful for
transient resolver failures in CI; it cannot bypass a permanently unavailable
DNS/network.  Files are accepted only when they are well-formed XML and the URL
uses an official NSE host.
"""
from __future__ import annotations

import socket
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ALLOWED_HOSTS = {"nsearchives.nseindia.com", "www.nseindia.com", "nseindia.com"}


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4, connect=4, read=2, status=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; NSE-V8-Filing-Audit/1.0)",
        "Accept": "application/xml,text/xml,*/*",
        "Referer": "https://www.nseindia.com/",
    })
    return session


def fetch_official_xbrl_xml(url: str, destination: str | Path, *,
                            session: requests.Session | None = None,
                            attempts: int = 4, sleep=time.sleep) -> Path:
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError("XBRL URL must use HTTPS on an official NSE host")
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    client = session or build_session()
    host = parsed.hostname
    last_error = None
    for attempt in range(attempts):
        try:
            # Resolve explicitly so transient DNS failures are visible and
            # retried before the HTTP layer; normal TLS verification is kept.
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            response = client.get(url, timeout=(10, 40))
            response.raise_for_status()
            body = response.content
            root = ET.fromstring(body)  # reject HTML challenge pages / corrupt XML
            root_name = root.tag.rsplit("}", 1)[-1].lower()
            if not root.tag or root_name in {"html", "body"}:
                raise ValueError("Response is an HTML challenge page, not XBRL XML")
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            return path
        except (socket.gaierror, requests.RequestException, ET.ParseError, OSError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"Official NSE XBRL fetch failed after {attempts} attempts: {last_error}") from last_error
