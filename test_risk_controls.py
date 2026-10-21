import json
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from risk_controls import apply_portfolio_risk_controls, REQUIRED_KEYS

CONFIG = {
    "account_equity_inr": 1_000_000,
    "risk_per_trade_pct": 1,
    "max_single_position_pct": 20,
    "max_sector_exposure_pct": 35,
    "max_total_exposure_pct": 80,
    "max_stop_distance_pct": 8,
    "current_total_exposure_pct": 20,
    "sector_exposure_pct_by_sector": {"IT": 10},
    "portfolio_exposure_verified": True,
}

class RiskControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name) / "risk.json"
        self.config.write_text(json.dumps(CONFIG), encoding="utf-8")
        self.frame = pd.DataFrame([{"TckrSymb":"ABC", "Sector":"IT", "EntryPricePlan":100, "StopLossPlan":95}])
    def tearDown(self): self.temp.cleanup()
    def test_valid_risk_config_passes_and_sizes_position(self):
        out = apply_portfolio_risk_controls(self.frame, self.config)
        self.assertEqual(out.iloc[0]["RiskControlStatus"], "PASS")
        self.assertEqual(out.iloc[0]["ProposedPositionQty"], 2000)
    def test_missing_config_waits(self):
        self.config.write_text("{}", encoding="utf-8")
        out = apply_portfolio_risk_controls(self.frame, self.config)
        self.assertEqual(out.iloc[0]["RiskControlStatus"], "WAIT_FOR_DATA")
    def test_stop_distance_limit_rejects(self):
        self.frame.loc[0,"StopLossPlan"] = 80
        out = apply_portfolio_risk_controls(self.frame, self.config)
        self.assertEqual(out.iloc[0]["RiskControlStatus"], "REJECT")
        self.assertIn("STOP_DISTANCE_EXCEEDS_LIMIT", out.iloc[0]["RiskControlReason"])
    def test_missing_sector_exposure_waits(self):
        CONFIG2 = dict(CONFIG); CONFIG2["sector_exposure_pct_by_sector"] = {}
        self.config.write_text(json.dumps(CONFIG2), encoding="utf-8")
        out = apply_portfolio_risk_controls(self.frame, self.config)
        self.assertEqual(out.iloc[0]["RiskControlStatus"], "WAIT_FOR_DATA")

if __name__ == "__main__": unittest.main()
