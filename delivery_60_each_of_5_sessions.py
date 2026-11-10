"""Strict five-session NSE Delivery-only shortlist for eligible Main Board stocks."""
from __future__ import annotations

import pandas as pd
from main_board_filter import apply_main_board_filter

REQUIRED_SESSIONS = 5
MIN_DELIVERY_INCLUSIVE = 60.0
AUDIT_COLUMNS = [
    "SYMBOL",
    "ASOF_DATE",
    "SESSION_1_DATE", "SESSION_1_DELIVERY_PCT",
    "SESSION_2_DATE", "SESSION_2_DELIVERY_PCT",
    "SESSION_3_DATE", "SESSION_3_DELIVERY_PCT",
    "SESSION_4_DATE", "SESSION_4_DELIVERY_PCT",
    "SESSION_5_DATE", "SESSION_5_DELIVERY_PCT",
    "MIN_DELIVERY_5D",
    "PASS_ALL_5D_GE_60",
]


def filter_five_session_delivery(
    sessions: list[tuple[object, pd.DataFrame]],
    eligible_symbols_by_date: dict | None = None,
    minimum_delivery: float = MIN_DELIVERY_INCLUSIVE,
) -> tuple[list[str], pd.DataFrame, dict]:
    """Return symbols with at least the threshold on each of five distinct EQ sessions.

    eligible_symbols_by_date is the independently validated official NSE stock
    universe for each session. It adds no technical or fundamental criteria; it
    prevents ETFs, mutual-fund units, SMEs, and unverified board classifications
    from entering a stock-only Delivery list.
    """
    if len(sessions) != REQUIRED_SESSIONS:
        raise ValueError(f"Exactly {REQUIRED_SESSIONS} valid sessions are required; got {len(sessions)}")
    normalized = sorted(
        [(pd.Timestamp(day).date(), frame.copy()) for day, frame in sessions],
        key=lambda item: item[0],
    )
    dates = [day for day, _ in normalized]
    if len(set(dates)) != REQUIRED_SESSIONS:
        raise ValueError("Five distinct session dates are required")
    if not 0 <= float(minimum_delivery) <= 100:
        raise ValueError("minimum_delivery must be between 0 and 100")

    eligible_lookup = None
    if eligible_symbols_by_date is not None:
        eligible_lookup = {
            pd.Timestamp(day).date(): {str(symbol).strip().upper() for symbol in symbols}
            for day, symbols in eligible_symbols_by_date.items()
        }

    daily_maps: list[dict[str, float]] = []
    daily_valid_counts: list[int] = []
    for day, raw in normalized:
        frame = raw.copy()
        frame.columns = [str(column).strip().upper().replace(" ", "_") for column in frame.columns]
        required = {"SYMBOL", "SERIES", "DELIV_PER"}
        if not required.issubset(frame.columns):
            raise ValueError(f"{day}: delivery report missing columns {sorted(required - set(frame.columns))}")
        frame["SYMBOL"] = frame["SYMBOL"].astype(str).str.strip().str.upper()
        frame["SERIES"] = frame["SERIES"].astype(str).str.strip().str.upper()
        frame["DELIV_PER"] = pd.to_numeric(frame["DELIV_PER"], errors="coerce")
        frame = frame[
            frame["SERIES"].eq("EQ") & frame["DELIV_PER"].between(0, 100)
        ].copy()

        counts = frame.groupby("SYMBOL").size()
        ambiguous = set(counts[counts != 1].index)
        if ambiguous:
            frame = frame.loc[~frame["SYMBOL"].isin(ambiguous)].copy()

        if eligible_lookup is not None:
            if day not in eligible_lookup:
                raise ValueError(f"{day}: official stock-universe classification is missing")
            frame = frame.loc[frame["SYMBOL"].isin(eligible_lookup[day])].copy()

        daily_map = frame.set_index("SYMBOL")["DELIV_PER"].astype(float).to_dict()
        daily_maps.append(daily_map)
        daily_valid_counts.append(len(daily_map))

    common_symbols = set(daily_maps[0])
    union_symbols = set(daily_maps[0])
    for day_map in daily_maps[1:]:
        common_symbols.intersection_update(day_map)
        union_symbols.update(day_map)

    qualifying = sorted(
        symbol for symbol in common_symbols
        if all(day_map[symbol] >= float(minimum_delivery) for day_map in daily_maps)
    )
    audit_rows = []
    asof = dates[-1].isoformat()
    for symbol in qualifying:
        row = {"SYMBOL": symbol, "ASOF_DATE": asof}
        daily_values = []
        for index, ((day, _), day_map) in enumerate(zip(normalized, daily_maps), start=1):
            value = float(day_map[symbol])
            daily_values.append(value)
            row[f"SESSION_{index}_DATE"] = day.isoformat()
            row[f"SESSION_{index}_DELIVERY_PCT"] = value
        row["MIN_DELIVERY_5D"] = min(daily_values)
        row["PASS_ALL_5D_GE_60"] = all(value >= float(minimum_delivery) for value in daily_values)
        audit_rows.append(row)

    summary = {
        "session_dates": [day.isoformat() for day in dates],
        "valid_eq_symbols_by_session": daily_valid_counts,
        "common_symbols": len(common_symbols),
        "symbols_missing_any_session": len(union_symbols - common_symbols),
        "qualifying_symbols": len(qualifying),
    }
    return qualifying, pd.DataFrame(audit_rows, columns=AUDIT_COLUMNS), summary


def eligible_mainboard_eq_symbols(
    bhavcopy: pd.DataFrame,
    main_board_symbols: set[str],
    sme_symbols: set[str],
    official_etf_symbols: set[str] | None = None,
    source_status: str = "OFFICIAL_NSE_LISTS",
) -> tuple[set[str], dict]:
    """Apply V8's official EQ stock-universe checks to one dated Bhavcopy.

    This is universe classification only: EQ series, valid Bhavcopy price/volume,
    ETF/MF exclusion, and official Main Board membership. It applies no trading
    or technical signal filters.
    """
    required = {"TckrSymb", "SctySrs", "ClsPric", "TtlTradgVol", "ISIN"}
    missing = required - set(bhavcopy.columns)
    if missing:
        raise ValueError(f"Bhavcopy is missing required stock-universe fields: {sorted(missing)}")

    frame = bhavcopy.copy()
    frame["TckrSymb"] = frame["TckrSymb"].astype(str).str.strip().str.upper()
    frame["SctySrs"] = frame["SctySrs"].astype(str).str.strip().str.upper()
    frame["ClsPric"] = pd.to_numeric(frame["ClsPric"], errors="coerce")
    frame["TtlTradgVol"] = pd.to_numeric(frame["TtlTradgVol"], errors="coerce")
    frame = frame[
        frame["SctySrs"].eq("EQ")
        & frame["ClsPric"].gt(0)
        & frame["TtlTradgVol"].ge(0)
        & frame["TckrSymb"].ne("")
        & frame["TckrSymb"].ne("NAN")
    ].copy()
    input_eq_rows = len(frame)

    etf_set = {str(symbol).strip().upper() for symbol in (official_etf_symbols or set())}
    if not etf_set and "FinInstrmNm" not in frame.columns:
        raise ValueError("Official ETF list and Bhavcopy instrument-name fallback are both unavailable")
    etf_mask = frame["TckrSymb"].isin(etf_set)
    etf_mask |= frame["ISIN"].fillna("").astype(str).str.strip().str.upper().str.startswith("INF")
    if "FinInstrmNm" in frame.columns:
        instrument_name = frame["FinInstrmNm"].fillna("").astype(str)
        etf_mask |= instrument_name.str.contains(
            r"\bAMC\s*-\s*", case=False, regex=True, na=False
        )
        etf_mask |= instrument_name.str.contains(
            r"\b(ETF|EXCHANGE TRADED FUND|MUTUAL FUND)\b",
            case=False, regex=True, na=False,
        )
    excluded_etf_mf = set(frame.loc[etf_mask, "TckrSymb"])
    frame = frame.loc[~etf_mask].copy()

    counts = frame.groupby("TckrSymb").size()
    ambiguous = set(counts[counts != 1].index)
    if ambiguous:
        frame = frame.loc[~frame["TckrSymb"].isin(ambiguous)].copy()

    board_frame, board_audit = apply_main_board_filter(
        frame,
        main_board_symbols,
        sme_symbols,
        source_status=source_status,
    )
    eligible = set(board_frame["TckrSymb"].astype(str).str.strip().str.upper())
    board_counts = board_audit["MainBoardStatus"].value_counts().to_dict()
    summary = {
        "input_eq_rows": input_eq_rows,
        "excluded_etf_mf_symbols": len(excluded_etf_mf),
        "ambiguous_symbols": len(ambiguous),
        "main_board_eligible_symbols": len(eligible),
        "excluded_sme_symbols": int(board_counts.get("EXCLUDED_SME", 0)),
        "excluded_unverified_symbols": int(board_counts.get("EXCLUDED_UNVERIFIED_CLASSIFICATION", 0)),
    }
    return eligible, summary
