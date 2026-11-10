"""Descriptive VCP/contraction observations; never a VCP or entry gate.

The report measures three consecutive 20-session blocks (60 sessions total)
because 20 sessions is already an established V8 lookback. It records the
observed range/volume sequence only; it does not declare VCP_CONFIRMED.
"""
from __future__ import annotations

import math
from pathlib import Path
import pandas as pd
from history_index import build_price_history_index, candidate_price_history

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


def build_vcp_observation_report(candidates, historical, asof_date, output_path=None):
    """Report sequential 20-session price-range and volume observations."""
    if candidates is None or candidates.empty:
        return pd.DataFrame()
    asof = _day(asof_date)
    if asof is None:
        raise ValueError(f"Invalid as-of date: {asof_date!r}")

    history_index, ordered_dates = build_price_history_index(historical, asof)

    rows = []
    candidate_symbols = candidates["TckrSymb"].astype(str).str.strip().str.upper()
    candidate_counts = candidate_symbols.value_counts()
    for candidate_index, candidate in candidates.iterrows():
        symbol = str(candidate.get("TckrSymb", "")).strip().upper()
        if candidate_counts.get(symbol, 0) != 1:
            rows.append({
                "TckrSymb": symbol, "AsOfDate": asof.isoformat(),
                "VCPWindowSessions": min(len(ordered_dates), TOTAL_SESSIONS),
                "VCPAvailableSymbolSessions": 0,
                "VCPSymbolWindowRows": 0,
                "VCPSymbolWindowUniqueDates": 0,
                "VCPMissingSessionCount": min(len(ordered_dates), TOTAL_SESSIONS),
                "VCPDuplicateSessionCount": 0,
                "VCPMissingOHLCRowCount": 0,
                "VCPInvalidOHLCRowCount": 0,
                "VCPMissingVolumeRowCount": 0,
                "VCPInvalidVolumeRowCount": 0,
                "VCPRangeWaitReason": "AMBIGUOUS_DUPLICATE_CANDIDATE_SYMBOL",
                "VCPVolumeWaitReason": "AMBIGUOUS_DUPLICATE_CANDIDATE_SYMBOL",
                "VCPWaitReason": "AMBIGUOUS_DUPLICATE_CANDIDATE_SYMBOL",
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
            })
            continue
        hist = candidate_price_history(history_index, candidate, asof)

        window_dates = ordered_dates[-TOTAL_SESSIONS:]
        aligned = hist[hist["Date"].dt.date.isin(window_dates)].copy().sort_values("Date")
        aligned_dates = aligned["Date"].dt.date
        unique_dates = set(aligned_dates)
        missing_dates = set(window_dates) - unique_dates
        duplicate_dates = aligned_dates[aligned_dates.duplicated(keep=False)].nunique()
        ohlc_columns = ["HghPric", "LwPric", "ClsPric"]
        has_ohlc_columns = set(ohlc_columns).issubset(aligned.columns)
        missing_ohlc_rows = (
            int(aligned[ohlc_columns].isna().any(axis=1).sum())
            if has_ohlc_columns else len(aligned)
        )
        invalid_ohlc_rows = 0
        if has_ohlc_columns:
            for _, candle in aligned.iterrows():
                values = [_number(candle[column]) for column in ohlc_columns]
                if not all(math.isfinite(value) and value > 0 for value in values):
                    continue
                high, low, close = values
                if high < low or close < low or close > high:
                    invalid_ohlc_rows += 1
        if len(window_dates) != TOTAL_SESSIONS:
            range_wait_reason = "INSUFFICIENT_MARKET_SESSION_WINDOW"
        elif duplicate_dates:
            range_wait_reason = "DUPLICATE_SYMBOL_SESSION_ROWS"
        elif missing_dates:
            range_wait_reason = "MISSING_SYMBOL_SESSION_ROWS"
        elif not has_ohlc_columns:
            range_wait_reason = "MISSING_OHLC_COLUMNS"
        elif missing_ohlc_rows:
            range_wait_reason = "MISSING_OHLC_VALUES"
        elif invalid_ohlc_rows:
            range_wait_reason = "INVALID_OHLC_VALUES"
        else:
            range_wait_reason = "OK"
        complete_window = range_wait_reason == "OK"
        volume_missing_rows = (
            int(aligned["TtlTradgVol"].isna().sum())
            if "TtlTradgVol" in aligned.columns else len(aligned)
        )
        volume_invalid_rows = 0
        if "TtlTradgVol" in aligned.columns:
            for value in aligned["TtlTradgVol"].dropna():
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    volume_invalid_rows += 1
                    continue
                if not math.isfinite(number) or number < 0:
                    volume_invalid_rows += 1
        if not complete_window:
            volume_wait_reason = "RANGE_WINDOW_INCOMPLETE"
        elif "TtlTradgVol" not in aligned.columns:
            volume_wait_reason = "MISSING_VOLUME_COLUMN"
        elif volume_missing_rows:
            volume_wait_reason = "MISSING_VOLUME_VALUES"
        elif volume_invalid_rows:
            volume_wait_reason = "INVALID_VOLUME_VALUES"
        else:
            volume_wait_reason = "OK"
        row = {
            "TckrSymb": symbol, "AsOfDate": asof.isoformat(),
            "VCPWindowSessions": min(len(ordered_dates), TOTAL_SESSIONS),
            "VCPAvailableSymbolSessions": int(hist["Date"].dt.date.nunique()),
            "VCPSymbolWindowRows": int(len(aligned)),
            "VCPSymbolWindowUniqueDates": int(len(unique_dates)),
            "VCPMissingSessionCount": int(len(missing_dates)),
            "VCPDuplicateSessionCount": int(duplicate_dates),
            "VCPMissingOHLCRowCount": int(missing_ohlc_rows),
            "VCPInvalidOHLCRowCount": int(invalid_ohlc_rows),
            "VCPMissingVolumeRowCount": int(volume_missing_rows),
            "VCPInvalidVolumeRowCount": int(volume_invalid_rows),
            "VCPRangeWaitReason": range_wait_reason,
            "VCPVolumeWaitReason": volume_wait_reason,
            "VCPWaitReason": range_wait_reason if range_wait_reason != "OK" else volume_wait_reason,
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
            "RangeContractionDepth2vs1Pct": float("nan"),
            "RangeContractionDepth3vs2Pct": float("nan"),
            "PriceVolumeContractionRelationship": "WAIT_FOR_DATA",
            "FalseVCPOutcomeStatus": "NOT_EVALUATED_NO_APPROVED_FORWARD_HORIZON",
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
                row["RangeContractionDepth2vs1Pct"] = (1.0 - ratio21) * 100.0 if math.isfinite(ratio21) else float("nan")
                row["RangeContractionDepth3vs2Pct"] = (1.0 - ratio32) * 100.0 if math.isfinite(ratio32) else float("nan")
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
                and aligned["TtlTradgVol"].map(
                    lambda value: math.isfinite(float(value)) and float(value) >= 0
                ).all()
            )
            if volume_complete:
                row["VCPVolumeWaitReason"] = "OK"
                row["VCPWaitReason"] = "OK"
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
                price_contracted = (
                    math.isfinite(_number(row["RangeContractionRatio2vs1"]))
                    and math.isfinite(_number(row["RangeContractionRatio3vs2"]))
                    and row["RangeContractionRatio2vs1"] < 1
                    and row["RangeContractionRatio3vs2"] < 1
                )
                volume_contracted = (
                    math.isfinite(_number(row["VolumeRatioBlock2vs1"]))
                    and math.isfinite(_number(row["VolumeRatioBlock3vs2"]))
                    and row["VolumeRatioBlock2vs1"] < 1
                    and row["VolumeRatioBlock3vs2"] < 1
                )
                if price_contracted and volume_contracted:
                    row["PriceVolumeContractionRelationship"] = "PRICE_AND_VOLUME_BOTH_CONTRACTED"
                elif price_contracted:
                    row["PriceVolumeContractionRelationship"] = "PRICE_CONTRACTED_VOLUME_DID_NOT_CONTRACT_BOTH_STEPS"
                elif volume_contracted:
                    row["PriceVolumeContractionRelationship"] = "VOLUME_CONTRACTED_PRICE_DID_NOT_CONTRACT_BOTH_STEPS"
                else:
                    row["PriceVolumeContractionRelationship"] = "NO_TWO_STEP_JOINT_CONTRACTION_OBSERVED"
            else:
                row["VCPObservationStatus"] = "PARTIAL_DATA"
                row["VCPStatus"] = "WAIT_FOR_DATA"
                row["VCPWaitReason"] = row["VCPVolumeWaitReason"]
        rows.append(row)

    report = pd.DataFrame(rows)
    target_path = Path(output_path) if output_path is not None else OUTPUT_DIR / f"v8_vcp_contraction_observations_{asof:%Y%m%d}.csv"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(target_path, index=False)
    return report
