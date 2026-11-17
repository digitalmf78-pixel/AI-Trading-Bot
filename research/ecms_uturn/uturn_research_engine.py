"""Pure, auditable calculations for the ECMS U-Turn research hypothesis.

Research only: this module does not create orders, entries, exits or P&L.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from statistics import fmean
from typing import Iterable

@dataclass(frozen=True)
class UTurnValuation:
    status: str
    peak_high: float | None = None
    reference_pe: float | None = None
    expected_correction: float | None = None
    target: float | None = None
    zone_low: float | None = None
    zone_high: float | None = None
    reason: str = ""

def calculate_uturn(
    peak_high: float,
    previous_diluted_eps: float,
    current_diluted_eps: float,
    previous_fy: str,
    current_fy: str,
    previous_basis: str,
    current_basis: str,
    zone_pct: float = 0.02,
) -> UTurnValuation:
    values = (peak_high, previous_diluted_eps, current_diluted_eps, zone_pct)
    if not all(isfinite(float(x)) for x in values):
        return UTurnValuation("WAIT_FOR_DATA", reason="NON_FINITE_INPUT")
    if peak_high <= 0 or previous_diluted_eps <= 0 or current_diluted_eps <= 0:
        return UTurnValuation("WAIT_FOR_DATA", reason="NON_POSITIVE_PRICE_OR_EPS")
    if not previous_fy or not current_fy or previous_fy == current_fy:
        return UTurnValuation("WAIT_FOR_DATA", reason="INVALID_FY_PAIR")
    if not previous_basis or previous_basis.strip().upper() != current_basis.strip().upper():
        return UTurnValuation("WAIT_FOR_DATA", reason="REPORTING_BASIS_MISMATCH")
    if not 0 < zone_pct < 0.25:
        return UTurnValuation("WAIT_FOR_DATA", reason="INVALID_ZONE_TOLERANCE")
    if current_diluted_eps >= previous_diluted_eps:
        return UTurnValuation("NO_EPS_DECLINE", peak_high=peak_high, reason="CURRENT_EPS_NOT_LOWER")
    pe = peak_high / previous_diluted_eps
    correction = (previous_diluted_eps - current_diluted_eps) * pe
    target = peak_high - correction
    return UTurnValuation(
        "PROVISIONAL_TARGET",
        peak_high=peak_high,
        reference_pe=pe,
        expected_correction=correction,
        target=target,
        zone_low=target * (1 - zone_pct),
        zone_high=target * (1 + zone_pct),
    )

def zone_touched(day_low: float, day_high: float, zone_low: float, zone_high: float) -> bool:
    vals = (day_low, day_high, zone_low, zone_high)
    if not all(isfinite(float(x)) for x in vals):
        return False
    if day_low > day_high or zone_low > zone_high:
        return False
    return day_low <= zone_high and day_high >= zone_low

def relative_volume(current_volume: float, prior_completed_volumes: Iterable[float]) -> float | None:
    prior = [float(v) for v in prior_completed_volumes]
    if len(prior) != 20 or not all(isfinite(v) and v > 0 for v in prior):
        return None
    if not isfinite(float(current_volume)) or current_volume < 0:
        return None
    avg = fmean(prior)
    return float(current_volume) / avg if avg > 0 else None

def technical_confirmation(
    day_low: float,
    day_high: float,
    zone_low: float,
    zone_high: float,
    delivery_pct: float | None,
    rvol: float | None,
) -> str:
    if not zone_touched(day_low, day_high, zone_low, zone_high):
        return "NO_ZONE_TOUCH"
    if delivery_pct is None or rvol is None:
        return "WAIT_FOR_DATA"
    if not isfinite(float(delivery_pct)) or not isfinite(float(rvol)):
        return "WAIT_FOR_DATA"
    if delivery_pct >= 60.0 and rvol >= 1.5:
        return "TECHNICAL_CONFIRMATION_ONLY"
    return "ZONE_TOUCH_NOT_CONFIRMED"
