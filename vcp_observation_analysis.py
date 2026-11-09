"""Descriptive VCP/contraction observations; never a VCP or entry gate.

The report measures three consecutive 20-session blocks (60 sessions total)
because 20 sessions is already an established V8 lookback. It records the
observed range/volume sequence only; it does not declare VCP_CONFIRMED.
"""
from __future__ import annotations

import math
from pathlib import Path
import pandas as pd

OUTPUT_DIR = Path("outputs")
BLOCK_SESSIONS = 20
BLOCK_COUNT = 3
TOTAL_SESSIONS = BLOCK_SESSIONS * BLOCK_COUNT
VOLUME_DRY_UP_OBSERVATION_RATIO = 0.5


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _day(value):
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def build_vcp_observation_report(candidates, historical, asof_date):
    """Report sequential 20-session price-range and volume observations."""
    if candidates is None or candidates.empty:
        return pd.DataFrame()
    asof = _day(asof_date)
    if asof is None:
        raise ValueError(f"Invalid as-of date: {asof_date!r}")

    market_dates = set()
    for raw in historical or []:
        if raw is None or raw.empty or "Date" not in raw.columns:
            continue
        for value in pd.to_datetime(raw["Date"], errors="coerce").dropna():
            if value.date() <= asof:
                market_dates.add(value.date())
    market_dates.add(asof)
    ordered_dates = sorted(market_dates)

    rows = []
    for _, candidate in candidates.drop_duplicates("TckrSymb", keep="first").iterrows():
        symbol = str(candidate.get("TckrSymb", "")).strip().upper()
        series = str(candidate.get("SctySrs", "EQ")).strip().upper() or "EQ"
        frames = []
        for raw in historical or []:
            if raw is None or raw.empty or "TckrSymb" not in raw.columns or "Date" not in raw.columns:
                continue
            raw_dates = pd.to_datetime(raw["Date"], errors="coerce")
            part = raw[
                raw["TckrSymb"].astype(str).str.strip().str.upper().eq(symbol)
                & raw_dates.dt.date.le(asof)
            ].copy()
            if "SctySrs" in part.columns:
                part = part[part["SctySrs"].astype(str).str.strip().str.upper().eq(series)]
            if not part.empty:
                frames.append(part)
        hist = (
            pd.concat(frames, ignore_index=True, sort=False)
            if frames else pd.DataFrame(columns=["TckrSymb", "SctySrs", "Date"])
        )
        hist["Date"] = pd.to_datetime(hist["Date"], errors="coerce")
        hist = hist.dropna(subset=["Date"])
        hist = hist[hist["Date"].dt.date <= asof]
        current = candidate.to_dict()
        current.update({"TckrSymb": symbol, "SctySrs": series, "Date": pd.Timestamp(asof)})
        existing_current = hist[hist["Date"].dt.date.eq(asof)]
        if len(existing_current) == 1:
            base = existing_current.iloc[0].to_dict()
            for key, value in current.items():
                if value is not None and not pd.isna(value):
                    base[key] = value
            hist = hist[~hist.index.isin(existing_current.index)]
            hist = pd.concat([hist, pd.DataFrame([base])], ignore_index=True, sort=False)
        elif len(existing_current) == 0:
            hist = pd.concat([hist, pd.DataFrame([current])], ignore_index=True, sort=False)
        # Preserve multiple cached rows for this date as an ambiguous session.
        hist = hist.sort_values("Date", kind="mergesort")
        # Do not collapse duplicate symbol/session rows: they are ambiguous
        # source data and must fail the exact-window completeness check.
        for column in ("HghPric", "LwPric", "ClsPric", "TtlTradgVol"):
            if column in hist.columns:
                hist[column] = pd.to_numeric(hist[column], errors="coerce")

        window_dates = ordered_dates[-TOTAL_SESSIONS:]
        aligned = hist[hist["Date"].dt.date.isin(window_dates)].copy().sort_values("Date")
        complete_window = (
            len(window_dates) == TOTAL_SESSIONS
            and len(aligned) == TOTAL_SESSIONS
            and aligned["Date"].dt.date.nunique() == TOTAL_SESSIONS
            and set(aligned["Date"].dt.date) == set(window_dates)
            and {"HghPric", "LwPric", "ClsPric"}.issubset(aligned.columns)
            and aligned[["HghPric", "LwPric", "ClsPric"]].notna().all().all()
        )
        row = {
            "TckrSymb": symbol, "AsOfDate": asof.isoformat(),
            "VCPWindowSessions": min(len(ordered_dates), TOTAL_SESSIONS),
            "VCPRangeObservationStatus": "WAIT_FOR_DATA",
            "VCPVolumeObservationStatus": "WAIT_FOR_DATA",
            "VCPObservationStatus": "WAIT_FOR_DATA",
            "ContractionSequenceObservation": "WAIT_FOR_DATA",
            "ContractionTransitionsObserved": float("nan"),
            "RangeWidthBlock1Pct": float("nan"),
            "RangeWidthBlock2Pct": float("nan"),
            "RangeWidthBlock3Pct": float("nan"),
            "RangeContractionRatio2vs1": float("nan"),
            "RangeContractionRatio3vs2": float("nan"),
            "VolumeAverageBlock1": float("nan"),
            "VolumeAverageBlock2": float("nan"),
            "VolumeAverageBlock3": float("nan"),
            "VolumeRatioBlock2vs1": float("nan"),
            "VolumeRatioBlock3vs2": float("nan"),
            "VolumeDryUpRatio3vs2": float("nan"),
            "VolumeDryUpFlag": "WAIT_FOR_DATA",
            "VCPStatus": "WAIT_FOR_DATA",
        }
        if complete_window:
            row["VCPRangeObservationStatus"] = "COMPLETE"
            blocks = [
                aligned.tail(TOTAL_SESSIONS).iloc[i*BLOCK_SESSIONS:(i+1)*BLOCK_SESSIONS]
                for i in range(BLOCK_COUNT)
            ]
            widths = []
            for index, block in enumerate(blocks, start=1):
                high = _number(block["HghPric"].max())
                low = _number(block["LwPric"].min())
                width = (high / low - 1.0) * 100.0 if low > 0 else float("nan")
                widths.append(width)
                row[f"RangeWidthBlock{index}Pct"] = width
            if all(math.isfinite(value) for value in widths):
                ratio21 = widths[1] / widths[0] if widths[0] > 0 else float("nan")
                ratio32 = widths[2] / widths[1] if widths[1] > 0 else float("nan")
                row["RangeContractionRatio2vs1"] = ratio21
                row["RangeContractionRatio3vs2"] = ratio32
                transitions = int(widths[1] < widths[0]) + int(widths[2] < widths[1])
                row["ContractionTransitionsObserved"] = transitions
                row["ContractionSequenceObservation"] = (
                    "TWO_CONTRACTION_STEPS_OBSERVED" if transitions == 2 else
                    "ONE_CONTRACTION_STEP_OBSERVED" if transitions == 1 else
                    "NO_CONTRACTION_STEP_OBSERVED"
                )

            volume_complete = (
                "TtlTradgVol" in aligned.columns
                and aligned["TtlTradgVol"].notna().all()
                and (aligned["TtlTradgVol"] >= 0).all()
            )
            if volume_complete:
                row["VCPVolumeObservationStatus"] = "COMPLETE"
                volume_averages = [float(block["TtlTradgVol"].mean()) for block in blocks]
                for index, value in enumerate(volume_averages, start=1):
                    row[f"VolumeAverageBlock{index}"] = value
                row["VolumeRatioBlock2vs1"] = volume_averages[1] / volume_averages[0] if volume_averages[0] > 0 else float("nan")
                row["VolumeRatioBlock3vs2"] = volume_averages[2] / volume_averages[1] if volume_averages[1] > 0 else float("nan")
                row["VolumeDryUpRatio3vs2"] = row["VolumeRatioBlock3vs2"]
                ratio = row["VolumeDryUpRatio3vs2"]
                row["VolumeDryUpFlag"] = (
                    "OBSERVATIONAL_BELOW_0_5X"
                    if pd.notna(ratio) and ratio < VOLUME_DRY_UP_OBSERVATION_RATIO
                    else "NO_SUB_0_5X_FLAG" if pd.notna(ratio) else "WAIT_FOR_DATA"
                )
            if row["VCPRangeObservationStatus"] == "COMPLETE" and row["VCPVolumeObservationStatus"] == "COMPLETE":
                row["VCPObservationStatus"] = "COMPLETE"
                row["VCPStatus"] = "NOT_CLASSIFIED"
            else:
                row["VCPObservationStatus"] = "PARTIAL_DATA"
                row["VCPStatus"] = "WAIT_FOR_DATA"
        rows.append(row)

    report = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report.to_csv(OUTPUT_DIR / f"v8_vcp_contraction_observations_{asof:%Y%m%d}.csv", index=False)
    return report
