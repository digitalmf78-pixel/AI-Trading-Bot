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
    "NSE Official Shareholding XBRL": "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern/",
    "Moneycontrol": "https://www.moneycontrol.com/",
    "Tickertape": "https://www.tickertape.in/",
}
NSE_SHAREHOLDING_METRICS = {
    "PromoterHoldingPct", "FIIHoldingPct", "DIIHoldingPct", "PublicHoldingPct", "PledgePct",
}

ALIASES = {
    "RevenueGrowthPct": ("revenue growth", "sales growth", "revenue growth %", "sales growth %"),
    "ProfitGrowthPct": ("net profit growth", "profit growth", "profit growth %", "pat growth"),
    "ROEPercent": ("return on equity", "roe", "roe %", "return on net worth", "return on networth / equity"),
    "ROCEPercent": ("return on capital employed", "roce", "roce %"),
    "DebtToEquity": ("debt equity", "debt to equity", "debt/equity", "debt equity ratio", "debt to equity (x)"),
    "InterestCoverage": ("interest coverage", "interest coverage ratio", "interest coverage ratios (x)"),
    "GrossMarginPct": ("gross margin", "gross margin %", "gross profit margin"),
    "OperatingMarginPct": ("operating margin", "operating margin %", "ebit margin"),
    "NetProfitMarginPct": ("net profit margin", "net margin", "net profit margin %"),
    "CurrentRatio": ("current ratio", "current ratio (x)"),
    "QuickRatio": ("quick ratio", "acid test ratio", "quick ratio (x)"),
    "AssetTurnover": ("asset turnover", "asset turnover ratio", "asset turnover ratio (%)"),
    "EPS": ("eps", "earnings per share", "basic eps", "basic eps (rs.)"),
    "BookValuePerShare": ("book value per share", "book value", "book value [excl. reval reserve]/share (rs.)"),
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
            response = original_get(url, *args, **kwargs)
            try:
                client._free_source_last_http = {
                    "status_code": getattr(response, "status_code", None),
                    "content_type": getattr(response, "headers", {}).get("Content-Type", ""),
                    "url": str(getattr(response, "url", ""))[:300],
                    "content_length": len(getattr(response, "content", b"") or b""),
                }
            except Exception:
                pass
            return response

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
    """Parse a single displayed scalar without silently accepting ranges/text."""
    if value is None:
        return None
    try:
        text = str(value).strip()
        if text.lower() in {"", "-", "--", "nan", "none", "na", "n/a", "nm"}:
            return None
        negative_parentheses = text.startswith("(") and text.endswith(")")
        if negative_parentheses:
            text = text[1:-1].strip()
        text = text.replace(",", "").replace("%", "")
        text = re.sub(r"(?i)(₹|rs\.?|inr|crores?|cr\.?|lakhs?|lacs?)", "", text)
        text = re.sub(r"(?i)\s*x$", "", text).strip()
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
            return None
        result = float(text)
        if negative_parentheses:
            result = -result
        return result if pd.notna(result) else None
    except (TypeError, ValueError):
        return None


def _label_column(frame: pd.DataFrame):
    accepted = {
        "name", "ratio", "ratios", "metric", "particular", "particulars",
        "parameter", "key", "headers", "headings", "quarterly", "annual",
        "unnamed0",
    }
    return next((col for col in frame.columns if _norm(col) in accepted),
                frame.columns[0] if len(frame.columns) else None)


def _extract_ratio_observation(frame: pd.DataFrame, aliases: tuple[str, ...]):
    """Return the first available exact-label value and its source period column."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None, ""
    wanted = {_norm(x) for x in aliases}
    for idx in frame.index:
        if _norm(idx) in wanted:
            row = frame.loc[idx]
            if isinstance(row, pd.DataFrame):
                return None, ""
            for column, value in row.items():
                number = _number(value)
                if number is not None:
                    return number, str(column)
    label_col = _label_column(frame)
    if label_col is not None:
        for _, row in frame.iterrows():
            if _norm(row.get(label_col)) not in wanted:
                continue
            for column in frame.columns:
                if column == label_col:
                    continue
                number = _number(row.get(column))
                if number is not None:
                    return number, str(column)
    for column in frame.columns:
        if _norm(column) in wanted:
            for value in frame[column].tolist():
                number = _number(value)
                if number is not None:
                    return number, str(column)
    return None, ""


def _extract_ratio(frame: pd.DataFrame, aliases: tuple[str, ...]):
    """Compatibility wrapper returning only the numeric ratio."""
    value, _period = _extract_ratio_observation(frame, aliases)
    return value


def _extract_annual_growth(frame: pd.DataFrame, aliases: tuple[str, ...]):
    """Calculate YoY growth only from two consecutive, positive-base annual columns."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None, ""
    wanted = {_norm(x) for x in aliases}
    label_col = _label_column(frame)
    if label_col is None:
        return None, ""
    matching = frame[frame[label_col].map(_norm).isin(wanted)]
    if len(matching) != 1:
        return None, ""
    row = matching.iloc[0]
    year_values = {}
    for column in frame.columns:
        if column == label_col:
            continue
        match = re.fullmatch(r"(?:fy)?(20\d{2})", _norm(column))
        if not match:
            continue
        year = int(match.group(1))
        number = _number(row.get(column))
        if number is not None:
            year_values[year] = number
    if not year_values:
        return None, ""
    current_year = max(year_values)
    previous_year = current_year - 1
    current_value = year_values.get(current_year)
    previous_value = year_values.get(previous_year)
    if current_value is None or previous_value is None or previous_value <= 0:
        return None, ""
    growth = (current_value - previous_value) / previous_value * 100.0
    return growth, f"FY{previous_year}->FY{current_year}"


def _extract_holding(frame: pd.DataFrame, aliases: tuple[str, ...]):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    wanted = {_norm(x) for x in aliases}
    name_cols = [c for c in frame.columns if _norm(c) in {"category", "name", "holder", "investortype", "type", "shareholder", "headers", "headings"}]
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
    """Query all enabled no-key sources; official NSE XBRL has first priority.

    source_factories is injectable for offline tests:
      {"nse_shareholding": callable(symbol) returning an NSE shareholding result,
       "moneycontrol": callable returning a MoneyControl-like object,
       "tickertape": callable returning a Tickertape-like object}
    When source_factories is supplied, the official NSE source is skipped unless
    explicitly injected, so unit tests never perform unexpected network calls.
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

    # Official NSE quarterly SHP XBRL is the authoritative no-key source for
    # promoter/FII/DII/public ownership. It is tried before third-party pages;
    # any later provider values are retained as metric-level alternates.
    shareholding_requested = wanted & NSE_SHAREHOLDING_METRICS
    if shareholding_requested:
        try:
            if "nse_shareholding" in factories:
                official_result = factories["nse_shareholding"](symbol)
            elif source_factories is not None:
                official_result = {
                    "metrics": {},
                    "provider": {
                        "status": "NOT_INJECTED_TEST_SOURCE",
                        "reason": "Offline source-factory test did not inject NSE shareholding",
                        "source_url": SOURCE_URLS["NSE Official Shareholding XBRL"],
                    },
                }
            else:
                from nse_shareholding import fetch_nse_shareholding_metrics
                official_result = fetch_nse_shareholding_metrics(symbol)

            official_metrics = official_result.get("metrics", {})
            official_provider = dict(official_result.get("provider", {}))
            official_provider.setdefault("source_url", SOURCE_URLS["NSE Official Shareholding XBRL"])
            official_provider.setdefault("status", "EMPTY")
            result["providers"]["NSE Official Shareholding XBRL"] = official_provider
            for metric, value in official_metrics.items():
                if metric not in shareholding_requested or _number(value) is None:
                    continue
                if metric in result["metrics"]:
                    result["metric_alternates"].setdefault(metric, []).append({
                        "source": "NSE Official Shareholding XBRL",
                        "value": value,
                        "period": official_result.get("metric_periods", {}).get(metric, ""),
                        "source_url": official_result.get("metric_urls", {}).get(metric, ""),
                    })
                    continue
                result["metrics"][metric] = float(value)
                result["metric_sources"][metric] = "NSE Official Shareholding XBRL"
                result["metric_urls"][metric] = official_result.get("metric_urls", {}).get(
                    metric, official_provider.get("source_url", SOURCE_URLS["NSE Official Shareholding XBRL"])
                )
                result["metric_periods"][metric] = official_result.get("metric_periods", {}).get(metric, "")
                result["metric_currencies"][metric] = ""
        except Exception as exc:
            result["providers"]["NSE Official Shareholding XBRL"] = {
                "status": "PROVIDER_ERROR",
                "reason": f"{type(exc).__name__}: {str(exc)[:300]}",
                "source_url": SOURCE_URLS["NSE Official Shareholding XBRL"],
            }

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
            if hasattr(getattr(client, "session", None), "headers"):
                client.session.headers.update({"Referer": SOURCE_URLS[source] + "/"})
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
                def _tickertape_search(hint):
                    response = client.hit_and_get_data(
                        f"{client._base_url}/search",
                        params={"text": hint, "types": "stock", "pageNumber": 0},
                    )
                    data = response.get("data", {}) if isinstance(response, dict) else {}
                    items = data.get("items", []) if isinstance(data, dict) else []
                    schema = {
                        "response_keys": list(response.keys()) if isinstance(response, dict) else [],
                        "data_type": type(data).__name__,
                        "data_keys": list(data.keys()) if isinstance(data, dict) else [],
                        "items_type": type(items).__name__,
                        "items_count": len(items) if isinstance(items, list) else 0,
                        "message": str(response.get("message", ""))[:240] if isinstance(response, dict) else "",
                    }
                    return (items if isinstance(items, list) else []), schema

                raw_hits, search_schema = _tickertape_search(str(company_name or symbol).strip())
                matching_hits = [item for item in raw_hits if str(item.get("ticker", "")).strip().upper() == symbol]
                if not matching_hits and company_name:
                    raw_hits, search_schema = _tickertape_search(symbol)
                    matching_hits = [item for item in raw_hits if str(item.get("ticker", "")).strip().upper() == symbol]
                if not matching_hits:
                    result["providers"][source] = {
                        "status": "IDENTITY_UNVERIFIED" if raw_hits else "NO_SEARCH_RESULTS",
                        "reason": "Tickertape did not return an exact NSE ticker symbol for the supplied company/symbol query",
                        "search_response_schema": search_schema,
                        "source_url": SOURCE_URLS[source],
                    }
                    continue
                hit = matching_hits[0]
                sid = str(hit.get("sid", "") or "").strip()
                if not sid:
                    result["providers"][source] = {
                        "status": "IDENTITY_UNVERIFIED",
                        "reason": "Tickertape exact symbol result had no SID",
                        "source_url": SOURCE_URLS[source],
                    }
                    continue
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
            table_schema = {}
            for name, frame in frames.items():
                if frame.empty:
                    continue
                label_columns = [col for col in frame.columns if _norm(col) in {
                    "name", "ratio", "ratios", "metric", "particular", "particulars",
                    "parameter", "key", "headers", "headings", "unnamed0",
                }]
                label_col = label_columns[0] if label_columns else (frame.columns[0] if len(frame.columns) else None)
                label_preview = (
                    [str(value) for value in frame[label_col].head(20).tolist()]
                    if label_col is not None else []
                )
                table_schema[name] = {
                    "columns": [str(col) for col in frame.columns[:20]],
                    "index_preview": [str(idx) for idx in frame.index[:15]],
                    "label_preview": label_preview,
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
                observation_period = ""
                if source == "Moneycontrol" and metric in {"RevenueGrowthPct", "ProfitGrowthPct"}:
                    growth_aliases = ("revenue", "sales") if metric == "RevenueGrowthPct" else ("net profit", "profit after tax")
                    value, observation_period = _extract_annual_growth(
                        frames.get("overview", pd.DataFrame()), growth_aliases,
                    )
                for frame in candidate_frames:
                    if value is not None:
                        break
                    if metric in {"PromoterHoldingPct", "FIIHoldingPct", "DIIHoldingPct", "PublicHoldingPct", "PledgePct"}:
                        value = _extract_holding(frame, ALIASES[metric])
                        observation_period = ""
                    else:
                        value, observation_period = _extract_ratio_observation(frame, ALIASES[metric])
                if value is None:
                    continue
                if metric in result["metrics"]:
                    result["metric_alternates"].setdefault(metric, []).append({
                        "source": source, "value": value, "period": observation_period,
                        "source_url": SOURCE_URLS[source],
                    })
                    continue
                result["metrics"][metric] = value
                result["metric_sources"][metric] = source
                result["metric_urls"][metric] = SOURCE_URLS[source]
                result["metric_periods"][metric] = observation_period
                result["metric_currencies"][metric] = ""
        except Exception as exc:
            result["providers"][source] = {
                "status": "PROVIDER_ERROR",
                "reason": f"{type(exc).__name__}: {str(exc)[:300]}",
                "source_url": SOURCE_URLS[source],
            }
    return result
