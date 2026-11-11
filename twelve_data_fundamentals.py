"""Optional Twelve Data fallback for NSE Mainboard fundamental enrichment.

This adapter is secondary-provider data only. It never changes NSE universe,
price/volume/Delivery selection, and never labels provider values as official
filing verified. It accepts only NSE/XNSE instrument metadata and records
currency/period provenance. Absolute INR cash-flow fields are populated only
when Twelve Data reports INR.
"""
from __future__ import annotations

from datetime import date
from typing import Any
import math
import re

import requests

BASE_URL = "https://api.twelvedata.com"
SOURCE_NAME = "Twelve Data"
SOURCE_URL = "https://twelvedata.com/exchanges/XNSE?group=fundamentals"


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if not value or value.lower() in {"none", "nan", "null", "—", "-"}:
                return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _find_number(data: Any, aliases: set[str]) -> float | None:
    """Find a numeric field by normalized key, recursively, without guessing."""
    if isinstance(data, dict):
        for key, value in data.items():
            if _norm(key) in aliases:
                found = _number(value)
                if found is not None:
                    return found
        for value in data.values():
            found = _find_number(value, aliases)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find_number(value, aliases)
            if found is not None:
                return found
    return None


def _quarter_key(value: Any):
    stamp = __import__("pandas").to_datetime(value, errors="coerce")
    if __import__("pandas").isna(stamp):
        return None
    return stamp.to_period("Q-DEC")


def _consecutive(rows: list[dict], count: int) -> bool:
    import pandas as pd
    if len(rows) < count:
        return False
    dates = [pd.to_datetime(row.get("fiscal_date"), errors="coerce") for row in rows[:count]]
    if any(pd.isna(value) for value in dates):
        return False
    keys = [value.to_period("Q-DEC").ordinal for value in dates]
    return len(set(keys)) == count and all(keys[i] - keys[i + 1] == 1 for i in range(len(keys) - 1))


def _rows(payload: dict, key: str) -> list[dict]:
    values = payload.get(key, [])
    return [row for row in values if isinstance(row, dict)] if isinstance(values, list) else []


def _get_endpoint(session, endpoint: str, symbol: str, api_key: str, outputsize: int) -> dict:
    response = session.get(
        f"{BASE_URL}/{endpoint}",
        params={
            "symbol": symbol,
            "exchange": "NSE",
            "mic_code": "XNSE",
            "period": "quarterly",
            "outputsize": outputsize,
            "apikey": api_key,
        },
        timeout=(5, 20),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"{endpoint}: response is not a JSON object")
    if payload.get("status") == "error" or payload.get("code") or payload.get("message") and not payload.get("meta"):
        raise RuntimeError(f"{endpoint}: {str(payload.get('message') or payload.get('code') or 'provider error')[:240]}")
    meta = payload.get("meta") or {}
    exchange = str(meta.get("exchange") or "").strip().upper()
    mic_code = str(meta.get("mic_code") or meta.get("micCode") or "").strip().upper()
    if exchange not in {"NSE", "NATIONAL STOCK EXCHANGE OF INDIA"} and mic_code != "XNSE":
        raise ValueError(f"{endpoint}: provider instrument is not confirmed as NSE (exchange={exchange!r}, mic={mic_code!r})")
    return payload


def fetch_twelve_data_fundamentals(
    symbol: str,
    api_key: str,
    *,
    session=None,
    asof_date=None,
) -> dict:
    """Fetch quarterly NSE statements and calculate conservative TTM metrics.

    Returns an empty metrics mapping on no-data only by raising a descriptive
    exception; callers record the failure and retain the existing cache.
    """
    if not str(api_key or "").strip():
        raise ValueError("TWELVE_DATA_API_KEY is not configured")
    client = session or requests.Session()
    symbol = str(symbol).strip().upper()
    cutoff = __import__("pandas").to_datetime(asof_date, errors="coerce") if asof_date else None
    income_payload = _get_endpoint(client, "income_statement", symbol, api_key, 8)
    balance_payload = _get_endpoint(client, "balance_sheet", symbol, api_key, 5)
    cash_payload = _get_endpoint(client, "cash_flow", symbol, api_key, 4)

    meta = income_payload.get("meta") or {}
    currency = str(meta.get("currency") or "").strip().upper()
    income = sorted(_rows(income_payload, "income_statement"), key=lambda row: str(row.get("fiscal_date") or ""), reverse=True)
    balance = sorted(_rows(balance_payload, "balance_sheet"), key=lambda row: str(row.get("fiscal_date") or ""), reverse=True)
    cash = sorted(_rows(cash_payload, "cash_flow"), key=lambda row: str(row.get("fiscal_date") or ""), reverse=True)

    if cutoff is not None and not __import__("pandas").isna(cutoff):
        cutoff_date = cutoff.date()
        income = [row for row in income if (lambda d: d is not None and d.date() <= cutoff_date)(__import__("pandas").to_datetime(row.get("fiscal_date"), errors="coerce"))]
        balance = [row for row in balance if (lambda d: d is not None and d.date() <= cutoff_date)(__import__("pandas").to_datetime(row.get("fiscal_date"), errors="coerce"))]
        cash = [row for row in cash if (lambda d: d is not None and d.date() <= cutoff_date)(__import__("pandas").to_datetime(row.get("fiscal_date"), errors="coerce"))]

    if not income:
        raise ValueError("Twelve Data returned no income statement periods")
    latest_period = str(income[0].get("fiscal_date") or "")
    metrics: dict[str, float] = {}
    metric_periods: dict[str, str] = {}
    metric_currencies: dict[str, str] = {}

    def put(name: str, value: float | None, period: str = latest_period, *, currency_code: str = currency):
        if value is not None and math.isfinite(value):
            metrics[name] = float(value)
            metric_periods[name] = period
            metric_currencies[name] = currency_code

    def value(row: dict, aliases: set[str]) -> float | None:
        return _find_number(row, aliases)

    revenue_aliases = {"sales", "totalrevenue", "revenue", "operatingrevenue"}
    profit_aliases = {"netincome", "netincometocommon", "netincomecontinuousoperations"}
    ebit_aliases = {"ebit", "operatingincome"}
    interest_aliases = {"interestexpense", "nonoperatinginterestexpense"}
    balance_currency = str((balance_payload.get("meta") or {}).get("currency") or "").strip().upper()
    cash_currency = str((cash_payload.get("meta") or {}).get("currency") or "").strip().upper()
    if any(code and currency and code != currency for code in (balance_currency, cash_currency)):
        raise ValueError(f"statement currencies do not match: income={currency}, balance={balance_currency}, cash={cash_currency}")

    if _consecutive(income, 8):
        latest4, prior4 = income[:4], income[4:8]
        rev_now = [value(row, revenue_aliases) for row in latest4]
        rev_prior = [value(row, revenue_aliases) for row in prior4]
        profit_now = [value(row, profit_aliases) for row in latest4]
        profit_prior = [value(row, profit_aliases) for row in prior4]
        if all(v is not None for v in rev_now + rev_prior):
            denominator = sum(rev_prior)
            if denominator > 0:
                put("RevenueGrowthPct", (sum(rev_now) - denominator) / denominator * 100.0)
        if all(v is not None for v in profit_now + profit_prior):
            denominator = sum(profit_prior)
            if denominator > 0:
                put("ProfitGrowthPct", (sum(profit_now) - denominator) / denominator * 100.0)

    ttm_income = income[:4] if _consecutive(income, 4) else []
    ttm_ebit = [value(row, ebit_aliases) for row in ttm_income]
    def interest_expense(row: dict) -> float | None:
        direct = value(row, interest_aliases)
        if direct is not None:
            return direct
        nested = row.get("non_operating_interest") or row.get("nonOperatingInterest") or {}
        return _find_number(nested, {"expense"}) if isinstance(nested, dict) else None

    ttm_interest = [interest_expense(row) for row in ttm_income]
    ttm_profit = [value(row, profit_aliases) for row in ttm_income]
    ebit_total = sum(ttm_ebit) if ttm_ebit and all(v is not None for v in ttm_ebit) else None
    interest_total = sum(abs(v) for v in ttm_interest) if ttm_interest and all(v is not None for v in ttm_interest) else None
    profit_total = sum(ttm_profit) if ttm_profit and all(v is not None for v in ttm_profit) else None

    if _consecutive(balance, 5):
        latest_bs, prior_bs = balance[0], balance[4]
        equity_aliases = {"totalshareholdersequity", "totalstockholdersequity", "shareholdersequity", "totalowners'equity", "totalowners equity"}
        asset_aliases = {"totalassets"}
        current_liability_aliases = {"totalcurrentliabilities", "currentliabilities"}
        debt_aliases = {"totaldebt"}
        equity_now = value(latest_bs, equity_aliases)
        equity_prior = value(prior_bs, equity_aliases)
        assets_now, assets_prior = value(latest_bs, asset_aliases), value(prior_bs, asset_aliases)
        current_liab_now = value(latest_bs, current_liability_aliases)
        current_liab_prior = value(prior_bs, current_liability_aliases)
        debt_now = value(latest_bs, debt_aliases)
        if debt_now is None:
            short_debt = _find_number(latest_bs, {"shorttermdebt", "shorttermborrowings"})
            long_debt = _find_number(latest_bs, {"longtermdebt", "longtermborrowings"})
            if short_debt is not None or long_debt is not None:
                debt_now = (short_debt or 0.0) + (long_debt or 0.0)
        if equity_now is not None and equity_now != 0 and debt_now is not None:
            put("DebtToEquity", debt_now / equity_now)
        if profit_total is not None and equity_now is not None and equity_prior is not None and (equity_now + equity_prior) != 0:
            put("ROEPercent", profit_total / ((equity_now + equity_prior) / 2.0) * 100.0)
        if ebit_total is not None and all(v is not None for v in (assets_now, assets_prior, current_liab_now, current_liab_prior)):
            ce_now, ce_prior = assets_now - current_liab_now, assets_prior - current_liab_prior
            average_ce = (ce_now + ce_prior) / 2.0
            if average_ce != 0:
                put("ROCEPercent", ebit_total / average_ce * 100.0)

    if ebit_total is not None and interest_total is not None and interest_total > 0:
        put("InterestCoverage", ebit_total / interest_total)

    if _consecutive(cash, 4) and len(ttm_income) == 4:
        cash_dates = [str(row.get("fiscal_date") or "") for row in cash[:4]]
        income_dates = [str(row.get("fiscal_date") or "") for row in ttm_income]
        if cash_dates == income_dates:
            ocf_values = [_find_number(row, {"operatingcashflow", "cashflowfromcontinuingoperatingactivities", "cashflowsfromusedinoperatingactivities"}) for row in cash[:4]]
            fcf_values = [_find_number(row, {"freecashflow"}) for row in cash[:4]]
            # Absolute cash-flow metrics are stored in INR only. Ratio metrics
            # remain currency invariant and can be used with reported currency.
            if currency == "INR":
                if all(v is not None for v in ocf_values):
                    put("OperatingCashFlowINR", sum(ocf_values), currency_code="INR")
                if all(v is not None for v in fcf_values):
                    put("FreeCashFlowINR", sum(fcf_values), currency_code="INR")

    if not metrics:
        raise ValueError(f"Twelve Data returned statements but no usable aligned metrics (currency={currency or 'unknown'})")
    endpoint_urls = {
        "income": f"{BASE_URL}/income_statement?symbol={symbol}&exchange=NSE",
        "balance": f"{BASE_URL}/balance_sheet?symbol={symbol}&exchange=NSE",
        "cash_flow": f"{BASE_URL}/cash_flow?symbol={symbol}&exchange=NSE",
    }
    return {
        "metrics": metrics,
        "metric_periods": metric_periods,
        "metric_currencies": metric_currencies,
        "metric_urls": {name: endpoint_urls["cash_flow" if name in {"OperatingCashFlowINR", "FreeCashFlowINR"} else "balance" if name in {"ROEPercent", "ROCEPercent", "DebtToEquity"} else "income"] for name in metrics},
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "currency": currency,
        "exchange": str(meta.get("exchange") or ""),
        "mic_code": str(meta.get("mic_code") or meta.get("micCode") or ""),
        "financial_period_end": latest_period,
        "calculation_basis": "QUARTERLY_TTM_ALIGNED_STATEMENTS",
    }
