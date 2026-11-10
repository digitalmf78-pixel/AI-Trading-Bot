"""Config-driven portfolio risk and position sizing controls for NSE V8."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import pandas as pd

CONFIG_PATH = Path("data") / "inputs" / "risk_config.json"
OUTPUT_DIR = Path("outputs")
REQUIRED_KEYS = [
    "account_equity_inr", "risk_per_trade_pct", "max_single_position_pct",
    "max_sector_exposure_pct", "max_total_exposure_pct", "max_stop_distance_pct",
    "current_total_exposure_pct", "sector_exposure_pct_by_sector", "portfolio_exposure_verified",
]
POSITION_LIMIT_KEYS = ["max_open_positions", "current_open_positions"]


def create_risk_config_template(path: str | Path = CONFIG_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        template = {key: None for key in REQUIRED_KEYS + POSITION_LIMIT_KEYS}
        path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")


def load_risk_config(config_path: str | Path = CONFIG_PATH) -> dict:
    """Load local settings, then overlay a private Actions JSON secret if present."""
    path = Path(config_path)
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        config = {}
    if not isinstance(config, dict):
        config = {}
    secret = os.environ.get("RISK_CONFIG_JSON", "").strip()
    if secret:
        try:
            secret_config = json.loads(secret)
        except json.JSONDecodeError:
            return {}
        if not isinstance(secret_config, dict):
            return {}
        config.update(secret_config)
    return config


def _num(value):
    return pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]


def apply_portfolio_risk_controls(frame: pd.DataFrame, config_path: str | Path = CONFIG_PATH) -> pd.DataFrame:
    config_path = Path(config_path)
    config = load_risk_config(config_path)
    missing = [key for key in REQUIRED_KEYS if config.get(key) is None]
    if not isinstance(config.get("sector_exposure_pct_by_sector"), dict):
        if "sector_exposure_pct_by_sector" not in missing:
            missing.append("sector_exposure_pct_by_sector")
    if not isinstance(config.get("portfolio_exposure_verified"), bool):
        if "portfolio_exposure_verified" not in missing:
            missing.append("portfolio_exposure_verified")
    numeric_limits = {
        "account_equity_inr": (0, float("inf")),
        "risk_per_trade_pct": (0, 100),
        "max_single_position_pct": (0, 100),
        "max_sector_exposure_pct": (0, 100),
        "max_total_exposure_pct": (0, 100),
        "max_stop_distance_pct": (0, 100),
        "current_total_exposure_pct": (0, 100),
    }
    for key, (low, high) in numeric_limits.items():
        if key in missing:
            continue
        try:
            number = float(config[key])
            lower_invalid = number < low if key == "current_total_exposure_pct" else number <= low
            if not math.isfinite(number) or lower_invalid or number > high:
                missing.append("INVALID:" + key)
        except (TypeError, ValueError):
            missing.append("INVALID:" + key)
    # Position counts affect concentration limits, so missing values must not
    # silently assume a four-position cap or an empty account.
    max_open_positions = config.get("max_open_positions")
    current_open_positions = config.get("current_open_positions")
    for key in ("max_open_positions", "current_open_positions"):
        if key not in config or config.get(key) is None:
            missing.append(key)
            continue
        if key in missing:
            continue
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            missing.append("INVALID:" + key)
    position_limit_invalid = any(
        key in missing
        for key in (
            "max_open_positions", "current_open_positions",
            "INVALID:max_open_positions", "INVALID:current_open_positions",
        )
    )
    if not position_limit_invalid:
        if max_open_positions <= 0 or current_open_positions > max_open_positions:
            missing.append("INVALID:open_position_limits")
    if isinstance(config.get("sector_exposure_pct_by_sector"), dict):
        for sector, value in config["sector_exposure_pct_by_sector"].items():
            try:
                number = float(value)
                if not math.isfinite(number) or number < 0 or number > 100:
                    missing.append("INVALID:sector_exposure_pct_by_sector." + str(sector))
            except (TypeError, ValueError):
                missing.append("INVALID:sector_exposure_pct_by_sector." + str(sector))
    out = frame.copy()
    risk_output_columns = ["RiskControlStatus", "RiskControlReason", "ProposedPositionQty", "RiskBudgetINR", "ProposedExposurePct", "StopDistancePct"]
    if out.empty:
        for col in risk_output_columns:
            if col not in out.columns:
                out[col] = pd.Series(dtype="object")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out.to_csv(OUTPUT_DIR / "v8_risk_control_report.csv", index=False)
        return out
    statuses, reasons, quantities, risk_budgets, exposures, stop_distances = [], [], [], [], [], []
    for _, row in out.iterrows():
        reason = []
        qty = math.nan; budget = math.nan; exposure = math.nan; stop_pct = math.nan
        if missing:
            reason.append("RISK_CONFIG_MISSING:" + ",".join(missing))
        if not missing and config.get("portfolio_exposure_verified") is not True:
            reason.append("PORTFOLIO_EXPOSURE_NOT_VERIFIED")
        sector = str(row.get("Sector", "")).strip()
        entry = _num(row.get("EntryPricePlan", row.get("EntryZoneHigh")))
        stop = _num(row.get("StopLossPlan"))
        if pd.isna(entry) or pd.isna(stop) or entry <= 0 or stop <= 0 or stop >= entry:
            reason.append("INVALID_ENTRY_OR_STOP")
        if not missing and not (pd.isna(entry) or pd.isna(stop) or entry <= 0 or stop <= 0 or stop >= entry):
            stop_pct = (entry - stop) / entry * 100
            if stop_pct > float(config["max_stop_distance_pct"]):
                reason.append("STOP_DISTANCE_EXCEEDS_LIMIT")
            risk_budget = float(config["account_equity_inr"]) * float(config["risk_per_trade_pct"]) / 100
            budget = risk_budget
            risk_per_share = entry - stop
            qty_by_risk = math.floor(risk_budget / risk_per_share) if risk_per_share > 0 else 0
            qty_by_single_position = math.floor(
                float(config["account_equity_inr"]) * float(config["max_single_position_pct"]) / 100 / entry
            )
            qty = max(0, min(qty_by_risk, qty_by_single_position))
            exposure = qty * entry / float(config["account_equity_inr"]) * 100 if float(config["account_equity_inr"]) > 0 else math.nan
            if qty <= 0:
                reason.append("POSITION_SIZE_ZERO")
            if not sector or sector.casefold() == "unknown":
                # Allow "Unknown" sector only when portfolio is verified empty
                # (no existing positions). Otherwise require explicit sector.
                if not (
                    config.get("portfolio_exposure_verified") is True
                    and config.get("current_total_exposure_pct", 1) == 0
                    and not config.get("sector_exposure_pct_by_sector")
                ):
                    reason.append("SECTOR_REQUIRED_FOR_CONCENTRATION_CHECK")
            else:
                sector_exposure = config["sector_exposure_pct_by_sector"].get(sector)
                # A verified empty portfolio has zero exposure in every sector.
                # Otherwise a missing sector entry must continue to fail closed.
                if (
                    sector_exposure is None
                    and config.get("portfolio_exposure_verified") is True
                    and config.get("current_total_exposure_pct") == 0
                    and not config["sector_exposure_pct_by_sector"]
                ):
                    sector_exposure = 0
                if sector_exposure is None:
                    reason.append("CURRENT_SECTOR_EXPOSURE_MISSING:" + sector)
                elif float(sector_exposure) + exposure > float(config["max_sector_exposure_pct"]):
                    reason.append("SECTOR_CONCENTRATION_LIMIT_EXCEEDED")
            if float(config["current_total_exposure_pct"]) + exposure > float(config["max_total_exposure_pct"]):
                reason.append("TOTAL_EXPOSURE_LIMIT_EXCEEDED")
        if reason:
            status = "WAIT_FOR_DATA" if any(r.startswith(("RISK_CONFIG_MISSING", "PORTFOLIO_EXPOSURE_NOT_VERIFIED", "INVALID_ENTRY_OR_STOP", "SECTOR_REQUIRED", "CURRENT_SECTOR_EXPOSURE_MISSING")) for r in reason) else "REJECT"
        else:
            status = "PASS"
        statuses.append(status); reasons.append(";".join(reason) if reason else "RISK_LIMITS_PASSED")
        quantities.append(qty); risk_budgets.append(budget); exposures.append(exposure); stop_distances.append(stop_pct)
    out["RiskControlStatus"] = statuses
    out["RiskControlReason"] = reasons
    out["ProposedPositionQty"] = quantities
    out["RiskBudgetINR"] = risk_budgets
    out["ProposedExposurePct"] = exposures
    out["StopDistancePct"] = stop_distances
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_DIR / "v8_risk_control_report.csv", index=False)
    return out

