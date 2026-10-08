"""Conservative, input-driven V8 layers 14–41.

The exchange EOD feed alone cannot supply sector membership, verified news,
intraday bars, or a user's open positions. Those inputs are read from CSV files
under data/inputs. Missing data is reported as WAIT_FOR_DATA; this module never
places orders or turns a score into an automatic buy/sell instruction.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
import math
import re
from urllib.parse import urlparse

import pandas as pd


INPUT_DIR = Path("data") / "inputs"
OUTPUT_DIR = Path("outputs")

NEWS_COLUMNS = [
    "TckrSymb", "PublishedAt", "Headline", "Source", "SourceType",
    "URL", "Impact", "EventID",
]
SECTOR_MAP_COLUMNS = ["TckrSymb", "Sector", "SectorIndexSymbol"]
SECTOR_HISTORY_COLUMNS = ["Date", "Sector", "Close"]
INTRADAY_COLUMNS = [
    "Symbol", "Datetime", "Open", "High", "Low", "Close", "Volume",
]
POSITION_COLUMNS = [
    "TckrSymb", "Quantity", "AverageEntryPrice", "InitialStop", "Target",
    "EntryDate", "Thesis",
]
POSITION_REPORT_COLUMNS = [
    "TckrSymb", "AsOfDate", "Quantity", "AverageEntryPrice",
    "CurrentPrice", "UnrealizedPnLPct", "ThesisStatus",
    "NewsEvidenceStatus", "NegativePrimaryNews", "SellingPressure",
    "SellingPressureStatus",
    "TargetStatus", "TrailingStop", "PositionAction", "DecisionMode",
    "Reason",
]
NEXT_DAY_REPORT_COLUMNS = [
    "TckrSymb", "SessionDate", "OvernightNewsStatus", "GapPct",
    "GapClassification", "OpeningPriceAction", "OpeningHigh15m",
    "OpeningLow15m", "VWAP", "VWAPStatus", "OpeningRVOL",
    "OpeningRVOLStatus", "RSI14Intraday", "RSIStatus",
    "NiftyConfirmation", "SectorConfirmation", "IndexConfirmation",
    "BreakoutConfirmation",
    "NextDayStatus", "NextDayReason",
]


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_csv(path)
    except Exception as exc:
        print(f"Input could not be read ({path}): {exc}")
        return pd.DataFrame(columns=columns)


def create_input_templates() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    templates = {
        "sector_map.csv": SECTOR_MAP_COLUMNS,
        "sector_history.csv": SECTOR_HISTORY_COLUMNS,
        "news_evidence.csv": NEWS_COLUMNS,
        "intraday_bars.csv": INTRADAY_COLUMNS,
        "positions.csv": POSITION_COLUMNS,
    }
    for filename, columns in templates.items():
        path = INPUT_DIR / filename
        if not path.exists():
            pd.DataFrame(columns=columns).to_csv(path, index=False)


def _num(value) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _first_number(row: pd.Series, names: list[str]) -> float:
    for name in names:
        if name in row.index:
            value = _num(row[name])
            if pd.notna(value):
                return value
    return float("nan")


def _domain(row: pd.Series) -> str:
    url = _text(row.get("URL", ""))
    source = _text(row.get("Source", "")).lower()
    host = urlparse(url).netloc.lower().removeprefix("www.") if url else ""
    return host or re.sub(r"\s+", " ", source)


def _is_primary(row: pd.Series) -> bool:
    kind = _text(row.get("SourceType", "")).lower()
    return kind in {"primary", "official", "exchange", "regulator", "company"}


def _headline_key(value) -> str:
    text = _text(value).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _event_groups(rows: pd.DataFrame) -> list[list[pd.Series]]:
    groups: list[list[pd.Series]] = []
    for _, row in rows.iterrows():
        event_id = _text(row.get("EventID", "")).lower()
        key = event_id or _headline_key(row.get("Headline", ""))
        if not key:
            continue
        placed = False
        for group in groups:
            first = group[0]
            first_id = _text(first.get("EventID", "")).lower()
            first_key = first_id or _headline_key(first.get("Headline", ""))
            if key == first_key or (
                not event_id
                and not first_id
                and SequenceMatcher(None, key, first_key).ratio() >= 0.84
            ):
                group.append(row)
                placed = True
                break
        if not placed:
            groups.append([row])
    return groups


def _news_for_symbol(
    news: pd.DataFrame,
    symbol: str,
    asof,
    start=None,
) -> dict:
    result = {
        "NewsEvidenceStatus": "NO_DATA",
        "NewsIndependentSources": 0,
        "NewsPrimarySources": 0,
        "NewsNegativePrimary": False,
        "NewsCatalyst": "",
    }
    if news.empty or "TckrSymb" not in news.columns:
        return result

    rows = news[
        news["TckrSymb"].astype(str).str.upper().eq(str(symbol).upper())
    ].copy()
    if rows.empty or "PublishedAt" not in rows.columns:
        return result
    rows["_date"] = pd.to_datetime(rows["PublishedAt"], errors="coerce", utc=True)
    asof_ts = pd.Timestamp(asof)
    if asof_ts.tzinfo is None:
        asof_ts = asof_ts.tz_localize("Asia/Kolkata")
    else:
        asof_ts = asof_ts.tz_convert("UTC")
    start_ts = pd.Timestamp(start) if start is not None else asof_ts - pd.Timedelta(days=5)
    if start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize("Asia/Kolkata")
    else:
        start_ts = start_ts.tz_convert("UTC")
    rows = rows[rows["_date"].between(start_ts, asof_ts, inclusive="both")]
    if rows.empty:
        return result

    groups = _event_groups(rows)
    best_secondary = 0
    best_primary = 0
    catalyst = ""
    for group in groups:
        primary_domains = {
            _domain(item) for item in group
            if _domain(item) and _is_primary(item)
        }
        secondary_domains = {
            _domain(item) for item in group
            if _domain(item) and not _is_primary(item)
        } - primary_domains
        if len(secondary_domains) + len(primary_domains) > best_secondary + best_primary:
            best_secondary = len(secondary_domains)
            best_primary = len(primary_domains)
            catalyst = _text(group[0].get("Headline", ""))

    negative_primary = any(
        _is_primary(row)
        and str(row.get("Impact", "")).strip().lower() in {"negative", "adverse"}
        for _, row in rows.iterrows()
    )
    confirmed = any(
        len(
            {
                _domain(item) for item in group
                if _domain(item) and not _is_primary(item)
            }
            - {
                _domain(item) for item in group
                if _domain(item) and _is_primary(item)
            }
        ) >= 3
        and len(
            {
                _domain(item) for item in group
                if _domain(item) and _is_primary(item)
            }
        ) >= 1
        for group in groups
    )
    status = "CONFIRMED_3_PLUS_1" if confirmed else "UNVERIFIED"
    if negative_primary:
        status = "NEGATIVE_PRIMARY_NEWS"
    return {
        "NewsEvidenceStatus": status,
        "NewsIndependentSources": best_secondary,
        "NewsPrimarySources": best_primary,
        "NewsNegativePrimary": negative_primary,
        "NewsCatalyst": catalyst,
    }


def _sector_strength(
    result: pd.DataFrame,
    sector_map: pd.DataFrame,
    sector_history: pd.DataFrame,
    asof,
) -> pd.DataFrame:
    mapping = {}
    if {"TckrSymb", "Sector"}.issubset(sector_map.columns):
        mapping = {
            str(row["TckrSymb"]).upper(): row
            for _, row in sector_map.iterrows()
        }
    history = sector_history.copy()
    if {"Date", "Sector", "Close"}.issubset(history.columns):
        history["Date"] = pd.to_datetime(history["Date"], errors="coerce")
        history["Close"] = pd.to_numeric(history["Close"], errors="coerce")
        history = history.dropna(subset=["Date", "Sector", "Close"])
    else:
        history = pd.DataFrame(columns=SECTOR_HISTORY_COLUMNS)

    rows = []
    for _, row in result.iterrows():
        symbol = str(row.get("TckrSymb", "")).upper()
        map_row = mapping.get(symbol)
        sector = str(map_row.get("Sector", "")).strip() if map_row is not None else ""
        sector_frame = history[history["Sector"].astype(str).str.casefold().eq(sector.casefold())].copy()
        sector_frame = sector_frame[sector_frame["Date"] <= pd.Timestamp(asof)].sort_values("Date")
        sector_return = float("nan")
        if len(sector_frame) >= 21 and sector_frame.iloc[-1]["Date"].normalize() == pd.Timestamp(asof).normalize():
            base = _num(sector_frame.iloc[-21]["Close"])
            close = _num(sector_frame.iloc[-1]["Close"])
            if pd.notna(base) and base > 0 and pd.notna(close):
                sector_return = (close / base - 1) * 100
        nifty_return = _num(row.get("NiftyReturn20D"))
        relative = sector_return - nifty_return if pd.notna(sector_return) and pd.notna(nifty_return) else float("nan")
        if pd.isna(relative):
            classification, status = "Insufficient Data", "WAIT_FOR_DATA"
        elif relative >= 2:
            classification, status = "Sector Outperforming", "PASS"
        elif relative > -2:
            classification, status = "Sector Market Aligned", "PASS"
        else:
            classification, status = "Sector Underperforming", "FAIL"
        rows.append({
            "TckrSymb": symbol,
            "Sector": sector or "Unknown",
            "SectorReturn20D": sector_return,
            "SectorStrengthNifty": relative,
            "SectorStrengthClassification": classification,
            "SectorStrengthStatus": status,
        })
    return pd.DataFrame(rows)


def _market_regime(nifty_history: pd.DataFrame, asof) -> str:
    if not {"Date", "NiftyClose"}.issubset(nifty_history.columns):
        return "WAIT_FOR_DATA"
    frame = nifty_history.copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["NiftyClose"] = pd.to_numeric(frame["NiftyClose"], errors="coerce")
    frame = frame.dropna(subset=["Date", "NiftyClose"])
    frame = frame[frame["Date"] <= pd.Timestamp(asof)].sort_values("Date")
    if len(frame) < 50 or frame.iloc[-1]["Date"].normalize() != pd.Timestamp(asof).normalize():
        return "WAIT_FOR_DATA"
    close = frame["NiftyClose"]
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
    prior_ema20 = close.ewm(span=20, adjust=False).mean().iloc[-6]
    last = close.iloc[-1]
    if last > ema20 > ema50 and ema20 > prior_ema20:
        return "RISK_ON"
    if last < ema20 < ema50 and ema20 < prior_ema20:
        return "RISK_OFF"
    return "MIXED"


def _delivery_pct(row: pd.Series) -> float:
    explicit = _first_number(row, ["DlvryPer", "DlvryPct", "DeliveryPct", "DeliverablePct", "DlvryToTradedQtyPer"])
    if pd.notna(explicit):
        return explicit
    delivered = _first_number(row, ["TtlDlvryQnty", "TtlDlvryQty", "DlvryQty", "DeliveryQty", "DeliverableQty"])
    traded = _first_number(row, ["TtlTradgVol", "TotalTradedQty", "Volume"])
    if pd.notna(delivered) and pd.notna(traded) and traded > 0:
        return 100 * delivered / traded
    return float("nan")


def _accumulation_score(frame: pd.DataFrame) -> float:
    if frame is None or len(frame) < 10:
        return float("nan")
    values = []
    for _, row in frame.tail(20).iterrows():
        high, low = _num(row.get("HghPric")), _num(row.get("LwPric"))
        close, volume = _num(row.get("ClsPric")), _num(row.get("TtlTradgVol"))
        if pd.isna(high) or pd.isna(low) or pd.isna(close) or pd.isna(volume) or high <= low:
            continue
        values.append((((2 * close) - high - low) / (high - low)) * volume)
    if not values:
        return float("nan")
    return sum(values) / max(sum(abs(value) for value in values), 1.0)


def _score_row(row: pd.Series) -> tuple[int, int]:
    score = 0
    available = 0
    weights = {
        "trend": 15, "rs": 15, "sector": 10, "market": 10,
        "rvol": 10, "volume": 10, "clv": 10, "setup": 10,
        "delivery": 5, "ad": 5,
    }
    trend = str(row.get("TrendClassification", ""))
    if trend not in {"", "Insufficient Data", "nan"}:
        available += weights["trend"]
        if "Bullish" in trend:
            score += weights["trend"]
        elif "Improving" in trend:
            score += 8
    rs = _num(row.get("RelativeStrengthNifty"))
    if pd.notna(rs):
        available += weights["rs"]
        score += weights["rs"] if rs >= 5 else 11 if rs >= 2 else 7 if rs > -2 else 2 if rs > -5 else 0
    sector = _num(row.get("SectorStrengthNifty"))
    if pd.notna(sector):
        available += weights["sector"]
        score += weights["sector"] if sector >= 2 else 6 if sector > -2 else 0
    regime = str(row.get("MarketRegime", ""))
    if regime in {"RISK_ON", "RISK_OFF", "MIXED"}:
        available += weights["market"]
        score += 10 if regime == "RISK_ON" else 4 if regime == "MIXED" else 0
    rvol = _num(row.get("RVOL"))
    if pd.notna(rvol):
        available += weights["rvol"]
        score += 10 if rvol >= 2 else 7 if rvol >= 1.5 else 4 if rvol >= 1.2 else 0
    reason = str(row.get("VolumeReason", ""))
    if reason not in {"", "Insufficient Data"}:
        available += weights["volume"]
        score += 10 if reason == "Demand-led" else 5 if reason == "Balanced / unclear" else 0
    clv = _num(row.get("CLV"))
    if pd.notna(clv):
        available += weights["clv"]
        score += 10 if clv >= 0.75 else 7 if clv >= 0.60 else 4 if clv >= 0.5 else 0
    setup = str(row.get("SetupType", ""))
    if setup not in {"", "Insufficient Data"}:
        available += weights["setup"]
        score += 10 if setup in {"Breakout", "Pullback"} else 5 if setup == "Pre-Breakout" else 3 if setup == "Possible Pullback" else 0
    delivery = _num(row.get("DeliveryPct"))
    if pd.notna(delivery):
        available += weights["delivery"]
        score += 5 if delivery >= 40 else 3 if delivery >= 25 else 0
    ad = _num(row.get("AccumulationDistribution20D"))
    if pd.notna(ad):
        available += weights["ad"]
        score += 5 if ad >= 0.20 else 3 if ad > 0 else 0
    return score, available


def run_eod_layers(
    result: pd.DataFrame,
    historical: list[pd.DataFrame],
    current: pd.DataFrame,
    nifty_history: pd.DataFrame,
    eod_date,
) -> pd.DataFrame:
    """Evaluate layers 14–24 and save the EOD watchlist report."""
    create_input_templates()
    sector_map = _read_csv(INPUT_DIR / "sector_map.csv", SECTOR_MAP_COLUMNS)
    sector_history = _read_csv(INPUT_DIR / "sector_history.csv", SECTOR_HISTORY_COLUMNS)
    news = _read_csv(INPUT_DIR / "news_evidence.csv", NEWS_COLUMNS)

    output = result.copy()
    sector = _sector_strength(output, sector_map, sector_history, eod_date)
    output = output.merge(sector, on="TckrSymb", how="left")

    regime = _market_regime(nifty_history, eod_date)
    output["MarketRegime"] = regime
    output["MarketRegimeStatus"] = "WAIT_FOR_DATA" if regime == "WAIT_FOR_DATA" else "PASS"

    delivery = output.apply(_delivery_pct, axis=1)
    output["DeliveryPct"] = delivery
    output["DeliveryClassification"] = delivery.map(
        lambda value: "WAIT_FOR_DATA" if pd.isna(value) else "High Delivery" if value >= 40 else "Moderate Delivery" if value >= 25 else "Low Delivery"
    )
    output["DeliveryStatus"] = delivery.map(lambda value: "WAIT_FOR_DATA" if pd.isna(value) else "PASS")

    def volume_reason(row):
        rvol, change, clv = _num(row.get("RVOL")), _num(row.get("PriceChangePct")), _num(row.get("CLV"))
        if pd.isna(rvol) or pd.isna(change) or pd.isna(clv):
            return "WAIT_FOR_DATA"
        if rvol >= 1.5 and change >= 0.5 and clv >= 0.65:
            return "Demand-led"
        if rvol >= 1.5 and change <= -0.5 and clv <= 0.35:
            return "Supply-led"
        if rvol >= 1.5:
            return "Balanced / unclear"
        return "No unusual volume"

    output["VolumeReason"] = output.apply(volume_reason, axis=1)
    output["VolumeReasonSource"] = "OHLCV inference only; not verified catalyst evidence"
    output["VolumeReasonStatus"] = output["VolumeReason"].map(
        lambda value: "WAIT_FOR_DATA" if value == "WAIT_FOR_DATA" else "PASS"
    )

    current_dated = current.copy()
    current_dated["Date"] = pd.Timestamp(eod_date)
    ad_history = pd.concat(
        historical[-19:] + [current_dated],
        ignore_index=True,
    )
    ad_history["Date"] = pd.to_datetime(ad_history["Date"], errors="coerce")
    ad_history = ad_history.sort_values("Date")
    ad_values = {
        str(symbol): _accumulation_score(group)
        for symbol, group in ad_history.groupby("TckrSymb")
    }
    output["AccumulationDistribution20D"] = output["TckrSymb"].astype(str).map(ad_values)
    output["AccumulationDistribution"] = output["AccumulationDistribution20D"].map(
        lambda value: "WAIT_FOR_DATA" if pd.isna(value) else "Accumulation" if value >= 0.20 else "Distribution" if value <= -0.20 else "Neutral"
    )
    output["AccumulationDistributionStatus"] = output["AccumulationDistribution"].map(
        lambda value: "WAIT_FOR_DATA" if value == "WAIT_FOR_DATA" else "PASS"
    )

    eod_end_ist = (
        pd.Timestamp(eod_date).normalize()
        + pd.Timedelta(days=1)
        - pd.Timedelta(microseconds=1)
    ).tz_localize("Asia/Kolkata")
    news_rows = [_news_for_symbol(news, symbol, eod_end_ist) for symbol in output["TckrSymb"]]
    news_frame = pd.DataFrame(news_rows, index=output.index)
    output = pd.concat([output, news_frame], axis=1)
    output["NewsStatus"] = output["NewsEvidenceStatus"].map(
        lambda value: "PASS" if value == "CONFIRMED_3_PLUS_1" else "FAIL" if value == "NEGATIVE_PRIMARY_NEWS" else "WAIT_FOR_DATA"
    )

    confirmations = []
    confirmation_statuses = []
    for _, row in output.iterrows():
        technical = sum([
            "Bullish" in str(row.get("TrendClassification", "")),
            _num(row.get("RelativeStrengthNifty")) >= 2 if pd.notna(_num(row.get("RelativeStrengthNifty"))) else False,
            _num(row.get("RVOL")) >= 1.5 if pd.notna(_num(row.get("RVOL"))) else False,
            _num(row.get("CLV")) >= 0.60 if pd.notna(_num(row.get("CLV"))) else False,
        ])
        confirmations.append(int(technical))
        confirmations_ok = (
            technical >= 3
            and row.get("NewsEvidenceStatus") == "CONFIRMED_3_PLUS_1"
            and not bool(row.get("NewsNegativePrimary"))
        )
        confirmation_statuses.append("PASS" if confirmations_ok else "WAIT_FOR_DATA" if row.get("NewsEvidenceStatus") in {"NO_DATA", "UNVERIFIED"} else "FAIL")
    output["TechnicalConfirmations"] = confirmations
    output["Confirmation3Plus1"] = output["NewsEvidenceStatus"].eq("CONFIRMED_3_PLUS_1")
    output["MandatoryConfirmationStatus"] = confirmation_statuses

    score_coverage = output.apply(_score_row, axis=1)
    output["V8Score"] = [item[0] for item in score_coverage]
    output["V8ScoreCoveragePct"] = [item[1] for item in score_coverage]

    rr_values, rr_status, rr_targets, rr_stops, chase_values = [], [], [], [], []
    hist_by_symbol = {}
    for frame in historical[-19:] + [current_dated]:
        for symbol, group in frame.groupby("TckrSymb"):
            hist_by_symbol.setdefault(str(symbol), []).append(group.iloc[-1])
    for _, row in output.iterrows():
        price = _num(row.get("ClsPric"))
        support = _num(row.get("SRSupport"))
        resistance = _num(row.get("SRResistance"))
        atr = _num(row.get("ATR14"))
        if pd.isna(atr) or atr <= 0:
            records = hist_by_symbol.get(str(row.get("TckrSymb")), [])
            ranges = []
            prev_close = float("nan")
            for record in records:
                high, low, close = _num(record.get("HghPric")), _num(record.get("LwPric")), _num(record.get("ClsPric"))
                if pd.isna(high) or pd.isna(low) or pd.isna(close):
                    continue
                tr = high - low if pd.isna(prev_close) else max(high - low, abs(high - prev_close), abs(low - prev_close))
                ranges.append(tr)
                prev_close = close
            atr = sum(ranges[-14:]) / min(len(ranges[-14:]), 14) if ranges else float("nan")
        stop_candidates = [value for value in [support, price - 1.5 * atr if pd.notna(atr) else float("nan")] if pd.notna(value) and pd.notna(price) and 0 < value < price]
        stop = max(stop_candidates) if stop_candidates else float("nan")
        entry = _num(row.get("EntryZoneHigh"))
        if pd.isna(entry) or entry <= 0:
            entry = price
        risk = entry - stop if pd.notna(stop) else float("nan")
        known_target = resistance if pd.notna(resistance) and resistance > entry else float("nan")
        target = known_target if pd.notna(known_target) else entry + 2 * risk if pd.notna(risk) and risk > 0 else float("nan")
        rr = (target - entry) / risk if pd.notna(target) and pd.notna(risk) and risk > 0 else float("nan")
        rr_values.append(rr)
        rr_targets.append(target)
        rr_stops.append(stop)
        rr_status.append("WAIT_FOR_DATA" if pd.isna(rr) else "PASS" if rr >= 2 else "FAIL")
        ema20 = _num(row.get("EMA20"))
        extended = (
            (pd.notna(price) and pd.notna(entry) and price > entry * 1.03)
            or (pd.notna(price) and pd.notna(ema20) and pd.notna(atr) and price > ema20 + 2 * atr)
            or (_num(row.get("PriceChangePct")) > 8 if pd.notna(_num(row.get("PriceChangePct"))) else False)
        )
        chase_values.append("CHASE" if extended else "CLEAR" if pd.notna(price) else "WAIT_FOR_DATA")
    output["EntryPricePlan"] = output["EntryZoneHigh"]
    output["StopLossPlan"] = rr_stops
    output["TargetPricePlan"] = rr_targets
    output["RiskReward"] = rr_values
    output["RiskRewardStatus"] = rr_status
    output["ChaseStatus"] = chase_values

    watch_statuses = []
    for _, row in output.iterrows():
        score_coverage = _num(row.get("V8ScoreCoveragePct"))
        required_data = [
            row.get("SectorStrengthStatus"), row.get("MarketRegimeStatus"),
            row.get("DeliveryStatus"), row.get("AccumulationDistributionStatus"),
            row.get("NewsStatus"), row.get("RiskRewardStatus"),
        ]
        if "WAIT_FOR_DATA" in required_data or pd.isna(score_coverage) or score_coverage < 100:
            watch_statuses.append("WAIT_FOR_DATA")
            continue
        rvol = _num(row.get("RVOL"))
        volume_reason_ok = not (pd.notna(rvol) and rvol >= 1.5) or row.get("VolumeReason") == "Demand-led"
        eligible = (
            row.get("MandatoryConfirmationStatus") == "PASS"
            and row.get("MarketRegime") != "RISK_OFF"
            and row.get("SectorStrengthStatus") == "PASS"
            and row.get("RiskRewardStatus") == "PASS"
            and row.get("ChaseStatus") == "CLEAR"
            and row.get("SetupType") in {"Breakout", "Pullback"}
            and row.get("DeliveryClassification") != "Low Delivery"
            and row.get("AccumulationDistribution") != "Distribution"
            and volume_reason_ok
            and _num(row.get("V8Score")) >= 70
        )
        watch_statuses.append("WATCH" if eligible else "SKIP")
    output["EODWatchlistStatus"] = watch_statuses
    output["EODLayerStatus"] = output["EODWatchlistStatus"].map(
        lambda value: "PASS" if value == "WATCH" else value
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output.sort_values(["EODWatchlistStatus", "V8Score"], ascending=[True, False]).to_csv(
        OUTPUT_DIR / "v8_eod_watchlist.csv", index=False
    )
    return output


def write_layer_status_summary(
    eod_result: pd.DataFrame,
    next_day_report: pd.DataFrame,
    position_report: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize data availability without labelling missing layers as passed."""
    specifications = [
        (14, "Sector strength", eod_result, "SectorStrengthStatus"),
        (15, "Market regime", eod_result, "MarketRegimeStatus"),
        (16, "Delivery analysis", eod_result, "DeliveryStatus"),
        (17, "Volume reason inference", eod_result, "VolumeReasonStatus"),
        (18, "Accumulation/distribution", eod_result, "AccumulationDistributionStatus"),
        (19, "News/catalyst evidence", eod_result, "NewsStatus"),
        (20, "Mandatory 3+1 confirmation", eod_result, "MandatoryConfirmationStatus"),
        (21, "V8 score", eod_result, "V8ScoreCoveragePct"),
        (22, "Risk/reward", eod_result, "RiskRewardStatus"),
        (23, "Chase filter", eod_result, "ChaseStatus"),
        (24, "Final EOD watchlist", eod_result, "EODLayerStatus"),
        (25, "Overnight news", next_day_report, "OvernightNewsStatus"),
        (26, "Gap analysis", next_day_report, "GapClassification"),
        (27, "Opening price action", next_day_report, "OpeningPriceAction"),
        (28, "VWAP", next_day_report, "VWAPStatus"),
        (29, "Opening volume/RVOL", next_day_report, "OpeningRVOLStatus"),
        (30, "Opening RSI", next_day_report, "RSIStatus"),
        (31, "Opening range", next_day_report, "OpeningHigh15m"),
        (32, "Nifty and sector confirmation", next_day_report, "IndexConfirmation"),
        (33, "Breakout confirmation", next_day_report, "BreakoutConfirmation"),
        (34, "Final entry/cancel review", next_day_report, "NextDayStatus"),
        (35, "Daily position monitor", position_report, "CurrentPrice"),
        (36, "Thesis check", position_report, "ThesisStatus"),
        (37, "Negative news check", position_report, "NewsEvidenceStatus"),
        (38, "Selling pressure", position_report, "SellingPressureStatus"),
        (39, "Target management", position_report, "TargetStatus"),
        (40, "Trailing stop", position_report, "TrailingStop"),
        (41, "Position review action", position_report, "PositionAction"),
    ]
    rows = []
    for layer, name, frame, column in specifications:
        if frame.empty or column not in frame.columns:
            rows.append({
                "Layer": layer, "Name": name, "Rows": 0,
                "DataAvailable": 0, "WaitingForData": 0,
                "Result": "WAIT_FOR_DATA",
            })
            continue
        values = frame[column]
        missing = values.isna()
        if pd.api.types.is_object_dtype(values.dtype) or pd.api.types.is_string_dtype(values.dtype):
            missing = missing | values.astype("string").str.strip().isin({"", "WAIT_FOR_DATA", "NO_DATA", "UNVERIFIED", "Insufficient Data"})
        waiting = int(missing.sum())
        data_available = int(len(values) - waiting)
        if column == "V8ScoreCoveragePct":
            waiting += int((values < 100).sum())
            data_available = int((values >= 100).sum())
        status = "WAIT_FOR_DATA" if data_available == 0 else "PARTIAL_DATA" if waiting else "DATA_AVAILABLE"
        rows.append({
            "Layer": layer, "Name": name, "Rows": len(values),
            "DataAvailable": data_available, "WaitingForData": waiting,
            "Result": status,
        })
    summary = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT_DIR / "v8_layer_status_summary.csv", index=False)
    return summary


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return bars
    frame = bars.copy()
    aliases = {
        "ticker": "Symbol", "symbol": "Symbol", "datetime": "Datetime",
        "timestamp": "Datetime", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume",
    }
    frame = frame.rename(columns={column: aliases[column.strip().lower()] for column in frame.columns if column.strip().lower() in aliases})
    needed = set(INTRADAY_COLUMNS)
    if not needed.issubset(frame.columns):
        return pd.DataFrame(columns=INTRADAY_COLUMNS)
    frame["Symbol"] = frame["Symbol"].astype(str).str.upper()
    frame["Datetime"] = pd.to_datetime(frame["Datetime"], errors="coerce")
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=INTRADAY_COLUMNS).sort_values("Datetime")


def _vwap(frame: pd.DataFrame) -> float:
    typical = (frame["High"] + frame["Low"] + frame["Close"]) / 3
    volume = frame["Volume"].clip(lower=0)
    total = volume.sum()
    return float((typical * volume).sum() / total) if total > 0 else float("nan")


def _rsi(values: pd.Series, period: int = 14) -> float:
    delta = values.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    if gain.empty or loss.empty:
        return float("nan")
    denominator = loss.iloc[-1]
    if pd.isna(denominator):
        return float("nan")
    if denominator == 0:
        return 100.0 if gain.iloc[-1] > 0 else 50.0
    return float(100 - 100 / (1 + gain.iloc[-1] / denominator))


def _opening_rvol(frame: pd.DataFrame, session_date, decision_time) -> float:
    sessions = frame[frame["Symbol"] == frame["Symbol"].iloc[0]].copy()
    sessions["_date"] = sessions["Datetime"].dt.date
    current = sessions[sessions["_date"] == session_date]
    current = current[current["Datetime"] <= decision_time]
    prior_dates = sorted(date for date in sessions["_date"].unique() if date < session_date)[-20:]
    if len(prior_dates) < 5 or current.empty:
        return float("nan")
    baseline = []
    for date in prior_dates:
        day = sessions[(sessions["_date"] == date) & (sessions["Datetime"].dt.time <= decision_time.time())]
        if not day.empty:
            baseline.append(float(day["Volume"].sum()))
    if len(baseline) < 5 or pd.Series(baseline).median() <= 0:
        return float("nan")
    return float(current["Volume"].sum() / pd.Series(baseline).median())


def validate_next_day(eod_result: pd.DataFrame, eod_date) -> pd.DataFrame:
    """Evaluate layers 25–34 from supplied 5-minute (or finer) market data."""
    create_input_templates()
    bars = _normalize_bars(_read_csv(INPUT_DIR / "intraday_bars.csv", INTRADAY_COLUMNS))
    news = _read_csv(INPUT_DIR / "news_evidence.csv", NEWS_COLUMNS)
    sector_map = _read_csv(INPUT_DIR / "sector_map.csv", SECTOR_MAP_COLUMNS)
    candidates = eod_result[eod_result["SetupType"].isin([
        "Breakout", "Pullback", "Pre-Breakout", "Possible Pullback",
    ])].copy()
    if bars.empty:
        rows = [{"TckrSymb": symbol, "NextDayStatus": "WAIT_FOR_DATA", "NextDayReason": "intraday_bars.csv missing or empty"} for symbol in candidates["TckrSymb"]]
        report = pd.DataFrame(rows, columns=NEXT_DAY_REPORT_COLUMNS)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        report.to_csv(OUTPUT_DIR / "v8_next_day_entry.csv", index=False)
        return report

    bars["_date"] = bars["Datetime"].dt.date
    eod_day = pd.Timestamp(eod_date).date()
    future_dates = sorted(date for date in bars["_date"].unique() if date > eod_day)
    if not future_dates:
        rows = [{"TckrSymb": symbol, "NextDayStatus": "WAIT_FOR_DATA", "NextDayReason": "No intraday session after EOD date"} for symbol in candidates["TckrSymb"]]
        report = pd.DataFrame(rows, columns=NEXT_DAY_REPORT_COLUMNS)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        report.to_csv(OUTPUT_DIR / "v8_next_day_entry.csv", index=False)
        return report
    session_date = future_dates[0]
    sector_indices = {}
    if {"TckrSymb", "SectorIndexSymbol"}.issubset(sector_map.columns):
        sector_indices = {str(row["TckrSymb"]).upper(): str(row["SectorIndexSymbol"]).upper() for _, row in sector_map.iterrows()}
    rows = []
    for _, candidate in candidates.iterrows():
        symbol = str(candidate["TckrSymb"]).upper()
        stock_all = bars[bars["Symbol"] == symbol].copy()
        stock_day = stock_all[stock_all["_date"] == session_date].sort_values("Datetime")
        if stock_day.empty or len(stock_day) < 15:
            rows.append({"TckrSymb": symbol, "NextDayStatus": "WAIT_FOR_DATA", "NextDayReason": "Need at least 15 intraday bars for opening indicators"})
            continue
        decision_time = stock_day.iloc[14]["Datetime"]
        opening_start = stock_day.iloc[0]["Datetime"]
        opening_end = opening_start + pd.Timedelta(minutes=15)
        opening = stock_day[stock_day["Datetime"] < opening_end]
        if opening.empty:
            rows.append({"TckrSymb": symbol, "NextDayStatus": "WAIT_FOR_DATA", "NextDayReason": "Opening-range bars are missing"})
            continue
        through_decision = stock_day[stock_day["Datetime"] <= decision_time]
        previous_close = _num(candidate.get("ClsPric"))
        first_open = _num(stock_day.iloc[0]["Open"])
        gap_pct = (first_open / previous_close - 1) * 100 if pd.notna(previous_close) and previous_close > 0 else float("nan")
        opening_high = float(opening["High"].max())
        opening_low = float(opening["Low"].min())
        vwap = _vwap(through_decision)
        last_close = float(through_decision.iloc[-1]["Close"])
        rsi = _rsi(through_decision["Close"])
        rvol = _opening_rvol(stock_all, session_date, decision_time)
        price_action = bool(
            float(opening.iloc[-1]["Close"]) > float(opening.iloc[0]["Open"])
            and float(opening.iloc[-1]["Close"]) >= float(opening.iloc[0]["Close"])
        )
        market = bars[(bars["Symbol"].isin(["NIFTY50", "NIFTY", "^NSEI"])) & (bars["_date"] == session_date)]
        market = market[market["Datetime"] <= decision_time]
        if len(market) < 3:
            market = pd.DataFrame()
        nifty_ok = bool(not market.empty and float(market.iloc[-1]["Close"]) > _vwap(market))
        sector_symbol = sector_indices.get(symbol, "")
        sector = bars[(bars["Symbol"] == sector_symbol) & (bars["_date"] == session_date)] if sector_symbol else pd.DataFrame()
        sector = sector[sector["Datetime"] <= decision_time] if not sector.empty else sector
        if len(sector) < 3:
            sector = pd.DataFrame()
        sector_ok = bool(not sector.empty and float(sector.iloc[-1]["Close"]) > _vwap(sector))
        level = _num(candidate.get("BreakoutLevel"))
        breakout_ok = bool(pd.notna(level) and last_close > max(level, opening_high))
        news_result = _news_for_symbol(news, symbol, decision_time, start=pd.Timestamp(eod_date) + pd.Timedelta(days=1))
        missing = []
        for label, value in [
            ("gap/previous close", gap_pct),
            ("opening RVOL baseline", rvol), ("intraday RSI", rsi),
            ("breakout level", level),
            ("Nifty bars", nifty_ok if not market.empty else None),
            ("sector bars", sector_ok if not sector.empty else None),
        ]:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                missing.append(label)
        chase = pd.notna(gap_pct) and gap_pct > 3
        gap_fail = pd.notna(gap_pct) and gap_pct < -1.5
        if missing or news_result["NewsEvidenceStatus"] in {"NO_DATA", "UNVERIFIED"}:
            status = "WAIT_FOR_DATA"
            reason = "; ".join(missing + (["overnight 3+1 news evidence"] if news_result["NewsEvidenceStatus"] in {"NO_DATA", "UNVERIFIED"} else []))
        elif chase or gap_fail or news_result["NewsNegativePrimary"]:
            status = "CANCEL"
            reason = "gap chase/down-gap or adverse primary news"
        elif (
            price_action and pd.notna(vwap) and last_close > vwap
            and pd.notna(rvol) and rvol >= 1.2
            and pd.notna(rsi) and 50 <= rsi <= 75
            and nifty_ok and sector_ok and breakout_ok
        ):
            status = "ENTRY_ELIGIBLE_REVIEW"
            reason = "All configured checks passed; manual review required"
        else:
            status = "CANCEL"
            reason = "One or more opening confirmation conditions failed"
        rows.append({
            "TckrSymb": symbol, "SessionDate": str(session_date),
            "OvernightNewsStatus": news_result["NewsEvidenceStatus"],
            "GapPct": gap_pct, "OpeningHigh15m": opening_high,
            "GapClassification": "WAIT_FOR_DATA" if pd.isna(gap_pct) else "GAP_UP" if gap_pct >= 1 else "GAP_DOWN" if gap_pct <= -1 else "FLAT_GAP",
            "OpeningPriceAction": "BULLISH" if price_action else "NOT_CONFIRMED",
            "OpeningLow15m": opening_low, "VWAP": vwap,
            "VWAPStatus": "ABOVE_VWAP" if pd.notna(vwap) and last_close > vwap else "BELOW_VWAP" if pd.notna(vwap) else "WAIT_FOR_DATA",
            "OpeningRVOL": rvol, "RSI14Intraday": rsi,
            "OpeningRVOLStatus": "PASS" if pd.notna(rvol) and rvol >= 1.2 else "FAIL" if pd.notna(rvol) else "WAIT_FOR_DATA",
            "RSIStatus": "PASS" if pd.notna(rsi) and 50 <= rsi <= 75 else "FAIL" if pd.notna(rsi) else "WAIT_FOR_DATA",
            "NiftyConfirmation": "WAIT_FOR_DATA" if market.empty else "PASS" if nifty_ok else "FAIL",
            "SectorConfirmation": "WAIT_FOR_DATA" if sector.empty else "PASS" if sector_ok else "FAIL",
            "IndexConfirmation": "WAIT_FOR_DATA" if market.empty or sector.empty else "PASS" if nifty_ok and sector_ok else "FAIL",
            "BreakoutConfirmation": "WAIT_FOR_DATA" if pd.isna(level) else "PASS" if breakout_ok else "FAIL",
            "OvernightNewsStatus": news_result["NewsEvidenceStatus"],
            "NextDayStatus": status, "NextDayReason": reason,
        })
    report = pd.DataFrame(rows, columns=NEXT_DAY_REPORT_COLUMNS)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report.to_csv(OUTPUT_DIR / "v8_next_day_entry.csv", index=False)
    return report


def monitor_positions(eod_result: pd.DataFrame, historical: list[pd.DataFrame], eod_date) -> pd.DataFrame:
    """Evaluate layers 35–41 for a user-supplied positions.csv; no orders sent."""
    create_input_templates()
    positions = _read_csv(INPUT_DIR / "positions.csv", POSITION_COLUMNS)
    news = _read_csv(INPUT_DIR / "news_evidence.csv", NEWS_COLUMNS)
    eod_end_ist = (
        pd.Timestamp(eod_date).normalize()
        + pd.Timedelta(days=1)
        - pd.Timedelta(microseconds=1)
    ).tz_localize("Asia/Kolkata")
    market = eod_result.set_index(eod_result["TckrSymb"].astype(str).str.upper(), drop=False)
    rows = []
    for _, position in positions.iterrows():
        symbol = str(position.get("TckrSymb", "")).upper().strip()
        if not symbol or symbol not in market.index:
            rows.append({"TckrSymb": symbol, "PositionAction": "CAUTION", "DecisionMode": "MANUAL_REVIEW_ONLY", "Reason": "Position symbol missing from latest EOD data"})
            continue
        row = market.loc[symbol]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        price = _num(row.get("ClsPric"))
        entry = _num(position.get("AverageEntryPrice"))
        quantity = _num(position.get("Quantity"))
        initial_stop = _num(position.get("InitialStop"))
        target = _num(position.get("Target"))
        pnl_pct = (price / entry - 1) * 100 if pd.notna(price) and pd.notna(entry) and entry > 0 else float("nan")
        stop_breached = pd.notna(price) and pd.notna(initial_stop) and price <= initial_stop
        ema50 = _num(row.get("EMA50"))
        rs = _num(row.get("RelativeStrengthNifty"))
        thesis = "INTACT" if pd.notna(price) and pd.notna(ema50) and price >= ema50 and (pd.isna(rs) or rs > -5) else "WEAKENING" if pd.notna(price) else "WAIT_FOR_DATA"
        news_state = _news_for_symbol(news, symbol, eod_end_ist, start=position.get("EntryDate") if pd.notna(position.get("EntryDate")) else None)
        negative_news = news_state["NewsNegativePrimary"]
        rvol, clv = _num(row.get("RVOL")), _num(row.get("CLV"))
        selling_pressure = bool(
            (str(row.get("VolumeReason", "")) == "Supply-led")
            or (pd.notna(rvol) and rvol >= 1.5 and pd.notna(clv) and clv < 0.25)
        )
        selling_pressure_status = "WAIT_FOR_DATA" if pd.isna(rvol) or pd.isna(clv) else "PASS"
        target_reached = pd.notna(price) and pd.notna(target) and price >= target
        target_near = pd.notna(price) and pd.notna(target) and target > 0 and (target - price) / target <= 0.02
        atr = _num(row.get("ATR14"))
        swing_low = _num(row.get("RecentSwingLow"))
        trail_candidates = [value for value in [initial_stop, swing_low, price - 2 * atr if pd.notna(price) and pd.notna(atr) and atr > 0 else float("nan")] if pd.notna(value)]
        trailing_stop = max(trail_candidates) if trail_candidates else float("nan")
        critical_missing = any(pd.isna(value) for value in [price, entry, quantity, initial_stop, target])
        if stop_breached:
            action, reason = "EXIT", "Initial stop breached; review promptly"
        elif negative_news:
            action, reason = "CAUTION", "Adverse primary-source news; review thesis"
        elif target_reached or selling_pressure:
            action, reason = "REDUCE", "Target reached or selling pressure detected"
        elif critical_missing or news_state["NewsEvidenceStatus"] in {"NO_DATA", "UNVERIFIED"}:
            action, reason = "CAUTION", "Position fields or current news evidence are missing"
        elif thesis == "WEAKENING" or target_near:
            action, reason = "CAUTION", "Thesis weakening or target near"
        else:
            action, reason = "HOLD", "No configured exit condition; manual review required"
        rows.append({
            "TckrSymb": symbol, "AsOfDate": str(eod_date), "Quantity": quantity,
            "AverageEntryPrice": entry, "CurrentPrice": price,
            "UnrealizedPnLPct": pnl_pct, "ThesisStatus": thesis,
            "NewsEvidenceStatus": news_state["NewsEvidenceStatus"],
            "NegativePrimaryNews": negative_news, "SellingPressure": selling_pressure,
            "SellingPressureStatus": selling_pressure_status,
            "TargetStatus": "WAIT_FOR_DATA" if pd.isna(target) else "REACHED" if target_reached else "NEAR" if target_near else "OPEN",
            "TrailingStop": trailing_stop, "PositionAction": action,
            "DecisionMode": "MANUAL_REVIEW_ONLY", "Reason": reason,
        })
    report = pd.DataFrame(rows, columns=POSITION_REPORT_COLUMNS)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report.to_csv(OUTPUT_DIR / "v8_position_monitor.csv", index=False)
    return report
