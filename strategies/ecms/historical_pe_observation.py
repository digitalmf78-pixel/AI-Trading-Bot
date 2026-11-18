"""Research-only historical PE valuation reference calculator.

This module calculates a valuation reference only. It does not identify support,
confirm a bottom/breakout, rank stocks, or emit trading instructions.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any, Iterable


def _positive_finite(value: Any) -> bool:
    # bool is a numeric subclass in Python (True == 1); never accept it as EPS/PE.
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return isfinite(number) and number > 0


def _percentile(values: list[float], percentile: float) -> float:
    """Linear-interpolated percentile (same convention as NumPy's default)."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def calculate_historical_pe_reference(
    observations: Iterable[dict[str, Any]],
    *,
    current_eps: Any,
    current_eps_basis: str,
    current_eps_period: str,
    current_eps_source: str,
    as_of_date: str,
    lower_percentile: float = 20.0,
    min_observations: int = 20,
) -> dict[str, Any]:
    """Return lower/median/upper historical-PE references or WAIT_FOR_DATA.

    This research prototype accepts only TTM diluted EPS and historical
    point-in-time PE observations. Current provider snapshots are not historical
    observations and must be rejected, even when their quote dates are populated.
    """
    def wait(reason: str) -> dict[str, Any]:
        return {"status": "WAIT_FOR_DATA", "reason": reason}

    if not _positive_finite(current_eps):
        return wait("CURRENT_EPS_NOT_POSITIVE_FINITE")
    if not all(isinstance(value, str) and value.strip() for value in (
        current_eps_basis, current_eps_period, current_eps_source, as_of_date
    )):
        return wait("CURRENT_EPS_PROVENANCE_MISSING")
    if current_eps_basis != "TTM_DILUTED":
        return wait("CURRENT_EPS_BASIS_NOT_TTM_DILUTED")
    try:
        cutoff = date.fromisoformat(as_of_date)
    except ValueError:
        return wait("AS_OF_DATE_INVALID")
    if isinstance(lower_percentile, bool):
        return wait("LOWER_PERCENTILE_OUT_OF_RANGE")
    try:
        percentile = float(lower_percentile)
    except (TypeError, ValueError, OverflowError):
        return wait("LOWER_PERCENTILE_OUT_OF_RANGE")
    if not isfinite(percentile) or not 0 < percentile < 50:
        return wait("LOWER_PERCENTILE_OUT_OF_RANGE")
    if not isinstance(min_observations, int) or isinstance(min_observations, bool) or min_observations < 2:
        return wait("MIN_OBSERVATIONS_INVALID")

    rows = list(observations)
    if len(rows) < min_observations:
        return wait("INSUFFICIENT_HISTORICAL_OBSERVATIONS")

    pes: list[float] = []
    seen_dates: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or any(
            field not in row or not isinstance(row[field], str) or not row[field].strip()
            for field in (
                "price_date", "eps_period", "eps_basis", "source",
                "point_in_time_status",
            )
        ):
            return wait("HISTORICAL_PROVENANCE_MISSING")
        if row["point_in_time_status"] != "HISTORICAL_POINT_IN_TIME_VERIFIED":
            return wait("HISTORICAL_POINT_IN_TIME_NOT_VERIFIED")
        if not _positive_finite(row.get("pe")):
            return wait("HISTORICAL_PE_NOT_POSITIVE_FINITE")
        if row["eps_basis"] != current_eps_basis:
            return wait("EPS_BASIS_MISMATCH")
        try:
            observation_date = date.fromisoformat(row["price_date"])
        except ValueError:
            return wait("HISTORICAL_PRICE_DATE_INVALID")
        if observation_date > cutoff:
            return wait("FUTURE_HISTORICAL_OBSERVATION")
        if row["price_date"] in seen_dates:
            return wait("DUPLICATE_HISTORICAL_PRICE_DATE")
        seen_dates.add(row["price_date"])
        pes.append(float(row["pe"]))

    lower_pe = _percentile(pes, percentile)
    median_pe = _percentile(pes, 50.0)
    upper_pe = _percentile(pes, 75.0)
    eps = float(current_eps)
    return {
        "status": "HISTORICAL_VALUATION_REFERENCE",
        "warning": "NOT_SUPPORT_NOT_FLOOR_NOT_TRADING_SIGNAL",
        "lower_percentile": percentile,
        "historical_pe_lower_band": lower_pe,
        "historical_pe_median": median_pe,
        "historical_pe_upper_band_p75": upper_pe,
        "current_eps": eps,
        "current_eps_basis": current_eps_basis,
        "current_eps_period": current_eps_period,
        "current_eps_source": current_eps_source,
        "valuation_reference_price": lower_pe * eps,
        "observation_count": len(pes),
        "as_of_date": as_of_date,
        "technical_status": "NOT_ASSESSED",
    }
