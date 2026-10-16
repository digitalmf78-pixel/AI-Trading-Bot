import importlib.util
import tempfile
import unittest
from pathlib import Path

import pandas as pd

MODULE_PATH = Path(__file__).with_name("sector_data.py")
SPEC = importlib.util.spec_from_file_location("sector_data_cache_reconciliation", MODULE_PATH)
sector_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sector_data)


class SectorMappingCacheReconciliationTests(unittest.TestCase):
    def test_unresolved_current_candidates_do_not_keep_stale_cached_mapping(self):
        old_map = pd.DataFrame([
            {"TckrSymb": "SPENCERS", "Sector": "Nifty Consumer Services", "SectorIndexSymbol": "NIFTY CONSUMER SERVICES"},
            {"TckrSymb": "MODINATUR", "Sector": "Nifty FMCG", "SectorIndexSymbol": "NIFTY FMCG"},
            {"TckrSymb": "OTHER", "Sector": "Nifty IT", "SectorIndexSymbol": "NIFTY IT"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "sector_candidate_mapping_20261015.csv"
            pd.DataFrame([
                {"TckrSymb": "SPENCERS", "MappingStatus": "WAIT_FOR_DATA"},
                {"TckrSymb": "MODINATUR", "MappingStatus": "WAIT_FOR_DATA"},
            ]).to_csv(audit_path, index=False)
            result = sector_data._remove_stale_unverified_candidate_mappings(old_map, audit_path)
        self.assertEqual(result["TckrSymb"].tolist(), ["OTHER"])

    def test_fresh_official_mapping_is_not_removed(self):
        old_map = pd.DataFrame([
            {"TckrSymb": "PSUBANKADD", "Sector": "Old", "SectorIndexSymbol": "OLD"},
            {"TckrSymb": "VALUE", "Sector": "Old", "SectorIndexSymbol": "OLD"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.csv"
            pd.DataFrame([
                {"TckrSymb": "PSUBANKADD", "MappingStatus": "WAIT_FOR_DATA"},
                {"TckrSymb": "VALUE", "MappingStatus": "ETF_UNDERLYING_INDEX_UNSUPPORTED"},
            ]).to_csv(audit_path, index=False)
            result = sector_data._remove_stale_unverified_candidate_mappings(
                old_map, audit_path, fresh_symbols={"PSUBANKADD"}
            )
        self.assertEqual(result["TckrSymb"].tolist(), ["PSUBANKADD"])

    def test_missing_audit_preserves_cache(self):
        old_map = pd.DataFrame([{"TckrSymb": "ABC", "Sector": "Nifty IT", "SectorIndexSymbol": "NIFTY IT"}])
        with tempfile.TemporaryDirectory() as tmp:
            result = sector_data._remove_stale_unverified_candidate_mappings(old_map, Path(tmp) / "missing.csv")
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["TckrSymb"], "ABC")


if __name__ == "__main__":
    unittest.main(verbosity=2)
