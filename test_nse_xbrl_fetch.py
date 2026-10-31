import socket
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import nse_xbrl_fetch as fetcher


class Response:
    status_code = 200
    content = b'<xbrl xmlns="urn:test"><context id="c1"/></xbrl>'
    def raise_for_status(self):
        pass


class Session:
    def __init__(self): self.calls = 0
    def get(self, url, timeout):
        self.calls += 1
        return Response()


def test_fetch_retries_transient_dns_and_writes_valid_xml(tmp_path, monkeypatch):
    calls = {"n": 0}
    def resolve(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise socket.gaierror("temporary resolver failure")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))]
    monkeypatch.setattr(fetcher.socket, "getaddrinfo", resolve)
    sleeps = []
    target = tmp_path / "filing.xml"
    result = fetcher.fetch_official_xbrl_xml(
        "https://nsearchives.nseindia.com/xbrl/sample.xml", target,
        session=Session(), attempts=3, sleep=sleeps.append,
    )
    assert result == target
    assert ET.parse(target).getroot().tag.endswith("xbrl")
    assert calls["n"] == 2
    assert sleeps == [1]


def test_fetch_rejects_non_nse_host(tmp_path):
    with pytest.raises(ValueError):
        fetcher.fetch_official_xbrl_xml("https://example.com/a.xml", tmp_path / "a.xml")


def test_fetch_rejects_html_challenge_page(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("192.0.2.1", 443))])
    class HtmlSession:
        def get(self, url, timeout):
            class HtmlResponse(Response):
                content = b"<html>Access denied</html>"
            return HtmlResponse()
    with pytest.raises(RuntimeError, match="fetch failed"):
        fetcher.fetch_official_xbrl_xml(
            "https://nsearchives.nseindia.com/xbrl/sample.xml", tmp_path / "bad.xml",
            session=HtmlSession(), attempts=1,
        )
