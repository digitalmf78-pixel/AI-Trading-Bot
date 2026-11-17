"""Pure, auditable calculations for the ECMS U-Turn research hypothesis.

Research only: no orders, entries, exits, or P&L.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from statistics import fmean
from typing import Iterable
import re

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

def _fy_year(value: str) -> int | None:
    if not isinstance(value,str): return None
    match=re.search(r"FY\s*['-]?(\d{2}|\d{4})",value.strip().upper())
    if not match: return None
    year=int(match.group(1))
    return year+2000 if year<100 else year

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
    try:
        values=(float(peak_high),float(previous_diluted_eps),float(current_diluted_eps),float(zone_pct))
    except (TypeError,ValueError):
        return UTurnValuation("WAIT_FOR_DATA",reason="NON_NUMERIC_INPUT")
    if not all(isfinite(x) for x in values):
        return UTurnValuation("WAIT_FOR_DATA",reason="NON_FINITE_INPUT")
    peak,prev_eps,curr_eps,zone=values
    if peak<=0 or prev_eps<=0 or curr_eps<=0:
        return UTurnValuation("WAIT_FOR_DATA",reason="NON_POSITIVE_PRICE_OR_EPS")
    py,cy=_fy_year(previous_fy),_fy_year(current_fy)
    if py is None or cy is None or cy!=py+1:
        return UTurnValuation("WAIT_FOR_DATA",reason="INVALID_OR_NON_CONSECUTIVE_FY_PAIR")
    if not isinstance(previous_basis,str) or not isinstance(current_basis,str) or not previous_basis.strip() or not current_basis.strip():
        return UTurnValuation("WAIT_FOR_DATA",reason="MISSING_REPORTING_BASIS")
    if previous_basis.strip().upper()!=current_basis.strip().upper():
        return UTurnValuation("WAIT_FOR_DATA",reason="REPORTING_BASIS_MISMATCH")
    if not 0<zone<0.25:
        return UTurnValuation("WAIT_FOR_DATA",reason="INVALID_ZONE_TOLERANCE")
    if curr_eps>=prev_eps:
        return UTurnValuation("NO_EPS_DECLINE",peak_high=peak,reason="CURRENT_EPS_NOT_LOWER")
    pe=peak/prev_eps
    correction=(prev_eps-curr_eps)*pe
    target=peak-correction
    return UTurnValuation("PROVISIONAL_TARGET",peak_high=peak,reference_pe=pe,expected_correction=correction,
        target=target,zone_low=target*(1-zone),zone_high=target*(1+zone))

def zone_touched(day_low: float, day_high: float, zone_low: float, zone_high: float) -> bool:
    try: vals=tuple(float(x) for x in (day_low,day_high,zone_low,zone_high))
    except (TypeError,ValueError): return False
    if not all(isfinite(x) for x in vals): return False
    low,high,zlow,zhigh=vals
    if low<=0 or zlow<=0 or low>high or zlow>zhigh: return False
    return low<=zhigh and high>=zlow

def relative_volume(current_volume: float, prior_completed_volumes: Iterable[float]) -> float | None:
    try:
        current=float(current_volume); prior=[float(v) for v in prior_completed_volumes]
    except (TypeError,ValueError): return None
    if len(prior)!=20 or not isfinite(current) or current<0 or not all(isfinite(v) and v>0 for v in prior):
        return None
    avg=fmean(prior)
    return current/avg if avg>0 else None

def technical_confirmation(day_low: float, day_high: float, zone_low: float, zone_high: float,
                          delivery_pct: float | None, rvol: float | None) -> str:
    if not zone_touched(day_low,day_high,zone_low,zone_high): return "NO_ZONE_TOUCH"
    if delivery_pct is None or rvol is None: return "WAIT_FOR_DATA"
    try: delivery=float(delivery_pct); relative=float(rvol)
    except (TypeError,ValueError): return "WAIT_FOR_DATA"
    if not isfinite(delivery) or not isfinite(relative) or not 0<=delivery<=100 or relative<0:
        return "WAIT_FOR_DATA"
    if delivery>=60.0 and relative>=1.5: return "TECHNICAL_CONFIRMATION_ONLY"
    return "ZONE_TOUCH_NOT_CONFIRMED"
