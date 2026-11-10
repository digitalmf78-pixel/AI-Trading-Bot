"""Risk-config consistency warnings are informational and never change status."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pandas as pd

from risk_controls import (
    apply_portfolio_risk_controls,
    load_risk_config,
    risk_config_warnings,
)

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
    "max_open_positions": 4,
    "current_open_positions": 0,
}


def _write(tmp_path, config):
    path = tmp_path / "risk.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_balanced_config_has_no_warnings():
    assert risk_config_warnings(CONFIG) == []


def test_dominated_single_position_cap_is_flagged():
    config = dict(CONFIG, max_single_position_pct=2, risk_per_trade_pct=2)
    warnings = risk_config_warnings(config)
    assert any("SINGLE_POSITION_CAP_DOMINATES" in message for message in warnings)


def test_tight_stop_limit_is_flagged():
    config = dict(CONFIG, max_stop_distance_pct=2)
    warnings = risk_config_warnings(config)
    assert any("STOP_DISTANCE_LIMIT_TOO_TIGHT" in message for message in warnings)


def test_median_stop_warning_is_logged_but_status_is_unchanged(tmp_path):
    config_path = _write(tmp_path, dict(CONFIG, max_stop_distance_pct=5))
    frame = pd.DataFrame([
        {"TckrSymb": "A", "Sector": "IT", "EntryPricePlan": 100, "StopLossPlan": 90},
        {"TckrSymb": "B", "Sector": "IT", "EntryPricePlan": 100, "StopLossPlan": 92},
        {"TckrSymb": "C", "Sector": "IT", "EntryPricePlan": 100, "StopLossPlan": 94},
    ])
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        out = apply_portfolio_risk_controls(frame, config_path)
    assert "median stop distance" in buffer.getvalue()
    # Informational only: every row still gets the same REJECT as before.
    assert set(out["RiskControlStatus"]) == {"REJECT"}


def test_invalid_risk_config_secret_fails_closed_with_message(tmp_path, monkeypatch):
    monkeypatch.setenv("RISK_CONFIG_JSON", "{not-json")
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        config = load_risk_config(tmp_path / "missing.json")
    assert config == {}
    assert "[RISK][ERROR]" in buffer.getvalue()
