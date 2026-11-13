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


    def test_persistent_mapping_rows_are_scoped_to_current_candidates(self):
        rows = [
            {"TckrSymb": "ABC", "Sector": "Nifty IT", "SectorIndexSymbol": "NIFTY IT"},
            {"TckrSymb": "XYZ", "Sector": "Nifty Bank", "SectorIndexSymbol": "NIFTY BANK"},
            {"TckrSymb": "QWE", "Sector": "Nifty Auto", "SectorIndexSymbol": "NIFTY AUTO"},
        ]
        result = sector_data._scope_mapping_rows_to_candidates(rows, ["xyz", "ABC"])
        self.assertEqual(set(result["TckrSymb"]), {"ABC", "XYZ"})
        self.assertNotIn("QWE", set(result["TckrSymb"]))

    def test_empty_candidate_list_persists_no_company_mappings(self):
        rows = [
            {"TckrSymb": "ABC", "Sector": "Nifty IT", "SectorIndexSymbol": "NIFTY IT"},
        ]
        result = sector_data._scope_mapping_rows_to_candidates(rows, [])
        self.assertTrue(result.empty)


    def test_official_constituent_cache_hit_avoids_network(self):
        import json
        import time

        with tempfile.TemporaryDirectory() as tmp:
            original_cache_dir = sector_data.CONSTITUENT_CACHE_DIR
            sector_data.CONSTITUENT_CACHE_DIR = Path(tmp)
            try:
                cache_path = Path(tmp) / "NIFTY_AUTO.csv"
                cache_path.write_text("Symbol,Company Name\nABC,ABC Limited\nXYZ,XYZ Limited\n", encoding="utf-8")
                (Path(tmp) / "NIFTY_AUTO.json").write_text(json.dumps({
                    "fetched_at_epoch": time.time(),
                    "source_filename": "ind_niftyautolist.csv",
                }), encoding="utf-8")

                class NoNetworkSession:
                    def get(self, *args, **kwargs):
                        raise AssertionError("fresh official constituent cache should avoid network")

                rows = sector_data._download_constituents(
                    NoNetworkSession(), "Nifty Auto", ["ind_niftyautolist.csv"], "NIFTY AUTO"
                )
                self.assertEqual({row["TckrSymb"] for row in rows}, {"ABC", "XYZ"})
            finally:
                sector_data.CONSTITUENT_CACHE_DIR = original_cache_dir

    def test_expired_official_constituent_cache_refreshes_from_source(self):
        import json
        import time

        with tempfile.TemporaryDirectory() as tmp:
            original_cache_dir = sector_data.CONSTITUENT_CACHE_DIR
            sector_data.CONSTITUENT_CACHE_DIR = Path(tmp)
            try:
                cache_path = Path(tmp) / "NIFTY_AUTO.csv"
                cache_path.write_text("Symbol\nOLD\n", encoding="utf-8")
                (Path(tmp) / "NIFTY_AUTO.json").write_text(json.dumps({
                    "fetched_at_epoch": time.time() - sector_data.CONSTITUENT_CACHE_TTL_SECONDS - 1,
                    "source_filename": "old.csv",
                }), encoding="utf-8")

                class Response:
                    status_code = 200
                    content = b"Symbol,Company Name\nNEW,New Limited\n"
                class Session:
                    def __init__(self):
                        self.calls = []
                    def get(self, url, **kwargs):
                        self.calls.append(url)
                        return Response()

                session = Session()
                rows = sector_data._download_constituents(
                    session, "Nifty Auto", ["ind_niftyautolist.csv"], "NIFTY AUTO"
                )
                self.assertEqual(len(session.calls), 1)
                self.assertEqual([row["TckrSymb"] for row in rows], ["NEW"])
                self.assertIn("NEW", cache_path.read_text(encoding="utf-8"))
            finally:
                sector_data.CONSTITUENT_CACHE_DIR = original_cache_dir

    def test_nse_session_warmup_runs_once_after_success(self):
        class Response:
            def __init__(self, status_code):
                self.status_code = status_code
        class Session:
            def __init__(self):
                self.calls = []
            def get(self, url, **kwargs):
                self.calls.append(url)
                return Response(403 if len(self.calls) == 1 else 200)

        session = Session()
        sector_data._warm_nse_session(session)
        sector_data._warm_nse_session(session)
        self.assertEqual(len(session.calls), 2)



    def test_official_nse_quote_classification_cache_hit_skips_network(self):
        import time

        with tempfile.TemporaryDirectory() as tmp:
            original_dir = sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR
            sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR = Path(tmp)
            try:
                sector_data._save_nse_quote_classification_cache(
                    "ABC",
                    {"macro": "Services", "sector": "Information Technology",
                     "industry": "IT - Software", "basicIndustry": "Software"},
                    now_epoch=time.time(),
                )
                original_fetch = sector_data._fetch_nse_quote_industry_classification
                def no_network(_session, _symbol):
                    raise AssertionError("fresh official classification cache should avoid network")
                sector_data._fetch_nse_quote_industry_classification = no_network
                result = sector_data._nse_quote_industry_classification(object(), "abc")
                self.assertEqual(result["sector"], "Information Technology")
                self.assertEqual(result["basicIndustry"], "Software")
                sector_data._fetch_nse_quote_industry_classification = original_fetch
            finally:
                sector_data._fetch_nse_quote_industry_classification = original_fetch
                sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR = original_dir

    def test_expired_official_nse_quote_classification_is_refetched_and_replaced(self):
        import time

        with tempfile.TemporaryDirectory() as tmp:
            original_dir = sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR
            original_fetch = sector_data._fetch_nse_quote_industry_classification
            sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR = Path(tmp)
            try:
                sector_data._save_nse_quote_classification_cache(
                    "ABC", {"sector": "Old Sector"},
                    now_epoch=time.time() - sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_TTL_SECONDS - 5,
                )
                calls = []
                def fetch(_session, symbol):
                    calls.append(symbol)
                    return {"macro": "Services", "sector": "Information Technology",
                            "industry": "IT - Software", "basicIndustry": "Software"}
                sector_data._fetch_nse_quote_industry_classification = fetch
                result = sector_data._nse_quote_industry_classification(object(), "ABC")
                self.assertEqual(calls, ["ABC"])
                self.assertEqual(result["sector"], "Information Technology")
                cached = sector_data._load_nse_quote_classification_cache("ABC")
                self.assertEqual(cached["sector"], "Information Technology")
            finally:
                sector_data._fetch_nse_quote_industry_classification = original_fetch
                sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR = original_dir

    def test_empty_or_failed_classification_is_never_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_dir = sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR
            original_fetch = sector_data._fetch_nse_quote_industry_classification
            sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR = Path(tmp)
            try:
                self.assertFalse(sector_data._save_nse_quote_classification_cache("ABC", {}))
                def fail(_session, _symbol):
                    raise RuntimeError("official endpoint unavailable")
                sector_data._fetch_nse_quote_industry_classification = fail
                with self.assertRaisesRegex(RuntimeError, "official endpoint unavailable"):
                    sector_data._nse_quote_industry_classification(object(), "ABC")
                self.assertFalse(sector_data._nse_quote_classification_cache_path("ABC").exists())
            finally:
                sector_data._fetch_nse_quote_industry_classification = original_fetch
                sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR = original_dir

    def test_quote_classification_cache_rejects_wrong_symbol_or_source(self):
        import json
        import time

        with tempfile.TemporaryDirectory() as tmp:
            original_dir = sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR
            sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR = Path(tmp)
            try:
                path = sector_data._nse_quote_classification_cache_path("ABC")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({
                    "schema_version": sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_SCHEMA_VERSION,
                    "symbol": "XYZ",
                    "source": "UNVERIFIED",
                    "fetched_at_epoch": time.time(),
                    "classification": {"sector": "Information Technology"},
                }), encoding="utf-8")
                self.assertIsNone(sector_data._load_nse_quote_classification_cache("ABC"))
            finally:
                sector_data.NSE_QUOTE_CLASSIFICATION_CACHE_DIR = original_dir


if __name__ == "__main__":
    unittest.main(verbosity=2)
