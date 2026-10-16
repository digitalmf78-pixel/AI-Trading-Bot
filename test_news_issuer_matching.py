"""Regression tests for V8 issuer matching in NSE/secondary news feeds."""
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("news_catalyst.py")
spec = importlib.util.spec_from_file_location("news_catalyst_under_test", MODULE_PATH)
news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(news)


class IssuerMatchingTests(unittest.TestCase):
    def test_registered_company_name_matches_after_legal_suffix_removed(self):
        self.assertEqual(
            news._issuer_match_reason(
                "MODINATUR",
                "Modi Naturals Limited has informed the Exchange about quarterly results",
                "Modi Naturals Limited",
            ),
            "COMPANY_NAME_MATCH",
        )

    def test_company_name_with_punctuation_matches_normalized_text(self):
        self.assertEqual(
            news._issuer_match_reason(
                "JKIPL",
                "Jinkushal Industries (JKIPL.NS) Climbs 3.18%",
                "Jinkushal Industries Limited",
            ),
            "COMPANY_NAME_MATCH",
        )

    def test_distinctive_single_token_company_name_matches(self):
        self.assertEqual(
            news._issuer_match_reason("AROGRANITE", "Arogranite reports new order", "Arogranite"),
            "COMPANY_NAME_MATCH",
        )

    def test_bare_ticker_as_ordinary_word_is_not_accepted(self):
        self.assertEqual(news._issuer_match_reason("AKASH", "Akash clouds expected today", "Akash Limited"), "")

    def test_explicit_ticker_identifier_is_accepted(self):
        self.assertEqual(
            news._issuer_match_reason("JKIPL", "Market update for JKIPL.NS", "Unrelated Registered Name"),
            "EXPLICIT_TICKER_MATCH",
        )

    def test_unrelated_company_name_does_not_match(self):
        self.assertEqual(
            news._issuer_match_reason("MODINATUR", "Tata Motors announces results", "Modi Naturals Limited"),
            "",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
