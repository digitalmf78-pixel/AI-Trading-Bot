"""Best-effort, no-key Indian fundamentals fallback.

Uses the Apache-2.0 Bharat-sm-data client for public Moneycontrol and Tickertape
pages. The upstream sites do not provide these as supported public APIs; this
adapter is read-only, rate-limited, non-gating, and records provenance. It only
returns narrowly mapped ratios/growth values; raw provider tables are not
published or committed by this module.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd

SOURCE_URLS = {
    "Moneycontrol": "https://www.moneycontrol.com/",
    "Tickertape": "https://www.tickertape.in/",
}

ALIASES = {
    "RevenueGrowthPct": ("revenue growth", "sales growth", "revenue growth %", "sales growth %"),
    "ProfitGrowthPct": ("net profit growth", "profit growth", "profit growth %", "pat growth"),
    "ROEPercent": ("return on equity", "roe", "roe %", "return on net worth"),
    "ROCEPercent": ("return on capital employed", "roce", "roce %"),
    "DebtToEquity": ("debt equity", "debt to equity", "debt/equity", "debt equity ratio"),
    "InterestCoverage": ("interest coverage", "interest coverage ratio"),
}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _number(value: Any):
    if value is None:
        return None
    try:
        text = str(value).strip().replace(",", "").replace("%", "")
        if text in {"", "-", "--", "nan", "None", "NA", "N/A"}:
            return None
        result = float(text)
        return result if pd.notna(result) else None
    except (TypeError, ValueError):
        return None


def _extract_ratio(frame: pd.DataFrame, aliases: tuple[str, ...]):
    """Extract only an exact normalized row/column label; no fuzzy guessing."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    wanted = {_norm(x) for x in aliases}
    # Common wide layout: metric labels in index, periods in columns.
    for idx in frame.index:
        if _norm(idx) in wanted:
            row = frame.loc[idx]
            values = row.tolist() if isinstance(row, pd.Series) else [row]
            for value in values:
                number = _number(value)
                if number is not None:
                    return number
    # Common long layout: metric labels in a name/ratio/metric column.
    for name_col in ("name", "ratio", "metric", "particulars", "parameter", "key"):
        matches = [c for c in frame.columns if _norm(c) == _norm(name_col)]
        if not matches:
            continue
        name = matches[0]
        for _, row in frame.iterrows():
            if _norm(row.get(name)) in wanted:
                for col in frame.columns:
                    if col == name:
                        continue
                    number = _number(row.get(col))
                    if number is not None:
                        return number
    # Some sources expose one metric per column.
    for col in frame.columns:
        if _norm(col) in wanted:
            for value in frame[col].tolist():
                number = _number(value)
                if number is not None:
                    return number
    return None


def _safe_frame(value):
    if isinstance(value, pd.DataFrame):
        return value
    if isinstance(value, pd.Series):
        return value.to_frame()
    if isinstance(value, dict):
        return pd.json_normalize(value)
    if isinstance(value, list):
        return pd.DataFrame(value)
    return pd.DataFrame()


def fetch_free_fundamental_sources(
    symbol: str,
    *,
    missing_metrics=None,
    pause_seconds: float = 0.5,
    source_factories=None,
) -> dict:
    """Query every installed no-key source; never stop after the first success.

    source_factories is injectable for offline tests:
      {"moneycontrol": callable returning a MoneyControl-like object,
       "tickertape": callable returning a Tickertape-like object}
    """
    symbol = str(symbol).strip().upper()
    wanted = set(missing_metrics or ALIASES)
    wanted &= set(ALIASES)
    result = {
        "symbol": symbol, "metrics": {}, "metric_sources": {},
        "metric_urls": {}, "metric_periods": {}, "metric_currencies": {},
        "providers": {}, "attempted_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    factories = source_factories or {}
    clients = []
    if "moneycontrol" in factories:
        clients.append(("Moneycontrol", factories["moneycontrol"]))
    else:
        try:
            from Fundamentals import MoneyControl
            clients.append(("Moneycontrol", MoneyControl))
        except Exception as exc:
            result["providers"]["Moneycontrol"] = {"status": "NOT_INSTALLED", "reason": str(exc)[:200]}
    if "tickertape" in factories:
        clients.append(("Tickertape", factories["tickertape"]))
    else:
        try:
            from Fundamentals import Tickertape
            clients.append(("Tickertape", Tickertape))
        except Exception as exc:
            result["providers"]["Tickertape"] = {"status": "NOT_INSTALLED", "reason": str(exc)[:200]}

    for source, factory in clients:
        frames = {}
        errors = []
        try:
            client = factory()
            if source == "Moneycontrol":
                ticker_id, raw_hits = client.get_ticker(symbol)
                if not ticker_id:
                    raise RuntimeError("symbol lookup returned no Moneycontrol ticker")
                calls = [
                    ("ratios", lambda: client.get_ratios_mini_statement(ticker_id, statement_type="consolidated")),
                    ("income", lambda: client.get_income_mini_statement(ticker_id, statement_type="consolidated", statement_frequency=3)),
                    ("balance_sheet", lambda: client.get_balance_sheet_mini_statement(ticker_id, statement_type="consolidated")),
                    ("cash_flow", lambda: client.get_cash_flow_mini_statement(ticker_id, statement_type="consolidated")),
                ]
            else:
                sid, raw_hits = client.get_ticker(symbol)
                if not sid:
                    raise RuntimeError("symbol lookup returned no Tickertape SID")
                calls = [
                    ("ratios", lambda: client.get_score_card(sid)),
                    ("income", lambda: client.get_income_data(sid, time_horizon="interim", num_time_periods=12, view_type="normal")),
                    ("income_growth", lambda: client.get_income_data(sid, time_horizon="interim", num_time_periods=12, view_type="growth")),
                    ("balance_sheet", lambda: client.get_balance_sheet_data(sid, num_time_periods=10)),
                    ("cash_flow", lambda: client.get_cash_flow_data(sid, num_time_periods=10)),
                    ("shareholding", lambda: client.get_share_holding_pattern(sid)),
                ]
            for name, call in calls:
                try:
                    frames[name] = _safe_frame(call())
                except Exception as exc:
                    errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:160]}")
                if pause_seconds:
                    time.sleep(max(0.0, float(pause_seconds)))
            row_counts = {name: int(len(frame)) for name, frame in frames.items() if not frame.empty}
            result["providers"][source] = {
                "status": "DATA_FOUND" if row_counts else "EMPTY",
                "rows": row_counts,
                "errors": errors,
                "source_url": SOURCE_URLS[source],
            }
            for metric in wanted:
                # Prefer the ratios/scorecard table, then the explicit growth table.
                candidate_frames = [frames.get("ratios", pd.DataFrame())]
                if metric in {"RevenueGrowthPct", "ProfitGrowthPct"}:
                    candidate_frames.insert(0, frames.get("income_growth", pd.DataFrame()))
                for frame in candidate_frames:
                    value = _extract_ratio(frame, ALIASES[metric])
                    if value is None:
                        continue
                    if metric in result["metrics"]:
                        # Keep the first source's value; retain the other source in diagnostics.
                        break
                    result["metrics"][metric] = value
                    result["metric_sources"][metric] = source
                    result["metric_urls"][metric] = SOURCE_URLS[source]
                    result["metric_periods"][metric] = ""
                    result["metric_currencies"][metric] = ""
                    break
        except Exception as exc:
            result["providers"][source] = {
                "status": "PROVIDER_ERROR",
                "reason": f"{type(exc).__name__}: {str(exc)[:300]}",
                "source_url": SOURCE_URLS[source],
            }
    return result
