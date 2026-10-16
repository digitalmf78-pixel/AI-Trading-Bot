"""Tests for bounded, namespace-safe NSE RSS field diagnostics."""
import importlib.util
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

MODULE_PATH = Path(__file__).with_name("news_catalyst.py")
spec = importlib.util.spec_from_file_location("news_catalyst_under_test_diag", MODULE_PATH)
news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(news)


class RSSDiagnosticsTests(unittest.TestCase):
    def test_reads_common_rss_fields(self):
        item = ET.fromstring(
            "<item><title>Aro Granite Industries Limited</title>"
            "<description>Company has informed the Exchange.</description>"
            "<link>https://example.invalid/notice</link></item>"
        )
        fields = news._rss_debug_fields(item)
        self.assertEqual(fields["title"], "Aro Granite Industries Limited")
        self.assertEqual(fields["description"], "Company has informed the Exchange.")
        self.assertEqual(fields["link"], "https://example.invalid/notice")

    def test_reads_namespace_qualified_fields(self):
        item = ET.fromstring(
            "<item xmlns:dc='http://purl.org/dc/elements/1.1/'>"
            "<title>Announcement</title><dc:creator>NSE</dc:creator></item>"
        )
        self.assertEqual(news._rss_debug_fields(item)["creator"], "NSE")

    def test_field_count_and_value_length_are_bounded(self):
        item = ET.fromstring("<item>" + "".join(f"<f{i}>{'x'*300}</f{i}>" for i in range(20)) + "</item>")
        fields = news._rss_debug_fields(item, max_fields=5, max_value=20)
        self.assertLessEqual(len(fields), 5)
        self.assertTrue(all(len(value) <= 20 for value in fields.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
