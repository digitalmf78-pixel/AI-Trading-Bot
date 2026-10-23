"""Optional automatic fundamentals collector for NSE equity candidates.

Primary user-provided/verified CSV records are preserved. Missing fields are
filled from Yahoo Finance via yfinance when available. Yahoo is a secondary
source; values should be verified against company filings before investment use.
Collection failures are recorded per symbol and never reject a Delivery A/B row.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

INPUT_DIR = Path("data") / "inputs"
OUTPUT_DIR = Path("outputs")
METRICS_PATH = INPUT_DIR / "fundamental_metrics.csv"
DIAGNOSTICS_PATH = OUTPUT_DIR / "v8_fundamental_provider_diagnostics.csv"

METRIC_COLUMNS = [
    "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
    "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
    "FreeCashFlowINR", "EarningsQualityStatus", "ValuationStatus",
]
BASE_COLUMNS = [
    "TckrSymb", "AsOfDate", "FinancialPeriodEnd", "PublicationDate",
    "PublicationDateStatus", "DataRetrievedAtUTC", "ROECalculationMethod",
    "Source", "SourceURL",
] + METRIC_COLUMNS


def _present(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip() not in {"", "nan", "None", "<NA>"}


def _num(info: dict, key: str, multiplier: float = 1.0):
    value = info.get(key)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return pd.NA
    if not pd.notna(value):
        return pd.NA
    return value * multiplier


def _first_number(info: dict, keys: list[str], multiplier: float = 1.0):
    for key in keys:
        value = _num(info, key, multiplier)
        if _present(value):
            return value
    return pd.NA


def _safe_statement_value(statement: pd.DataFrame, possible_rows: list[str], col_index: int = 0):
    if not isinstance(statement, pd.DataFrame) or statement.empty:
        return pd.NA
    for label in possible_rows:
        if label in statement.index and len(statement.columns) > col_index:
            value = statement.iloc[:, col_index].get(label, pd.NA)
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if pd.notna(value):
                return value
    return pd.NA


def _growth_from_statement(statement: pd.DataFrame, possible_rows: list[str]):
    if not isinstance(statement, pd.DataFrame) or statement.empty or len(statement.columns) < 2:
        return pd.NA
    latest = _safe_statement_value(statement, possible_rows, 0)
    previous = _safe_statement_value(statement, possible_rows, 1)
    try:
        latest, previous = float(latest), float(previous)
        if previous == 0:
            return pd.NA
        return (latest - previous) / abs(previous) * 100.0
    except (TypeError, ValueError):
        return pd.NA


def _statement_columns_asof(statement: pd.DataFrame, asof_date=None) -> pd.DataFrame:
    """Return statement columns with period-end dates no later than EOD.

    If a point-in-time cutoff is supplied and statement column dates cannot be
    parsed, return an empty frame rather than risk future-period leakage.
    """
    if not isinstance(statement, pd.DataFrame) or statement.empty:
        return pd.DataFrame()
    if asof_date is None:
        return statement
    cutoff = pd.to_datetime(asof_date, errors="coerce")
    if pd.isna(cutoff):
        return pd.DataFrame()
    allowed = []
    for col in statement.columns:
        period = pd.to_datetime(col, errors="coerce")
        if pd.notna(period) and period.normalize() <= cutoff.normalize():
            allowed.append(col)
    return statement.loc[:, allowed] if allowed else pd.DataFrame()


def _financial_period_end(ticker_obj, info: dict, asof_date=None) -> str:
    """Find the latest observable statement period on/before the EOD cutoff."""
    candidates = []
    for attr in ("financials", "balance_sheet", "cashflow",
                 "income_stmt", "quarterly_income_stmt", "quarterly_balance_sheet", "quarterly_cashflow"):
        try:
            statement = getattr(ticker_obj, attr)
        except Exception:
            continue
        if isinstance(statement, pd.DataFrame) and not statement.empty:
            for col in statement.columns:
                parsed = pd.to_datetime(col, errors="coerce")
                if pd.notna(parsed):
                    candidates.append(parsed.normalize())
    cutoff = pd.to_datetime(asof_date, errors="coerce") if asof_date is not None else pd.NaT
    candidates = [d for d in candidates if pd.isna(cutoff) or d <= cutoff.normalize()]
    if candidates:
        return max(candidates).date().isoformat()

    # Info timestamps are fallback metadata only; never use nextFiscalYearEnd.
    for key in ("mostRecentQuarter", "lastFiscalYearEnd"):
        value = info.get(key)
        if value:
            try:
                parsed = datetime.fromtimestamp(int(value), tz=timezone.utc).date()
                if asof_date is None or parsed <= pd.to_datetime(asof_date).date():
                    return parsed.isoformat()
            except (TypeError, ValueError, OSError, OverflowError):
                pass
    return ""


def _roe_from_statements(financials: pd.DataFrame, balance_sheet: pd.DataFrame):
    """Calculate a transparent ROE fallback when provider ROE is absent.

    Prefer net income divided by average opening/closing equity. If only one
    equity period is available, use ending equity as a clearly labelled proxy.
    The output is a calculated metric, not a provider-reported ROE.
    """
    net_income = _safe_statement_value(financials, [
        "Net Income", "Net Income Common Stockholders",
        "Net Income From Continuing Operation Net Minority Interest",
    ])
    equity_rows = ["Stockholders Equity", "Total Stockholder Equity",
                   "Common Stock Equity", "Total Equity Gross Minority Interest"]
    latest_equity = _safe_statement_value(balance_sheet, equity_rows, 0)
    prior_equity = _safe_statement_value(balance_sheet, equity_rows, 1)
    if not (_present(net_income) and _present(latest_equity)):
        return pd.NA, "UNAVAILABLE_MISSING_NET_INCOME_OR_EQUITY"
    denominator = float(latest_equity)
    method = "NET_INCOME_DIVIDED_BY_ENDING_EQUITY_PROXY"
    if _present(prior_equity):
        average_equity = (float(latest_equity) + float(prior_equity)) / 2.0
        if average_equity != 0:
            denominator = average_equity
            method = "NET_INCOME_DIVIDED_BY_AVERAGE_EQUITY"
    if denominator == 0:
        return pd.NA, "UNAVAILABLE_ZERO_EQUITY"
    return float(net_income) / denominator * 100.0, method


def _fetch_one(symbol: str, ticker_factory=None, asof_date=None) -> tuple[dict, dict]:
    symbol = str(symbol).strip().upper()
    url = f"https://finance.yahoo.com/quote/{symbol}.NS/financials/"
    diagnostic = {"TckrSymb": symbol, "ProviderStatus": "WAIT_FOR_DATA", "ProviderReason": "", "ProviderSource": "Yahoo Finance via yfinance", "ProviderSourceURL": url, "AttemptedAtUTC": datetime.now(timezone.utc).isoformat()}
    record = {col: pd.NA for col in BASE_COLUMNS}
    record.update({
        "TckrSymb": symbol,
        # AsOfDate is the financial period end for backward compatibility; it is
        # NOT the retrieval date or a publication date.
        "AsOfDate": pd.NA,
        "FinancialPeriodEnd": pd.NA,
        "PublicationDate": pd.NA,
        "PublicationDateStatus": "UNVERIFIED",
        "DataRetrievedAtUTC": datetime.now(timezone.utc).isoformat(),
        "ROECalculationMethod": "PROVIDER_REPORTED_OR_NOT_YET_CALCULATED",
        "Source": "Yahoo Finance via yfinance (secondary; verify against filings)",
        "SourceURL": url,
    })
    try:
        if ticker_factory is None:
            import yfinance as yf  # type: ignore
            ticker_factory = yf.Ticker
        ticker = ticker_factory(f"{symbol}.NS")
        info = ticker.info or {}
        revenue_growth = _first_number(info, ["revenueGrowth"], 100.0)
        profit_growth = _first_number(info, ["earningsGrowth", "earningsQuarterlyGrowth"], 100.0)
        roe = _first_number(info, ["returnOnEquity"], 100.0)
        roe_method = "YAHOO_INFO_RETURN_ON_EQUITY" if _present(roe) else "MISSING_PROVIDER_ROE"
        debt_to_equity = _first_number(info, ["debtToEquity"])
        # Yahoo commonly reports debtToEquity as a percentage (e.g. 80 means 0.8x).
        if _present(debt_to_equity):
            debt_to_equity = float(debt_to_equity) / 100.0
        ocf = _first_number(info, ["operatingCashflow"])
        fcf = _first_number(info, ["freeCashflow"])
        ebit = _first_number(info, ["ebit", "ebitda"])
        interest_expense = _first_number(info, ["interestExpense"])
        assets = _first_number(info, ["totalAssets"])
        current_liabilities = _first_number(info, ["totalCurrentLiabilities", "currentLiabilities"])
        equity = _first_number(info, ["totalStockholderEquity", "stockholdersEquity"])
        total_debt = _first_number(info, ["totalDebt"])

        financials = pd.DataFrame()
        balance_sheet = pd.DataFrame()
        cashflow = pd.DataFrame()
        # Statements are only requested when needed, so a provider's partial info
        # response can still produce useful, explicitly partial data.
        need_statements = (not _present(revenue_growth) or not _present(profit_growth) or
                           not _present(roe) or not _present(ocf) or not _present(fcf) or
                           not _present(interest_expense) or not _present(assets) or
                           not _present(current_liabilities) or not _present(equity) or
                           not _present(total_debt))
        if need_statements:
            # Use annual statements first for year-over-year growth calculations;
            # quarterly statements are a fallback only when annual data is absent.
            try:
                financials = ticker.financials
            except Exception:
                financials = pd.DataFrame()
            try:
                balance_sheet = ticker.balance_sheet
            except Exception:
                balance_sheet = pd.DataFrame()
            try:
                cashflow = ticker.cashflow
            except Exception:
                cashflow = pd.DataFrame()
            financials = _statement_columns_asof(financials, asof_date)
            balance_sheet = _statement_columns_asof(balance_sheet, asof_date)
            cashflow = _statement_columns_asof(cashflow, asof_date)
            if financials.empty:
                try:
                    financials = _statement_columns_asof(getattr(ticker, "quarterly_income_stmt", pd.DataFrame()), asof_date)
                except Exception:
                    financials = pd.DataFrame()
            if balance_sheet.empty:
                try:
                    balance_sheet = _statement_columns_asof(getattr(ticker, "quarterly_balance_sheet", pd.DataFrame()), asof_date)
                except Exception:
                    balance_sheet = pd.DataFrame()
            if cashflow.empty:
                try:
                    cashflow = _statement_columns_asof(getattr(ticker, "quarterly_cashflow", pd.DataFrame()), asof_date)
                except Exception:
                    cashflow = pd.DataFrame()

        if not _present(revenue_growth):
            revenue_growth = _growth_from_statement(financials, ["Total Revenue", "Operating Revenue"])
        if not _present(profit_growth):
            profit_growth = _growth_from_statement(financials, ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"])
        if not _present(ocf):
            ocf = _safe_statement_value(cashflow, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities", "Operating Cash Flow"])
        if not _present(fcf):
            cash_capex = _safe_statement_value(cashflow, ["Capital Expenditure", "Capital Expenditures"])
            if _present(ocf) and _present(cash_capex):
                # Yahoo statement capex is generally a negative cash outflow.
                fcf = float(ocf) + float(cash_capex)
        if not _present(ebit):
            ebit = _safe_statement_value(financials, ["EBIT", "Operating Income"])
        if not _present(interest_expense):
            interest_expense = _safe_statement_value(financials, ["Interest Expense", "Interest Expense Non Operating"])
        if not _present(assets):
            assets = _safe_statement_value(balance_sheet, ["Total Assets"])
        if not _present(current_liabilities):
            current_liabilities = _safe_statement_value(balance_sheet, ["Current Liabilities", "Total Current Liabilities"])
        if not _present(equity):
            equity = _safe_statement_value(balance_sheet, ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"])
        if not _present(total_debt):
            total_debt = _safe_statement_value(balance_sheet, ["Total Debt", "Long Term Debt And Capital Lease Obligation"])
        if not _present(debt_to_equity) and _present(total_debt) and _present(equity) and float(equity) != 0:
            debt_to_equity = float(total_debt) / float(equity)
        if not _present(roe):
            roe, roe_method = _roe_from_statements(financials, balance_sheet)

        roce = pd.NA
        if _present(ebit) and _present(assets) and _present(current_liabilities):
            capital_employed = float(assets) - float(current_liabilities)
            if capital_employed != 0:
                roce = float(ebit) / capital_employed * 100.0
        interest_coverage = pd.NA
        if _present(ebit) and _present(interest_expense) and float(interest_expense) != 0:
            interest_coverage = float(ebit) / abs(float(interest_expense))

        values = {
            "RevenueGrowthPct": revenue_growth,
            "ProfitGrowthPct": profit_growth,
            "ROEPercent": roe,
            "ROCEPercent": roce,
            "DebtToEquity": debt_to_equity,
            "InterestCoverage": interest_coverage,
            "OperatingCashFlowINR": ocf,
            "FreeCashFlowINR": fcf,
        }
        for col, value in values.items():
            record[col] = value if _present(value) else pd.NA
        record["EarningsQualityStatus"] = (
            "POSITIVE_OPERATING_CASH_FLOW" if _present(ocf) and float(ocf) > 0
            else "NEGATIVE_OPERATING_CASH_FLOW" if _present(ocf) and float(ocf) < 0
            else pd.NA
        )
        valuation_multiple = _first_number(info, ["trailingPE", "forwardPE"])
        record["ValuationStatus"] = "VALUATION_MULTIPLE_AVAILABLE" if _present(valuation_multiple) else "VALUATION_DATA_MISSING"
        record["ROECalculationMethod"] = roe_method
        period_end = _financial_period_end(ticker, info, asof_date=asof_date)
        record["FinancialPeriodEnd"] = period_end if period_end else pd.NA
        record["AsOfDate"] = period_end if period_end else pd.NA
        # Yahoo's generic yfinance info/statement endpoints do not reliably
        # expose the exchange filing publication timestamp. Never infer it from
        # retrieval time or financial period end.
        record["PublicationDate"] = pd.NA
        record["PublicationDateStatus"] = "UNVERIFIED"
        metric_count = sum(_present(record.get(col)) for col in METRIC_COLUMNS)
        diagnostic["ProviderStatus"] = "DATA_FOUND" if metric_count else "MISSING_DATA"
        diagnostic["ProviderReason"] = f"metrics_available={metric_count}/{len(METRIC_COLUMNS)}"
        diagnostic["FinancialPeriodEnd"] = record.get("FinancialPeriodEnd", "")
        diagnostic["PublicationDate"] = record.get("PublicationDate", "")
        diagnostic["PublicationDateStatus"] = record.get("PublicationDateStatus", "UNVERIFIED")
        diagnostic["DataRetrievedAtUTC"] = record.get("DataRetrievedAtUTC", "")
        diagnostic["ROECalculationMethod"] = roe_method
        diagnostic["MetricsAvailable"] = metric_count
    except Exception as exc:
        diagnostic["ProviderStatus"] = "PROVIDER_ERROR"
        diagnostic["ProviderReason"] = f"{type(exc).__name__}: {exc}"[:500]
        diagnostic["MetricsAvailable"] = 0
    return record, diagnostic


def collect_missing_fundamentals(candidates: pd.DataFrame, metrics_path: str | Path = METRICS_PATH, enabled: bool | None = None, ticker_factory=None, pause_seconds: float = 0.15, asof_date=None) -> pd.DataFrame:
    """Fetch missing fundamentals for every unique Delivery A/B symbol.

    Existing manual records are authoritative. Provider failures remain visible
    in diagnostics and never remove candidate rows.
    """
    if enabled is None:
        enabled = os.getenv("V8_AUTO_FETCH_FUNDAMENTALS", "true").strip().lower() not in {"0", "false", "no", "off"}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(metrics_path)
    if path.exists() and path.stat().st_size:
        try:
            existing = pd.read_csv(path)
        except Exception:
            existing = pd.DataFrame(columns=BASE_COLUMNS)
    else:
        existing = pd.DataFrame(columns=BASE_COLUMNS)
    for col in BASE_COLUMNS:
        if col not in existing.columns:
            existing[col] = pd.NA
    existing["TckrSymb"] = existing["TckrSymb"].astype(str).str.strip().str.upper()

    symbols = []
    if candidates is not None and not candidates.empty and "TckrSymb" in candidates.columns:
        symbols = sorted({str(x).strip().upper() for x in candidates["TckrSymb"].dropna() if str(x).strip() and str(x).strip().lower() != "nan"})
    records = {str(row["TckrSymb"]): row.to_dict() for _, row in existing.iterrows() if str(row.get("TckrSymb", "")).strip() not in {"", "NAN", "nan"}}
    diagnostics = []
    for symbol in symbols:
        current = records.get(symbol, {})
        if not current:
            current = {col: pd.NA for col in BASE_COLUMNS}
            current["TckrSymb"] = symbol
            records[symbol] = current
        missing = [col for col in METRIC_COLUMNS if not _present(current.get(col))]
        if not enabled:
            diagnostics.append({"TckrSymb": symbol, "ProviderStatus": "DISABLED", "ProviderReason": "V8_AUTO_FETCH_FUNDAMENTALS disabled; manual CSV only", "ProviderSource": "", "ProviderSourceURL": "", "AttemptedAtUTC": datetime.now(timezone.utc).isoformat(), "MetricsAvailable": sum(_present(current.get(c)) for c in METRIC_COLUMNS)})
            continue
        if not missing:
            diagnostics.append({"TckrSymb": symbol, "ProviderStatus": "EXISTING_RECORD_COMPLETE", "ProviderReason": "all metrics already populated in input CSV", "ProviderSource": current.get("Source", ""), "ProviderSourceURL": current.get("SourceURL", ""), "AttemptedAtUTC": datetime.now(timezone.utc).isoformat(), "MetricsAvailable": len(METRIC_COLUMNS)})
            continue
        fetched, diagnostic = _fetch_one(symbol, ticker_factory=ticker_factory, asof_date=asof_date)
        # Never overwrite a manually supplied value with provider data.
        merged = dict(current)
        for col in BASE_COLUMNS + ["FinancialPeriodEnd"]:
            if col not in merged:
                merged[col] = pd.NA
        for col in METRIC_COLUMNS + ["AsOfDate", "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus", "DataRetrievedAtUTC", "ROECalculationMethod", "Source", "SourceURL"]:
            if not _present(merged.get(col)) and _present(fetched.get(col)):
                merged[col] = fetched.get(col)
        if not _present(merged.get("TckrSymb")):
            merged["TckrSymb"] = symbol
        if not _present(merged.get("FinancialPeriodEnd")):
            merged["FinancialPeriodEnd"] = fetched.get("FinancialPeriodEnd", pd.NA)
        records[symbol] = merged
        diagnostic["MetricsAvailable"] = sum(_present(merged.get(c)) for c in METRIC_COLUMNS)
        diagnostic["MetricsMissing"] = ";".join([c for c in METRIC_COLUMNS if not _present(merged.get(c))])
        diagnostics.append(diagnostic)
        if pause_seconds > 0:
            time.sleep(pause_seconds)

    combined = pd.DataFrame(list(records.values()))
    for col in BASE_COLUMNS:
        if col not in combined.columns:
            combined[col] = pd.NA
    # Preserve all existing records (including symbols outside today's universe).
    combined = combined.drop_duplicates(subset=["TckrSymb"], keep="last")
    # Verify publication dates only against exact NSE official result-announcement
    # matches (same symbol + financial period end). Network failures are non-fatal.
    try:
        from fundamental_official_filings import apply_official_publication_dates
        combined = apply_official_publication_dates(combined, asof_date=asof_date)
    except Exception as official_date_exc:
        print(f"[FUNDAMENTAL OFFICIAL DATE] verification unavailable; retain UNVERIFIED dates: {type(official_date_exc).__name__}: {official_date_exc}")
    combined.to_csv(path, index=False)
    pd.DataFrame(diagnostics).to_csv(DIAGNOSTICS_PATH, index=False)
    print(f"[FUNDAMENTAL PROVIDER] Delivery A/B unique symbols={len(symbols)}; provider statuses={pd.Series([d.get('ProviderStatus') for d in diagnostics]).value_counts().to_dict()}; metrics cache={path}; diagnostics={DIAGNOSTICS_PATH}")
    return combined
