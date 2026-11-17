"""Format-aware NSE trading-session date normalization for cached bhavcopies."""
from __future__ import annotations

import re
import pandas as pd


def parse_nse_session_date(value):
    """Parse ISO UDiFF dates and legacy NSE DD/MM/YYYY-style dates safely."""
    if value is None or pd.isna(value):
        return pd.NaT
    raw = str(value).strip()
    if not raw or raw.lower() in {"nan", "nat", "none", "<na>"}:
        return pd.NaT

    # UDiFF TradDt is ISO. Preserve year-month-day rather than applying Indian
    # day-first parsing to an already unambiguous ISO value.
    if re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[ T])", raw):
        return pd.to_datetime(raw, errors="coerce")

    # Compact exchange dates are YYYYMMDD when they begin with a 19xx/20xx year;
    # otherwise interpret them as the legacy DDMMYYYY representation.
    if re.fullmatch(r"\d{8}", raw):
        fmt = "%Y%m%d" if raw.startswith(("19", "20")) else "%d%m%Y"
        return pd.to_datetime(raw, format=fmt, errors="coerce")

    # Legacy DATE1 / Date fields are day-first (e.g. 01/04/2026 = 1 April).
    return pd.to_datetime(raw, errors="coerce", dayfirst=True)


def normalize_session_dates(values):
    """Return a pandas string Series of normalized YYYY-MM-DD session dates."""
    parsed = values.map(parse_nse_session_date)
    return pd.to_datetime(parsed, errors="coerce").dt.date.astype("string")
