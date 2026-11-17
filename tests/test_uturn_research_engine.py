import unittest
import pandas as pd
from research.ecms_uturn.cache_date_utils import normalize_session_dates
from research.ecms_uturn.uturn_research_engine import (
    calculate_uturn, relative_volume, technical_confirmation, zone_touched
)

class UTurnResearchEngineTests(unittest.TestCase):
    def test_nse_cache_dates_preserve_iso_and_parse_legacy_day_first(self):
        values = pd.Series([
            "2026-04-01",
            "01/04/2026",
            "04/01/2026",
            "20260401",
            "01042026",
            "not-a-date",
        ])
        normalized = normalize_session_dates(values).tolist()
        self.assertEqual(normalized[:5], [
            "2026-04-01",
            "2026-04-01",
            "2026-01-04",
            "2026-04-01",
            "2026-04-01",
        ])
        self.assertTrue(pd.isna(normalized[5]))

    def test_formula_and_two_percent_zone(self):
        x=calculate_uturn(1000,20,18,"FY25","FY26","CONSOLIDATED","CONSOLIDATED")
        self.assertEqual(x.status,"PROVISIONAL_TARGET")
        self.assertAlmostEqual(x.reference_pe,50)
        self.assertAlmostEqual(x.expected_correction,100)
        self.assertAlmostEqual(x.target,900)
        self.assertAlmostEqual(x.zone_low,882)
        self.assertAlmostEqual(x.zone_high,918)

    def test_no_eps_drop_has_no_target(self):
        x=calculate_uturn(1000,20,20,"FY25","FY26","CONSOLIDATED","CONSOLIDATED")
        self.assertEqual(x.status,"NO_EPS_DECLINE")
        self.assertIsNone(x.target)

    def test_basis_mismatch_waits(self):
        x=calculate_uturn(1000,20,18,"FY25","FY26","STANDALONE","CONSOLIDATED")
        self.assertEqual(x.status,"WAIT_FOR_DATA")
        self.assertEqual(x.reason,"REPORTING_BASIS_MISMATCH")

    def test_missing_basis_does_not_crash(self):
        x=calculate_uturn(1000,20,18,"FY25","FY26",None,"CONSOLIDATED")
        self.assertEqual(x.status,"WAIT_FOR_DATA")
        self.assertEqual(x.reason,"MISSING_REPORTING_BASIS")

    def test_non_consecutive_fy_is_rejected(self):
        x=calculate_uturn(1000,20,18,"FY24","FY26","CONSOLIDATED","CONSOLIDATED")
        self.assertEqual(x.status,"WAIT_FOR_DATA")
        self.assertEqual(x.reason,"INVALID_OR_NON_CONSECUTIVE_FY_PAIR")

    def test_zone_requires_valid_range_overlap(self):
        self.assertTrue(zone_touched(890,895,880,920))
        self.assertFalse(zone_touched(930,950,880,920))
        self.assertFalse(zone_touched(-1,895,880,920))

    def test_rvol_uses_exactly_20_prior_sessions(self):
        self.assertAlmostEqual(relative_volume(300,[100]*20),3.0)
        self.assertIsNone(relative_volume(300,[100]*19))
        self.assertIsNone(relative_volume(300,[0]*20))

    def test_same_session_delivery_and_rvol_required(self):
        self.assertEqual(technical_confirmation(890,900,880,920,65,1.8),"TECHNICAL_CONFIRMATION_ONLY")
        self.assertEqual(technical_confirmation(890,900,880,920,59.9,1.8),"ZONE_TOUCH_NOT_CONFIRMED")
        self.assertEqual(technical_confirmation(890,900,880,920,None,1.8),"WAIT_FOR_DATA")
        self.assertEqual(technical_confirmation(890,900,880,920,120,1.8),"WAIT_FOR_DATA")

if __name__=="__main__": unittest.main()
