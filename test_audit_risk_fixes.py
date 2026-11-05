"""Regression coverage for the scanner audit fixes requested on 2026-11-05."""
import json
from datetime import date

import pandas as pd

import delivery_filter
import fundamental_filter
from risk_controls import apply_portfolio_risk_controls
from volume_gainer import prepare_equity_data


def test_zero_previous_close_produces_nan_price_change():
    frame = pd.DataFrame([
        {"TckrSymb": "AAA", "SctySrs": "EQ", "OpnPric": 100, "HghPric": 111,
         "LwPric": 99, "ClsPric": 110, "PrvsClsgPric": 0, "TtlTradgVol": 1000},
        {"TckrSymb": "BBB", "SctySrs": "EQ", "OpnPric": 100, "HghPric": 111,
         "LwPric": 99, "ClsPric": 110, "PrvsClsgPric": 100, "TtlTradgVol": 1000},
    ])
    prepared = prepare_equity_data(frame, etf_symbols=set()).set_index("TckrSymb")
    assert pd.isna(prepared.loc["AAA", "PriceChangePct"])
    assert prepared.loc["BBB", "PriceChangePct"] == 10


def test_stale_delivery_window_cannot_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(delivery_filter, "AUDIT_DIR", tmp_path / "reports")
    reports = [(date(2026, 1, day), pd.DataFrame({
        "SYMBOL": ["AAA"], "SERIES": ["EQ"], "DELIV_PER": [70.0],
    })) for day in range(5, 10)]
    candidates = pd.DataFrame([{"TckrSymb": "AAA", "SctySrs": "EQ"}])

    qualified, audit = delivery_filter.apply_delivery_filter(
        candidates, "2026-02-02", sessions=reports,
    )

    assert qualified.empty
    assert audit.iloc[0]["DeliveryStatus"] == "WAIT_FOR_DATA_STALE_REPORT"
    assert bool(audit.iloc[0]["DeliveryWindowStale"]) is True


def test_missing_position_counts_fail_closed(tmp_path):
    config = {
        "account_equity_inr": 100000, "risk_per_trade_pct": 1,
        "max_single_position_pct": 25, "max_sector_exposure_pct": 50,
        "max_total_exposure_pct": 100, "max_stop_distance_pct": 4,
        "current_total_exposure_pct": 0, "sector_exposure_pct_by_sector": {},
        "portfolio_exposure_verified": True,
    }
    path = tmp_path / "risk.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    frame = pd.DataFrame([{
        "TckrSymb": "AAA", "Sector": "Industrials",
        "EntryPricePlan": 100, "StopLossPlan": 95,
    }])

    result = apply_portfolio_risk_controls(frame, path)

    assert result.iloc[0]["RiskControlStatus"] == "WAIT_FOR_DATA"
    assert "max_open_positions" in result.iloc[0]["RiskControlReason"]
    assert "current_open_positions" in result.iloc[0]["RiskControlReason"]


def test_created_threshold_template_has_explicit_strong_fundamental_baseline(monkeypatch, tmp_path):
    monkeypatch.setattr(fundamental_filter, "INPUT_DIR", tmp_path / "inputs")
    monkeypatch.setattr(fundamental_filter, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(fundamental_filter, "METRICS_PATH", tmp_path / "inputs" / "metrics.csv")
    monkeypatch.setattr(fundamental_filter, "THRESHOLDS_PATH", tmp_path / "inputs" / "fundamental_thresholds.json")

    fundamental_filter.create_fundamental_templates()
    thresholds = json.loads(fundamental_filter.THRESHOLDS_PATH.read_text(encoding="utf-8"))

    assert thresholds["min_roe_pct"] == 10
    assert thresholds["min_roce_pct"] == 12
    assert thresholds["require_positive_operating_cash_flow"] is True
    assert thresholds["max_data_age_days"] == 548
