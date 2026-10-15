import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).with_name("sector_data.py")
SPEC = importlib.util.spec_from_file_location("sector_data_under_test", MODULE_PATH)
sector_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sector_data)


class ETFUnderlyingIndexDiagnosticTests(unittest.TestCase):
    def test_value_and_dividend_are_explicitly_unsupported_for_sector_strength(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                mappings = sector_data._targeted_shortlist_mappings(
                    candidate_symbols=["VALUE", "DIVIDEND"],
                    existing_mapping_by_symbol={},
                    nifty500_industries={},
                    asof=pd.Timestamp("2026-10-15"),
                    nse_classifications={},
                    etf_symbols={"VALUE", "DIVIDEND"},
                )
                audit = pd.read_csv(
                    "data/reports/sector_candidate_mapping_20261015.csv"
                ).set_index("TckrSymb")
            finally:
                os.chdir(old_cwd)

        self.assertEqual(mappings, [])
        for symbol in ("VALUE", "DIVIDEND"):
            self.assertEqual(
                audit.loc[symbol, "MappingStatus"],
                "ETF_UNDERLYING_INDEX_UNSUPPORTED",
            )
            self.assertTrue(pd.isna(audit.loc[symbol, "MappedSector"]))
            self.assertTrue(pd.isna(audit.loc[symbol, "SectorIndexSymbol"]))
            self.assertIn("Official source:", audit.loc[symbol, "Reason"])

    def test_verified_psubankadd_etf_mapping_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                mappings = sector_data._targeted_shortlist_mappings(
                    candidate_symbols=["PSUBANKADD"],
                    existing_mapping_by_symbol={},
                    nifty500_industries={},
                    asof=pd.Timestamp("2026-10-15"),
                    nse_classifications={},
                    etf_symbols={"PSUBANKADD"},
                )
                audit = pd.read_csv(
                    "data/reports/sector_candidate_mapping_20261015.csv"
                ).set_index("TckrSymb")
            finally:
                os.chdir(old_cwd)

        self.assertEqual(len(mappings), 1)
        self.assertEqual(mappings[0]["Sector"], "Nifty PSU Bank")
        self.assertEqual(mappings[0]["SectorIndexSymbol"], "NIFTY PSU BANK")
        self.assertEqual(
            audit.loc["PSUBANKADD", "MappingStatus"],
            "ETF_UNDERLYING_INDEX_VERIFIED",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
