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
    "GrossMarginPct": ("gross margin", "gross margin %"),
    "OperatingMarginPct": ("operating margin", "operating margin %", "ebit margin"),
    "NetProfitMarginPct": ("net profit margin", "net margin", "net profit margin %"),
    "CurrentRatio": ("current ratio",),
    "QuickRatio": ("quick ratio", "acid test ratio"),
    "AssetTurnover": ("asset turnover", "asset turnover ratio"),
    "EPS": ("eps", "earnings per share", "basic eps"),
    "BookValuePerShare": ("book value per share", "book value"),
    "PromoterHoldingPct": ("promoter", "promoter holding", "promoters"),
    "FIIHoldingPct": ("fii", "fii holding", "foreign institutional investors"),
    "DIIHoldingPct": ("dii", "dii holding", "domestic institutional investors"),
    "PublicHoldingPct": ("public", "public holding"),
    "PledgePct": ("pledged", "promoter pledge", "pledge"),
}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())



def _configure_bounded_session(client):
    """Bound each third-party request and disable aggressive upstream retries."""
    session = getattr(client, "session", None)
    if session is None:
        return
    try:
        from requests.adapters import HTTPAdapter
        session.mount("https://", HTTPAdapter(max_retries=0))
        session.mount("http://", HTTPAdapter(max_retries=0))
        original_get = session.get

        def bounded_get(url, *args, **kwargs):
            kwargs.setdefault("timeout", (4, 8))
            return original_get(url, *args, **kwargs)

        session.get = bounded_get
    except Exception:
        # Keep source-specific failures isolated; the caller records diagnostics.
        return


def _instantiate_bounded_client(factory):
    """Apply timeout/no-retry policy even to requests made inside __init__."""
    from requests import Session
    from requests.adapters import HTTPAdapter

    original_get = Session.get
    original_adapter_init = HTTPAdapter.__init__

    def bounded_get(session, url, *args, **kwargs):
        kwargs.setdefault("timeout", (4, 8))
        return original_get(session, url, *args, **kwargs)

    def no_retry_adapter_init(adapter, *args, **kwargs):
        args = list(args)
        if len(args) >= 3:
            args[2] = 0
            kwargs.pop("max_retries", None)
        else:
            kwargs["max_retries"] = 0
        return original_adapter_init(adapter, *args, **kwargs)

    Session.get = bounded_get
    HTTPAdapter.__init__ = no_retry_adapter_init
    try:
        client = factory()
    finally:
        Session.get = original_get
        HTTPAdapter.__init__ = original_adapter_init
    _configure_bounded_session(client)
    return client


def _identity_matches(symbol: str, company_name: str | None, raw: Any) -> bool:
    """Fail closed unless the search result identifies this exact NSE symbol/company."""
    items = raw if isinstance(raw, list) else [raw]
    expected_name = _norm(company_name or "")
    expected_name = expected_name.replace("limited", "").replace("ltd", "")
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("ticker", "symbol", "nse_code", "nse_symbol", "nseCode", "symbol_code"):
            if str(item.get(key, "")).strip().upper() == symbol:
                return True
        if expected_name:
            for key in ("stock_name", "company_name", "company", "name", "security_name"):
                observed = _norm(item.get(key, ""))
                observed = observed.replace("limited", "").replace("ltd", "")
                if observed and (observed == expected_name or observed in expected_name or expected_name in observed):
                    return True
    return False


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



def _extract_holding(frame: pd.DataFrame, aliases: tuple[str, ...]):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    wanted = {_norm(x) for x in aliases}
    name_cols = [c for c in frame.columns if _norm(c) in {"category", "name", "holder", "investortype", "type", "shareholder"}]
    value_cols = [c for c in frame.columns if _norm(c) in {"percentage", "holding", "value", "shareholding", "percent", "holdingpercentage"}]
    for name_col in name_cols:
        for _, row in frame.iterrows():
            if _norm(row.get(name_col)) in wanted:
                for value_col in value_cols:
                    value = _number(row.get(value_col))
                    if value is not None:
                        return value
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
    company_name: str | None = None,
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
        "metric_alternates": {}, "providers": {}, "attempted_at_utc": datetime.now(timezone.utc).isoformat(),
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
            client = _instantiate_bounded_client(factory)
            if source == "Moneycontrol":
                lookup_term = str(company_name or symbol).strip()
                ticker_id, raw_hits = client.get_ticker(lookup_term)
                if not ticker_id:
                    raise RuntimeError("symbol lookup returned no Moneycontrol ticker")
                if not _identity_matches(symbol, company_name, raw_hits):
                    result["providers"][source] = {
                        "status": "IDENTITY_UNVERIFIED",
                        "reason": "Moneycontrol search result could not be matched to the NSE symbol/company name",
                        "source_url": SOURCE_URLS[source],
                    }
                    continue
                calls = [
                    ("ratios", lambda: client.get_ratios_mini_statement(ticker_id, statement_type="consolidated")),
                    ("overview", lambda: client.get_overview_mini_statement(ticker_id, statement_type="consolidated", statement_frequency=12)),
                    ("income", lambda: client.get_income_mini_statement(ticker_id, statement_type="consolidated", statement_frequency=3)),
                    ("income_annual", lambda: client.get_income_mini_statement(ticker_id, statement_type="consolidated", statement_frequency=12)),
                    ("balance_sheet", lambda: client.get_balance_sheet_mini_statement(ticker_id, statement_type="consolidated")),
                    ("cash_flow", lambda: client.get_cash_flow_mini_statement(ticker_id, statement_type="consolidated")),
                ]
            else:
                sid, raw_hits = client.get_ticker(symbol, search_place="stock")
                if not sid:
                    raise RuntimeError("symbol lookup returned no Tickertape SID")
                matching_hits = [item for item in raw_hits if str(item.get("ticker", "")).strip().upper() == symbol]
                if not matching_hits:
                    result["providers"][source] = {
                        "status": "IDENTITY_UNVERIFIED",
                        "reason": "Tickertape search result did not return an exact NSE ticker symbol",
                        "source_url": SOURCE_URLS[source],
                    }
                    continue
                hit = matching_hits[0]
                sid = str(hit.get("sid", "") or sid)
                slug = str(hit.get("slug", "") or "").strip()
                calls = [
                    ("ratios", lambda: client.get_key_ratios(slug)) if slug else ("ratios", lambda: pd.DataFrame()),
                    ("scorecard", lambda: client.get_score_card(sid)),
                    ("income", lambda: client.get_income_data(sid, time_horizon="interim", num_time_periods=12, view_type="normal")),
                    ("income_growth", lambda: client.get_income_data(sid, time_horizon="interim", num_time_periods=12, view_type="growth")),
                    ("income_annual", lambda: client.get_income_data(sid, time_horizon="annual", num_time_periods=10, view_type="normal")),
                    ("income_annual_growth", lambda: client.get_income_data(sid, time_horizon="annual", num_time_periods=10, view_type="growth")),
                    ("balance_sheet", lambda: client.get_balance_sheet_data(sid, num_time_periods=10)),
                    ("cash_flow", lambda: client.get_cash_flow_data(sid, num_time_periods=10)),
                    ("shareholding", lambda: client.get_share_holding_pattern(slug)) if slug else ("shareholding", lambda: pd.DataFrame()),
                ]
            for name, call in calls:
                try:
                    frames[name] = _safe_frame(call())
                except Exception as exc:
                    errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:160]}")
                if pause_seconds:
                    time.sleep(max(0.0, float(pause_seconds)))
            row_counts = {name: int(len(frame)) for name, frame in frames.items() if not frame.empty}
            table_schema = {
                name: {
                    "columns": [str(col) for col in frame.columns[:20]],
                    "index_preview": [str(idx) for idx in frame.index[:15]],
                }
                for name, frame in frames.items() if not frame.empty
            }
            result["providers"][source] = {
                "status": "DATA_FOUND" if row_counts else "EMPTY",
                "rows": row_counts,
                "table_schema": table_schema,
                "errors": errors,
                "source_url": SOURCE_URLS[source],
            }
            for metric in wanted:
                candidate_frames = [
                    frames.get("ratios", pd.DataFrame()),
                    frames.get("overview", pd.DataFrame()),
                    frames.get("scorecard", pd.DataFrame()),
                    frames.get("income", pd.DataFrame()),
                    frames.get("income_annual", pd.DataFrame()),
                    frames.get("balance_sheet", pd.DataFrame()),
                    frames.get("cash_flow", pd.DataFrame()),
                ]
                if metric in {"RevenueGrowthPct", "ProfitGrowthPct"}:
                    candidate_frames.insert(0, frames.get("income_growth", pd.DataFrame()))
                    candidate_frames.insert(1, frames.get("income_annual_growth", pd.DataFrame()))
                if metric in {"PromoterHoldingPct", "FIIHoldingPct", "DIIHoldingPct", "PublicHoldingPct", "PledgePct"}:
                    candidate_frames.insert(0, frames.get("shareholding", pd.DataFrame()))
                value = None
                for frame in candidate_frames:
                    if metric in {"PromoterHoldingPct", "FIIHoldingPct", "DIIHoldingPct", "PublicHoldingPct", "PledgePct"}:
                        value = _extract_holding(frame, ALIASES[metric])
                    else:
                        value = _extract_ratio(frame, ALIASES[metric])
                    if value is not None:
                        break
                if value is None:
                    continue
                if metric in result["metrics"]:
                    result["metric_alternates"].setdefault(metric, []).append({
                        "source": source, "value": value, "source_url": SOURCE_URLS[source],
                    })
                    continue
                result["metrics"][metric] = value
                result["metric_sources"][metric] = source
                result["metric_urls"][metric] = SOURCE_URLS[source]
                result["metric_periods"][metric] = ""
                result["metric_currencies"][metric] = ""
        except Exception as exc:
            result["providers"][source] = {
                "status": "PROVIDER_ERROR",
                "reason": f"{type(exc).__name__}: {str(exc)[:300]}",
                "source_url": SOURCE_URLS[source],
            }
    return result
