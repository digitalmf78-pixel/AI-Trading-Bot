"""Regression tests for official sector-index aliases and issuer announcement matching."""
import os
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from unittest.mock import patch

import pandas as pd
import sector_data
import news_catalyst as news


class SectorIndexAliasTests(unittest.TestCase):
    def test_archive_index_suffix_is_normalized_without_fuzzy_matching(self):
        self.assertEqual(sector_data._normalise_index_name("Nifty Power Index"), "NIFTY POWER")
        self.assertEqual(sector_data._normalise_index_name("Nifty Transportation & Logistics Index"), "NIFTY TRANSPORTATION AND LOGISTICS")
        self.assertEqual(sector_data._normalise_index_name("Nifty Non-Cyclical Consumer Index"), "NIFTY NON-CYCLICAL CONSUMER")
        self.assertNotEqual(sector_data._normalise_index_name("Nifty Power Index Extra"), "NIFTY POWER")

    def test_archive_history_maps_all_index_suffix_variants_to_exact_dates(self):
        asof = pd.Timestamp("2026-10-19")
        def fake_archive(_session, day):
            rows = []
            for _sector, _files, index_name, _symbol in sector_data.SECTOR_INDICES:
                raw_name = index_name if index_name.upper().endswith(" INDEX") else index_name + " Index"
                rows.append({
                    "Index Name": raw_name,
                    "Index Date": pd.Timestamp(day).strftime("%d-%m-%Y"),
                    "Closing Index Value": 1000.0 + len(rows),
                })
            return pd.DataFrame(rows)
        with patch.object(sector_data, "_download_daily_index_file", side_effect=fake_archive), \
             patch.object(sector_data.time, "sleep", return_value=None):
            rows, exact = sector_data._history_from_nse_archive(object(), asof)
        self.assertEqual(exact, len(sector_data.SECTOR_INDICES))
        self.assertEqual({r["Sector"] for r in rows if r["Date"] == asof.strftime("%Y-%m-%d")},
                         {item[0] for item in sector_data.SECTOR_INDICES})

    def test_textile_logistics_and_construction_use_official_benchmarks(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                rows = sector_data._targeted_shortlist_mappings(
                    candidate_symbols=["LAGNAM", "OMFREIGHT", "BCPL"],
                    existing_mapping_by_symbol={},
                    nifty500_industries={},
                    asof=pd.Timestamp("2026-10-19"),
                    nse_classifications={
                        "LAGNAM": {"macro": "CONSUMER DISCRETIONARY", "sector": "TEXTILES", "industry": "TEXTILES AND APPARELS", "basicIndustry": "OTHER TEXTILE PRODUCTS"},
                        "OMFREIGHT": {"macro": "SERVICES", "sector": "SERVICES", "industry": "TRANSPORT SERVICES", "basicIndustry": "LOGISTICS SOLUTION PROVIDER"},
                        "BCPL": {"macro": "INDUSTRIALS", "sector": "CONSTRUCTION", "industry": "CONSTRUCTION", "basicIndustry": "CIVIL CONSTRUCTION"},
                    },
                    etf_symbols=set(),
                )
            finally:
                os.chdir(old_cwd)
        by_symbol = {r["TckrSymb"]: r for r in rows}
        self.assertEqual(by_symbol["LAGNAM"]["Sector"], "Nifty Non-Cyclical Consumer")
        self.assertEqual(by_symbol["OMFREIGHT"]["Sector"], "Nifty Transportation and Logistics")
        self.assertEqual(by_symbol["BCPL"]["Sector"], "Nifty Construction")

    def test_unclassified_symbol_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                rows = sector_data._targeted_shortlist_mappings(
                    candidate_symbols=["UNKNOWNXYZ"], existing_mapping_by_symbol={},
                    nifty500_industries={}, asof=pd.Timestamp("2026-10-19"),
                    nse_classifications={}, etf_symbols=set(),
                )
            finally:
                os.chdir(old_cwd)
        self.assertEqual(rows, [])


class NewsAnnouncementMatchingTests(unittest.TestCase):
    def test_unrelated_global_rss_records_do_not_count_as_candidate_coverage(self):
        # A successful global RSS fetch with other issuers' records is not coverage
        # for this candidate when its issuer-filtered NSE API call failed.
        self.assertEqual(
            news._premarket_news_status(official_count=0, secondary_count=0, api_covered=False),
            "WAIT_FOR_DATA",
        )

    def test_successful_empty_issuer_api_can_confirm_no_news(self):
        self.assertEqual(
            news._premarket_news_status(official_count=0, secondary_count=0, api_covered=True),
            "NO_NEWS_FOUND",
        )

    def test_secondary_only_remains_unverified_when_official_api_covered(self):
        self.assertEqual(
            news._premarket_news_status(official_count=0, secondary_count=1, api_covered=True),
            "SECONDARY_ONLY_UNVERIFIED",
        )

    def test_distinctive_single_word_registered_company_name_matches(self):
        self.assertEqual(
            news._issuer_match_reason("MARICO", "Marico Limited files quarterly results", "Marico Limited"),
            "COMPANY_NAME_MATCH",
        )

    def test_generic_single_word_name_does_not_match(self):
        self.assertEqual(news._issuer_match_reason("TECH", "Tech shares rise today", "Tech Limited"), "")

    def test_official_symbol_field_matches_exactly(self):
        item = ET.fromstring('<item><title>General Updates</title><symbol>MARICO</symbol></item>')
        self.assertTrue(news._item_has_exact_symbol(item, "MARICO"))
        self.assertFalse(news._item_has_exact_symbol(item, "MARIC"))

    def test_market_quote_pages_are_not_news_catalysts(self):
        self.assertTrue(news._is_market_quote_headline("OWAIS Share Price - Live NSE: OWAIS Stock Price & Chart - Upstox"))
        self.assertTrue(news._is_market_quote_headline("SRTL Share Price Today, Live Chart & News"))
        self.assertFalse(news._is_market_quote_headline("Company receives a major order and announces expansion"))

    def test_issuer_api_exact_symbol_field_is_accepted_even_if_title_omits_ticker(self):
        item = ET.fromstring(
            '<item><title>General Updates</title><description>Issuer filing</description>'
            '<symbol>MARICO</symbol><pubDate>Sun, 18 Oct 2026 10:00:00 +0530</pubDate>'
            '<link>https://nsearchives.nseindia.com/corporate/example.pdf</link></item>'
        )
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            old_mode = os.environ.get("NEWS_SCAN_MODE")
            os.chdir(tmp)
            os.environ["NEWS_SCAN_MODE"] = "EOD"
            try:
                def fake_rss(url, params=None):
                    if "news.google.com" in url:
                        return news._RSSItemList([])
                    return news._RSSItemList([])
                with patch.object(news, "_read_equity_master", return_value={}), \
                     patch.object(news, "_rss_items", side_effect=fake_rss), \
                     patch.object(news, "_nse_announcement_api_items", return_value=news._RSSItemList([item], available=True)) as api_mock:
                    frame, _status = news.collect_catalyst_news(
                        pd.DataFrame({"TckrSymb": ["MARICO"], "Delivery_1": [60], "Delivery_2": [61], "Delivery_3": [62], "Delivery_4": [63], "Delivery_5": [64]}),
                        "2026-10-19",
                    )
                api_mock.assert_called_once()
                self.assertTrue((frame["SourceType"] == "primary").any())
                self.assertIn("MARICO", frame["TckrSymb"].tolist())
            finally:
                os.chdir(old_cwd)
                if old_mode is None:
                    os.environ.pop("NEWS_SCAN_MODE", None)
                else:
                    os.environ["NEWS_SCAN_MODE"] = old_mode

    def test_official_rss_exact_symbol_field_is_accepted_even_if_title_omits_ticker(self):
        item = ET.fromstring(
            '<item><title>General Updates</title><description>Company filing</description>'
            '<symbol>MARICO</symbol><pubDate>Sun, 18 Oct 2026 10:00:00 +0530</pubDate>'
            '<link>https://archives.nseindia.com/example.pdf</link></item>'
        )
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            old_mode = os.environ.get("NEWS_SCAN_MODE")
            os.chdir(tmp)
            os.environ["NEWS_SCAN_MODE"] = "EOD"
            try:
                def fake_rss(url, params=None):
                    if "Google" in url or "news.google.com" in url:
                        return news._RSSItemList([])
                    if "Online_announcements.xml" in url:
                        return news._RSSItemList([item])
                    return news._RSSItemList([])
                with patch.object(news, "_read_equity_master", return_value={"MARICO": "Marico Limited"}), \
                     patch.object(news, "_rss_items", side_effect=fake_rss), \
                     patch.object(news, "_nse_announcement_api_items", return_value=news._RSSItemList([], available=True)):
                    frame, _status = news.collect_catalyst_news(
                        pd.DataFrame({"TckrSymb": ["MARICO"], "Delivery_1": [60], "Delivery_2": [61], "Delivery_3": [62], "Delivery_4": [63], "Delivery_5": [64]}),
                        "2026-10-19",
                    )
                self.assertTrue((frame["SourceType"] == "primary").any())
                self.assertIn("MARICO", frame["TckrSymb"].tolist())
            finally:
                os.chdir(old_cwd)
                if old_mode is None:
                    os.environ.pop("NEWS_SCAN_MODE", None)
                else:
                    os.environ["NEWS_SCAN_MODE"] = old_mode


if __name__ == "__main__":
    unittest.main(verbosity=2)
