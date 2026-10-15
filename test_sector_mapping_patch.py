"""Focused regression tests for the issuer-evidence sector-mapping fallback."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sector_data


class IssuerEvidenceMappingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_cwd = os.getcwd()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def map_symbols(self, symbols, etfs=None):
        return sector_data._targeted_shortlist_mappings(
            candidate_symbols=symbols,
            existing_mapping_by_symbol={},
            nifty500_industries={},
            asof=sector_data.pd.Timestamp("2026-10-14"),
            nse_classifications={},
            etf_symbols=set(etfs or []),
        )

    def test_amjland_maps_only_with_reviewed_issuer_evidence(self):
        rows = self.map_symbols(["AMJLAND"])
        self.assertEqual(rows, [{
            "TckrSymb": "AMJLAND",
            "Sector": "Nifty Realty",
            "SectorIndexSymbol": "NIFTY REALTY",
        }])

    def test_akash_and_efcil_remain_wait_for_data(self):
        self.assertEqual(self.map_symbols(["AKASH", "EFCIL"]), [])

    def test_unreviewed_symbol_is_not_guessed(self):
        self.assertEqual(self.map_symbols(["UNKNOWNXYZ"]), [])

    def test_etfs_do_not_get_company_sector_mapping(self):
        self.assertEqual(
            self.map_symbols(["AONELIQUID", "HDFCBSE500"], etfs=["AONELIQUID", "HDFCBSE500"]),
            [],
        )

    def test_value_etf_is_explicitly_unsupported_not_sector_mapped(self):
        self.assertEqual(
            self.map_symbols(["VALUE"], etfs=["VALUE"]),
            [],
        )

    def test_unverified_dividend_etf_is_not_guessed(self):
        self.assertEqual(
            self.map_symbols(["DIVIDEND"], etfs=["DIVIDEND"]),
            [],
        )

    def test_equities_without_exact_tracked_sector_evidence_remain_unmapped(self):
        self.assertEqual(self.map_symbols(["BEDMUTHA", "JKIPL", "AROGRANITE"]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
