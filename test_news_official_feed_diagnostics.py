"""Focused regression tests for official RSS diagnostics and ticker matching."""
import importlib.util
from datetime import timezone
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

MODULE_PATH = Path(__file__).with_name("news_catalyst.py")
spec = importlib.util.spec_from_file_location("news_catalyst_under_test", MODULE_PATH)
news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(news)


class OfficialFeedDiagnosticTests(unittest.TestCase):
    def test_namespaced_rss_fields_are_read(self):
        item = ET.fromstring(
            '<item xmlns:x="urn:test"><x:title>Singer India Limited</x:title>'
            '<x:description>Quarterly results filed</x:description></item>'
        )
        self.assertEqual(news._item_text(item, "title"), "Singer India Limited")
        self.assertEqual(news._item_text(item, "description"), "Quarterly results filed")

    def test_filing_date_tag_is_parsed(self):
        item = ET.fromstring('<item><filingDate>2026-10-16T12:00:00Z</filingDate></item>')
        stamp = news._published(item)
        self.assertIsNotNone(stamp)
        self.assertEqual(stamp.tzinfo, timezone.utc)
        self.assertEqual(stamp.year, 2026)

    def test_explicit_nse_ticker_with_colon_matches(self):
        self.assertEqual(
            news._issuer_match_reason("SINGERIND", "NSE: SINGERIND announces filing", ""),
            "EXPLICIT_TICKER_MATCH",
        )

    def test_parenthesized_ticker_matches(self):
        self.assertEqual(
            news._issuer_match_reason("SINGERIND", "Update for (SINGERIND)", ""),
            "EXPLICIT_TICKER_MATCH",
        )

    def test_bare_ambiguous_ticker_does_not_match(self):
        self.assertEqual(news._issuer_match_reason("TECH", "Tech shares rose today", ""), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
