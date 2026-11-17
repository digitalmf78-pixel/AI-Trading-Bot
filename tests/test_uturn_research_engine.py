import unittest
from research.ecms_uturn.uturn_research_engine import (
    calculate_uturn, relative_volume, technical_confirmation, zone_touched
)

class UTurnResearchEngineTests(unittest.TestCase):
    def test_formula_and_two_percent_zone(self):
        x = calculate_uturn(1000, 20, 18, "FY25", "FY26", "CONSOLIDATED", "CONSOLIDATED")
        self.assertEqual(x.status, "PROVISIONAL_TARGET")
        self.assertAlmostEqual(x.reference_pe, 50)
        self.assertAlmostEqual(x.expected_correction, 100)
        self.assertAlmostEqual(x.target, 900)
        self.assertAlmostEqual(x.zone_low, 882)
        self.assertAlmostEqual(x.zone_high, 918)

    def test_no_eps_drop_has_no_target(self):
        x = calculate_uturn(1000, 20, 20, "FY25", "FY26", "CONSOLIDATED", "CONSOLIDATED")
        self.assertEqual(x.status, "NO_EPS_DECLINE")
        self.assertIsNone(x.target)

    def test_basis_mismatch_waits(self):
        x = calculate_uturn(1000, 20, 18, "FY25", "FY26", "STANDALONE", "CONSOLIDATED")
        self.assertEqual(x.status, "WAIT_FOR_DATA")
        self.assertEqual(x.reason, "REPORTING_BASIS_MISMATCH")

    def test_zone_requires_range_overlap(self):
        self.assertTrue(zone_touched(890, 895, 880, 920))
        self.assertFalse(zone_touched(930, 950, 880, 920))

    def test_rvol_uses_exactly_20_prior_sessions(self):
        self.assertAlmostEqual(relative_volume(300, [100] * 20), 3.0)
        self.assertIsNone(relative_volume(300, [100] * 19))

    def test_same_session_delivery_and_rvol_required(self):
        self.assertEqual(technical_confirmation(890, 900, 880, 920, 65, 1.8), "TECHNICAL_CONFIRMATION_ONLY")
        self.assertEqual(technical_confirmation(890, 900, 880, 920, 59.9, 1.8), "ZONE_TOUCH_NOT_CONFIRMED")
        self.assertEqual(technical_confirmation(890, 900, 880, 920, None, 1.8), "WAIT_FOR_DATA")

if __name__ == "__main__":
    unittest.main()
