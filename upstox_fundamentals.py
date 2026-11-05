"""Optional Upstox fundamentals adapter used only as a secondary data source.

Upstox values never become official XBRL evidence. They remain provider values
until the NSE/BSE filing audit independently reconciles them.
"""
from __future__ import annotations

import calendar
import os
from datetime import datetime, timezone
from typing import Any

import requests

BASE_URL = "https://api.upstox.com/v2/fundamentals"
METRIC_NAMES = ("RevenueGrowthPct", "ProfitGrowthPct", "OperatingCashFlowINR")


def _month_end_period(value: Any) -> tuple[str, str] | None:
    raw = str(value or "").strip()
    try:
        parsed = datetime.strptime(raw, "%b %Y")
    except ValueError:
        try:
            parsed = datetime.strptime(raw, "%B %Y")
        except ValueError:
            return None
    day = calendar.monthrange(parsed.year, parsed.month)[1]
    end = f"{parsed.year:04d}-{parsed.month:02d}-{day:02d}"
    return end, f"{parsed.year:04d}-{parsed.month:02d}-01"


def _unique_history(data: dict, collection_key: str, category: str) -> dict[str, float]:
    rows = [row for row in data.get(collection_key, [])
            if str(row.get("category", "")).strip().lower() == category]
    if len(rows) != 1:
        return {}
    result: dict[str, float] = {}
    for point in rows[0].get("history", []):
        period = _month_end_period(point.get("period"))
        try:
            value = float(point.get("value"))
        except (TypeError, ValueError):
            continue
        if period and period[0] not in result:
            result[period[0]] = value
    return result


def metrics_from_responses(income: dict, balance: dict, cashflow: dict) -> dict:
    """Extract only metrics represented unambiguously by documented API fields."""
    income_data = income.get("data", {})
    balance_data = balance.get("data", {})
    cash_data = cashflow.get("data", {})
    if (str(income.get("status", "")).lower() != "success"
            or str(balance.get("status", "")).lower() != "success"
            or str(cashflow.get("status", "")).lower() != "success"):
        raise ValueError("Upstox returned a non-success response")
    if (str(income_data.get("type", "")).lower() != "consolidated"
            or str(balance_data.get("type", "")).lower() != "consolidated"
            or str(cash_data.get("type", "")).lower() != "consolidated"):
        raise ValueError("Only consolidated statements are accepted by this adapter")
    if (str(income_data.get("time_period", "")).lower() != "yearly"
            or str(balance_data.get("time_period", "yearly")).lower() != "yearly"
            or str(cash_data.get("time_period", "")).lower() != "yearly"):
        raise ValueError("Upstox income and cash-flow statements must both be yearly")
    if any(str(item.get("units_in", "")).lower() != "crore"
           for item in (income_data, balance_data, cash_data)):
        raise ValueError("Upstox monetary units must be INR crore")

    revenue = _unique_history(income_data, "income_statement", "revenue")
    profit = _unique_history(income_data, "income_statement", "net_profit")
    operating = _unique_history(cash_data, "cash_flow", "operating")
    balance_periods = {period[0] for row in balance_data.get("history", [])
                       if (period := _month_end_period(row.get("period")))}
    common_periods = sorted(set(revenue) & set(profit) & set(operating) & balance_periods, reverse=True)
    if not common_periods:
        raise ValueError("No common annual period across revenue, net profit, and operating cash flow")
    latest = common_periods[0]
    result = {
        "FinancialPeriodEnd": latest,
        "MetricCalculationBasis": "ANNUAL_ALIGNED_STATEMENTS",
        "MetricPeriodAlignmentStatus": "VERIFIED",
        "ProviderSector": "",
        "UpstoxRetrievedAtUTC": datetime.now(timezone.utc).isoformat(),
        "UpstoxReportingBasis": "CONSOLIDATED",
        "UpstoxUnits": "INR_CRORE",
        "UpstoxStatus": "DATA_FOUND",
    }
    if len(common_periods) > 1:
        prior = common_periods[1]
        if prior < latest and revenue[prior] > 0:
            result["RevenueGrowthPct"] = (revenue[latest] - revenue[prior]) / revenue[prior] * 100.0
        if prior < latest and profit[prior] > 0:
            result["ProfitGrowthPct"] = (profit[latest] - profit[prior]) / profit[prior] * 100.0
    result["OperatingCashFlowINR"] = operating[latest] * 10_000_000
    result["UpstoxProviderSource"] = "Upstox Fundamentals API"
    result["UpstoxProviderSourceURL"] = f"{BASE_URL}/<ISIN>"
    result["UpstoxMissingMetrics"] = ";".join(name for name in METRIC_NAMES if name not in result)
    return result


def fetch_upstox_fundamentals(isin: str, *, access_token: str | None = None,
                              session=None, timeout: float = 20.0) -> dict:
    """Fetch annual consolidated income/cash-flow data; never logs the token."""
    token = access_token if access_token is not None else os.getenv("UPSTOX_ACCESS_TOKEN", "")
    clean_isin = str(isin or "").strip().upper()
    if not token.strip():
        return {"UpstoxStatus": "SKIPPED_NO_ACCESS_TOKEN", "UpstoxReason": "Set UPSTOX_ACCESS_TOKEN in the environment/Actions secret"}
    if not clean_isin:
        return {"UpstoxStatus": "SKIPPED_NO_ISIN", "UpstoxReason": "Candidate has no ISIN"}
    client = session or requests
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token.strip()}"}
    try:
        urls = {
            "income": f"{BASE_URL}/{clean_isin}/income-statement",
            "balance": f"{BASE_URL}/{clean_isin}/balance-sheet",
            "cashflow": f"{BASE_URL}/{clean_isin}/cash-flow",
        }
        responses = {}
        for key, url in urls.items():
            params = {"type": "consolidated", "fs": "true"}
            if key == "income":
                params["time_period"] = "yearly"
            response = client.get(url, params=params,
                                  headers=headers, timeout=timeout)
            response.raise_for_status()
            responses[key] = response.json()
        return metrics_from_responses(responses["income"], responses["balance"], responses["cashflow"])
    except requests.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return {"UpstoxStatus": "AUTH_OR_PROVIDER_ERROR" if status in (401, 403) else "PROVIDER_HTTP_ERROR",
                "UpstoxReason": f"HTTP {status or 'error'}"}
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        return {"UpstoxStatus": "PROVIDER_DATA_ERROR", "UpstoxReason": f"{type(exc).__name__}: {exc}"[:300]}
