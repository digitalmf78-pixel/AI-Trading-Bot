"""Optional automatic fundamentals collector for NSE equity candidates.

Primary user-provided/verified CSV records are preserved. Missing fields are
filled from Yahoo Finance via yfinance when available. Yahoo is a secondary
source; values should be verified against company filings before investment use.
Collection failures are recorded per symbol and never reject a Delivery A/B row.
"""
from __future__ import annotations

import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

INPUT_DIR = Path("data") / "inputs"
OUTPUT_DIR = Path("outputs")
METRICS_PATH = INPUT_DIR / "fundamental_metrics.csv"
HISTORY_DIR = Path("data") / "cache" / "fundamental_history"
DIAGNOSTICS_PATH = OUTPUT_DIR / "v8_fundamental_provider_diagnostics.csv"

METRIC_COLUMNS = [
    "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
    "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
    "FreeCashFlowINR", "EarningsQualityStatus", "ValuationStatus",
]
BASE_COLUMNS = [
    "TckrSymb", "AsOfDate", "DataRetrievedAtUTC", "Source", "SourceURL",
    "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus",
    "OfficialFilingURL", "OfficialFilingSource", "MetricPeriodAlignmentStatus",
    "ProviderSector",
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


def _financial_period_end(ticker_obj, info: dict) -> str:
    """Return a reported statement period, never a forecast fiscal-year end.

    Statement column dates take priority. Yahoo's nextFiscalYearEnd is explicitly
    excluded because it is a forecast/calendar field, not evidence of a reported
    financial period. mostRecentQuarter/lastFiscalYearEnd are fallback metadata
    only and must still pass official publication-date verification downstream.
    """
    for attr in ("quarterly_financials", "quarterly_balance_sheet", "quarterly_cashflow",
                 "financials", "balance_sheet", "cashflow"):
        try:
            statement = getattr(ticker_obj, attr)
        except Exception:
            statement = None
        if isinstance(statement, pd.DataFrame) and len(statement.columns):
            dates = pd.to_datetime(list(statement.columns), errors="coerce")
            dates = [d for d in dates if not pd.isna(d)]
            if dates:
                return max(dates).date().isoformat()
    for key in ("mostRecentQuarter", "lastFiscalYearEnd"):
        value = info.get(key)
        if value:
            try:
                return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
            except (TypeError, ValueError, OSError, OverflowError):
                pass
    return ""


def _row_value(statement, labels, col):
    """Value of the first matching row label at column position `col`."""
    if not isinstance(statement, pd.DataFrame) or statement.empty or len(statement.columns) <= col:
        return pd.NA
    for label in labels:
        if label in statement.index:
            try:
                value = float(statement.iloc[:, col].get(label, pd.NA))
            except (TypeError, ValueError):
                continue
            if pd.notna(value):
                return value
    return pd.NA


def _col_date(statement):
    if not isinstance(statement, pd.DataFrame) or statement.empty:
        return None
    parsed = pd.to_datetime(statement.columns[0], errors="coerce")
    return None if pd.isna(parsed) else parsed.date().isoformat()


def _aligned_annual_metrics(ticker_obj) -> dict:
    """Compute every metric from ONE fiscal year of statements.

    Income statement, balance sheet and cash-flow statement must all have the
    same latest period-end column; otherwise `ok` is False and the caller falls
    back to the legacy path, which stays UNVERIFIED. Nothing is taken from
    Yahoo's `info` snapshot here, so no TTM/annual mixing can occur.
    Growth needs the previous year's column; loss-making previous years give no
    percentage (NA) rather than a misleading sign-flipped number.
    """
    out = {"ok": False, "period_end": "", "values": {}, "reason": ""}
    stmts = {}
    for name, attr in (("income", "financials"), ("balance", "balance_sheet"), ("cash", "cashflow")):
        try:
            stmts[name] = getattr(ticker_obj, attr)
        except Exception:
            stmts[name] = None
    dates = {k: _col_date(v) for k, v in stmts.items()}
    if not all(dates.values()):
        out["reason"] = "ANNUAL_STATEMENT_MISSING:" + ",".join(k for k, v in dates.items() if not v)
        return out
    if len(set(dates.values())) != 1:
        out["reason"] = "STATEMENT_PERIODS_DIFFER:" + ",".join(f"{k}={v}" for k, v in dates.items())
        return out
    inc, bal, cash = stmts["income"], stmts["balance"], stmts["cash"]
    rev0 = _row_value(inc, ["Total Revenue", "Operating Revenue"], 0)
    rev1 = _row_value(inc, ["Total Revenue", "Operating Revenue"], 1)
    ni_labels = ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"]
    ni0, ni1 = _row_value(inc, ni_labels, 0), _row_value(inc, ni_labels, 1)
    ebit = _row_value(inc, ["EBIT", "Operating Income"], 0)
    interest = _row_value(inc, ["Interest Expense", "Interest Expense Non Operating"], 0)
    assets = _row_value(bal, ["Total Assets"], 0)
    cur_liab = _row_value(bal, ["Current Liabilities", "Total Current Liabilities"], 0)
    eq_labels = ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"]
    eq0, eq1 = _row_value(bal, eq_labels, 0), _row_value(bal, eq_labels, 1)
    debt = _row_value(bal, ["Total Debt", "Long Term Debt And Capital Lease Obligation"], 0)
    ocf = _row_value(cash, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], 0)
    fcf = _row_value(cash, ["Free Cash Flow"], 0)
    if not _present(fcf):
        capex = _row_value(cash, ["Capital Expenditure", "Capital Expenditures"], 0)
        if _present(ocf) and _present(capex):
            fcf = float(ocf) + float(capex)  # capex is reported as a negative outflow

    def growth(new, old):
        if not (_present(new) and _present(old)) or float(old) <= 0:
            return pd.NA
        return (float(new) - float(old)) / float(old) * 100.0

    avg_equity = pd.NA
    if _present(eq0) and _present(eq1):
        avg_equity = (float(eq0) + float(eq1)) / 2.0
    elif _present(eq0):
        avg_equity = float(eq0)
    roe = pd.NA
    if _present(ni0) and _present(avg_equity) and float(avg_equity) > 0:
        roe = float(ni0) / float(avg_equity) * 100.0
    roce = pd.NA
    if _present(ebit) and _present(assets) and _present(cur_liab) and float(assets) - float(cur_liab) > 0:
        roce = float(ebit) / (float(assets) - float(cur_liab)) * 100.0
    de = pd.NA
    if _present(debt) and _present(eq0) and float(eq0) > 0:
        de = float(debt) / float(eq0)
    coverage = pd.NA
    if _present(ebit) and _present(interest):
        # Zero reported interest = debt-free; use a documented cap instead of infinity.
        coverage = 999.0 if float(interest) == 0 else float(ebit) / abs(float(interest))

    out["values"] = {
        "RevenueGrowthPct": growth(rev0, rev1), "ProfitGrowthPct": growth(ni0, ni1),
        "ROEPercent": roe, "ROCEPercent": roce, "DebtToEquity": de,
        "InterestCoverage": coverage, "OperatingCashFlowINR": ocf, "FreeCashFlowINR": fcf,
    }
    out["period_end"] = dates["income"]
    out["ok"] = True
    return out


def _aligned_quarterly_metrics(ticker_obj) -> dict:
    """Compute metrics from aligned quarterly statements when the provider exposes them.

    Growth is year-over-year (latest quarter vs the same quarter one year earlier).
    Point-in-time balance-sheet ratios use the latest quarter. Quarterly ROE/ROCE
    are annualized (x4) so they remain comparable to annual threshold conventions.
    Cash-flow values are the latest reported quarter, not a silently mixed annual total.
    """
    out = {"ok": False, "period_end": "", "values": {}, "reason": ""}
    stmts = {}
    for name, attr in (("income", "quarterly_financials"), ("balance", "quarterly_balance_sheet"), ("cash", "quarterly_cashflow")):
        try:
            stmts[name] = getattr(ticker_obj, attr)
        except Exception:
            stmts[name] = None
    dates = {k: _col_date(v) for k, v in stmts.items()}
    if not all(dates.values()):
        out["reason"] = "QUARTERLY_STATEMENT_MISSING:" + ",".join(k for k, v in dates.items() if not v)
        return out
    if len(set(dates.values())) != 1:
        out["reason"] = "QUARTERLY_STATEMENT_PERIODS_DIFFER:" + ",".join(f"{k}={v}" for k, v in dates.items())
        return out
    inc, bal, cash = stmts["income"], stmts["balance"], stmts["cash"]
    rev_labels = ["Total Revenue", "Operating Revenue"]
    ni_labels = ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"]
    rev0, rev4 = _row_value(inc, rev_labels, 0), _row_value(inc, rev_labels, 4)
    ni0, ni4 = _row_value(inc, ni_labels, 0), _row_value(inc, ni_labels, 4)
    ebit = _row_value(inc, ["EBIT", "Operating Income"], 0)
    interest = _row_value(inc, ["Interest Expense", "Interest Expense Non Operating"], 0)
    assets = _row_value(bal, ["Total Assets"], 0)
    cur_liab = _row_value(bal, ["Current Liabilities", "Total Current Liabilities"], 0)
    eq0 = _row_value(bal, ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"], 0)
    debt = _row_value(bal, ["Total Debt", "Long Term Debt And Capital Lease Obligation"], 0)
    ocf = _row_value(cash, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], 0)
    fcf = _row_value(cash, ["Free Cash Flow"], 0)
    if not _present(fcf):
        capex = _row_value(cash, ["Capital Expenditure", "Capital Expenditures"], 0)
        if _present(ocf) and _present(capex):
            fcf = float(ocf) + float(capex)
    def yoy(new, old):
        if not (_present(new) and _present(old)) or float(old) <= 0:
            return pd.NA
        return (float(new) - float(old)) / float(old) * 100.0
    roe = (float(ni0) * 4 / float(eq0) * 100.0) if _present(ni0) and _present(eq0) and float(eq0) > 0 else pd.NA
    capital = float(assets) - float(cur_liab) if _present(assets) and _present(cur_liab) else 0
    roce = (float(ebit) * 4 / capital * 100.0) if _present(ebit) and capital > 0 else pd.NA
    de = float(debt) / float(eq0) if _present(debt) and _present(eq0) and float(eq0) > 0 else pd.NA
    coverage = (float(ebit) / abs(float(interest))) if _present(ebit) and _present(interest) and float(interest) != 0 else (999.0 if _present(interest) and float(interest) == 0 else pd.NA)
    out["values"] = {"RevenueGrowthPct": yoy(rev0, rev4), "ProfitGrowthPct": yoy(ni0, ni4), "ROEPercent": roe, "ROCEPercent": roce, "DebtToEquity": de, "InterestCoverage": coverage, "OperatingCashFlowINR": ocf, "FreeCashFlowINR": fcf}
    out["period_end"] = dates["income"]
    out["ok"] = True
    return out


def _fetch_one(symbol: str, ticker_factory=None) -> tuple[dict, dict]:
    symbol = str(symbol).strip().upper()
    url = f"https://finance.yahoo.com/quote/{symbol}.NS/financials/"
    diagnostic = {"TckrSymb": symbol, "ProviderStatus": "WAIT_FOR_DATA", "ProviderReason": "", "ProviderSource": "Yahoo Finance via yfinance", "ProviderSourceURL": url, "AttemptedAtUTC": datetime.now(timezone.utc).isoformat()}
    record = {col: pd.NA for col in BASE_COLUMNS}
    record.update({
        "TckrSymb": symbol, "AsOfDate": "", "DataRetrievedAtUTC": datetime.now(timezone.utc).isoformat(),
        "Source": "Yahoo Finance via yfinance (secondary; verify against filings)", "SourceURL": url,
        "PublicationDateStatus": "UNVERIFIED", "MetricPeriodAlignmentStatus": "UNVERIFIED",
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
        need_statements = not _present(revenue_growth) or not _present(profit_growth) or not _present(ocf) or not _present(fcf) or not _present(interest_expense) or not _present(assets) or not _present(current_liabilities) or not _present(equity) or not _present(total_debt)
        if need_statements:
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

        roce = pd.NA
        if _present(ebit) and _present(assets) and _present(current_liabilities):
            capital_employed = float(assets) - float(current_liabilities)
            if capital_employed != 0:
                roce = float(ebit) / capital_employed * 100.0
        interest_coverage = pd.NA
        if _present(ebit) and _present(interest_expense) and float(interest_expense) != 0:
            interest_coverage = float(ebit) / abs(float(interest_expense))

        aligned_quarterly = _aligned_quarterly_metrics(ticker)
        aligned_annual = _aligned_annual_metrics(ticker)
        aligned = aligned_quarterly if aligned_quarterly["ok"] else aligned_annual
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
        if aligned["ok"]:
            # One fiscal year, one set of statements: replace (never mix with) snapshot values.
            values = aligned["values"]
            record["MetricPeriodAlignmentStatus"] = "VERIFIED"
            diagnostic["AlignmentNote"] = (f"ALIGNED_QUARTERLY_STATEMENTS:{aligned['period_end']}" if aligned is aligned_quarterly else f"ALIGNED_ANNUAL_STATEMENTS:{aligned['period_end']}")
        else:
            diagnostic["AlignmentNote"] = aligned_quarterly["reason"] or aligned_annual["reason"] or "LEGACY_SNAPSHOT_PATH"
        for col, value in values.items():
            record[col] = value if _present(value) else pd.NA
        sector = info.get("sector") if isinstance(info, dict) else None
        record["ProviderSector"] = str(sector).strip() if sector else pd.NA
        record["EarningsQualityStatus"] = (
            "POSITIVE_OPERATING_CASH_FLOW" if _present(ocf) and float(ocf) > 0
            else "NEGATIVE_OPERATING_CASH_FLOW" if _present(ocf) and float(ocf) < 0
            else pd.NA
        )
        valuation_multiple = _first_number(info, ["trailingPE", "forwardPE"])
        record["ValuationStatus"] = "VALUATION_MULTIPLE_AVAILABLE" if _present(valuation_multiple) else "VALUATION_DATA_MISSING"
        record["FinancialPeriodEnd"] = aligned["period_end"] if aligned["ok"] else _financial_period_end(ticker, info)
        metric_count = sum(_present(record.get(col)) for col in METRIC_COLUMNS)
        diagnostic["ProviderStatus"] = "DATA_FOUND" if metric_count else "MISSING_DATA"
        diagnostic["ProviderReason"] = f"metrics_available={metric_count}/{len(METRIC_COLUMNS)}"
        diagnostic["FinancialPeriodEnd"] = record.get("FinancialPeriodEnd", "")
        diagnostic["MetricsAvailable"] = metric_count
    except Exception as exc:
        diagnostic["ProviderStatus"] = "PROVIDER_ERROR"
        diagnostic["ProviderReason"] = f"{type(exc).__name__}: {exc}"[:500]
        diagnostic["MetricsAvailable"] = 0
    return record, diagnostic


def _is_stale_provider_record(record: dict, today, refresh_days: int) -> bool:
    """Provider-sourced (never manual) records older than refresh_days are refetched."""
    raw_source = record.get("Source", "")
    source = str(raw_source) if _present(raw_source) else ""
    if not source.startswith("Yahoo Finance"):
        return False
    retrieved = pd.to_datetime(record.get("DataRetrievedAtUTC"), errors="coerce", utc=True)
    if pd.isna(retrieved):
        return True
    return (pd.Timestamp(today, tz="UTC") - retrieved).days >= refresh_days


def save_fundamental_history_snapshot(metrics_path: str | Path = METRICS_PATH,
                                       asof_date=None,
                                       history_dir: str | Path = HISTORY_DIR) -> Path | None:
    """Save a dated, full-universe snapshot after official-date verification.

    Existing dated snapshots are updated in place for same-day reruns; snapshots
    from earlier dates are never deleted. This is intended to live under the
    GitHub Actions persistent cache path configured in the workflow.
    """
    source = Path(metrics_path)
    if not source.exists() or source.stat().st_size == 0:
        return None
    cutoff = pd.to_datetime(asof_date if asof_date is not None else date.today(), errors="coerce")
    if pd.isna(cutoff):
        return None
    target_dir = Path(history_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"fundamental_metrics_{cutoff.date().isoformat()}.csv"
    target.write_bytes(source.read_bytes())
    return target


def collect_missing_fundamentals(
    candidates: pd.DataFrame,
    metrics_path: str | Path = METRICS_PATH,
    enabled: bool | None = None,
    ticker_factory=None,
    pause_seconds: float = 0.15,
    asof_date=None,
    filings_fetcher: Callable | None = None,
) -> pd.DataFrame:
    """Fetch missing fundamentals for every unique Delivery A/B symbol.

    Existing manual records are authoritative. Provider failures remain visible
    in diagnostics and never remove candidate rows.
    """
    if enabled is None:
        enabled = os.getenv("V8_AUTO_FETCH_FUNDAMENTALS", "true").strip().lower() not in {"0", "false", "no", "off"}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = pd.to_datetime(asof_date if asof_date is not None else date.today(), errors="coerce")
    cutoff_text = "" if pd.isna(cutoff) else cutoff.date().isoformat()
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
        refresh_days = int(os.getenv("V8_FUNDAMENTAL_REFRESH_DAYS", "30") or 30)
        today_for_refresh = cutoff if pd.notna(cutoff) else pd.Timestamp.today()
        if enabled and _is_stale_provider_record(current, today_for_refresh.date(), refresh_days):
            # Provider-owned record is old: clear it so new quarterly/annual results are picked up.
            for col in METRIC_COLUMNS + ["FinancialPeriodEnd", "PublicationDate", "MetricPeriodAlignmentStatus"]:
                current[col] = pd.NA
            current["PublicationDateStatus"] = "UNVERIFIED"
        missing = [col for col in METRIC_COLUMNS if not _present(current.get(col))]
        provider_owned = not any(_present(current.get(col)) for col in METRIC_COLUMNS)
        if not enabled:
            diagnostics.append({"TckrSymb": symbol, "ProviderStatus": "DISABLED", "ProviderReason": "V8_AUTO_FETCH_FUNDAMENTALS disabled; manual CSV only", "ProviderSource": "", "ProviderSourceURL": "", "AttemptedAtUTC": datetime.now(timezone.utc).isoformat(), "MetricsAvailable": sum(_present(current.get(c)) for c in METRIC_COLUMNS)})
            continue
        if not missing:
            diagnostics.append({"TckrSymb": symbol, "ProviderStatus": "EXISTING_RECORD_COMPLETE", "ProviderReason": "all metrics already populated in input CSV", "ProviderSource": current.get("Source", ""), "ProviderSourceURL": current.get("SourceURL", ""), "AttemptedAtUTC": datetime.now(timezone.utc).isoformat(), "MetricsAvailable": len(METRIC_COLUMNS)})
            continue
        fetched, diagnostic = _fetch_one(symbol, ticker_factory=ticker_factory)
        # Never overwrite a manually supplied value with provider data.
        merged = dict(current)
        for col in BASE_COLUMNS:
            if col not in merged:
                merged[col] = pd.NA
        for col in BASE_COLUMNS:
            if col in {"TckrSymb"}:
                continue
            if not _present(merged.get(col)) and _present(fetched.get(col)):
                merged[col] = fetched.get(col)
        if provider_owned and any(_present(fetched.get(c)) for c in METRIC_COLUMNS):
            # No manual metric values exist, so period/source fields describe the provider data
            # as one unit and must replace stale UNVERIFIED defaults from earlier runs.
            for col in ("MetricPeriodAlignmentStatus", "FinancialPeriodEnd", "Source", "SourceURL", "DataRetrievedAtUTC", "ProviderSector"):
                if _present(fetched.get(col)):
                    merged[col] = fetched.get(col)
        if not _present(merged.get("AsOfDate")) and cutoff_text:
            merged["AsOfDate"] = cutoff_text
        if not _present(merged.get("DataRetrievedAtUTC")):
            merged["DataRetrievedAtUTC"] = datetime.now(timezone.utc).isoformat()
        if not _present(merged.get("PublicationDateStatus")):
            merged["PublicationDateStatus"] = "UNVERIFIED"
        if not _present(merged.get("MetricPeriodAlignmentStatus")):
            merged["MetricPeriodAlignmentStatus"] = "UNVERIFIED"
        if not _present(merged.get("TckrSymb")):
            merged["TckrSymb"] = symbol
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
    if cutoff_text:
        blank_asof = combined["AsOfDate"].isna() | combined["AsOfDate"].astype(str).str.strip().isin(["", "nan", "None"])
        combined.loc[blank_asof, "AsOfDate"] = cutoff_text
    # Official date verification is a single batched request for the full universe.
    # Failure is non-fatal: candidates remain and statuses stay UNVERIFIED.
    try:
        from fundamental_official_filings import apply_official_publication_dates
        combined = apply_official_publication_dates(combined, cutoff_text or date.today().isoformat(), fetcher=filings_fetcher)
    except Exception as exc:
        combined["PublicationDateStatus"] = combined.get("PublicationDateStatus", pd.Series("UNVERIFIED", index=combined.index)).fillna("UNVERIFIED")
        combined["OfficialFilingVerificationError"] = f"{type(exc).__name__}: {exc}"[:300]
    combined.to_csv(path, index=False)
    snapshot_path = save_fundamental_history_snapshot(path, cutoff_text or date.today().isoformat())
    pd.DataFrame(diagnostics).to_csv(DIAGNOSTICS_PATH, index=False)
    print(f"[FUNDAMENTAL PROVIDER] Delivery A/B unique symbols={len(symbols)}; provider statuses={pd.Series([d.get('ProviderStatus') for d in diagnostics]).value_counts().to_dict()}; metrics cache={path}; history snapshot={snapshot_path}; diagnostics={DIAGNOSTICS_PATH}")
    return combined
