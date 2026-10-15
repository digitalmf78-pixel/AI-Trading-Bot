import xml.etree.ElementTree as ET

import pytest
import news_catalyst as news


class FakeResponse:
    def __init__(self, content, encoding="utf-8"):
        self.content = content.encode(encoding) if isinstance(content, str) else content
        self.encoding = encoding

    def raise_for_status(self):
        return None


def test_valid_rss_feed_parses_normally(monkeypatch):
    payload = '''<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Issuer quarterly results</title><pubDate>Wed, 14 Oct 2026 10:00:00 GMT</pubDate></item>
      <item><title>Issuer board meeting</title><pubDate>Wed, 14 Oct 2026 11:00:00 GMT</pubDate></item>
    </channel></rss>'''
    monkeypatch.setattr(news.requests, "get", lambda *a, **k: FakeResponse(payload))
    items = news._rss_items("https://example.test/rss")
    assert len(items) == 2
    assert items.partial is False
    assert items[0].findtext("title") == "Issuer quarterly results"


def test_truncated_rss_recovers_only_complete_items_and_marks_partial(monkeypatch):
    payload = '''<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Issuer quarterly results</title><pubDate>Wed, 14 Oct 2026 10:00:00 GMT</pubDate></item>
      <item><title>Issuer board meeting</title><pubDate>Wed, 14 Oct 2026 11:00:00 GMT</pubDate></item>
      <item><title>Issuer broken tail <description>truncated'''
    monkeypatch.setattr(news.requests, "get", lambda *a, **k: FakeResponse(payload))
    items = news._rss_items("https://example.test/rss")
    assert len(items) == 2
    assert items.partial is True
    assert all(item.findtext("title") for item in items)


def test_unrecoverable_html_or_xml_raises_parse_error(monkeypatch):
    monkeypatch.setattr(news.requests, "get", lambda *a, **k: FakeResponse("<html><body>Access denied"))
    with pytest.raises(ET.ParseError):
        news._rss_items("https://example.test/rss")


def test_namespace_declared_on_feed_root_is_supported_during_recovery(monkeypatch):
    payload = '''<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
      <item><title>Issuer filing</title><dc:date>2026-10-14</dc:date></item>
      <item><title>broken tail'''
    monkeypatch.setattr(news.requests, "get", lambda *a, **k: FakeResponse(payload))
    items = news._rss_items("https://example.test/rss")
    assert len(items) == 1
    assert items.partial is True
    assert items[0].find("{http://purl.org/dc/elements/1.1/}date") is not None
