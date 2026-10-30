"""Pure parsing/classification helpers for the Screener relative-P/E watchlist."""
from __future__ import annotations
import re
import statistics


def parse_positive_number(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in {"", "-", "—", "NA", "N/A", "nan", "None"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        number = float(match.group(0))
    except ValueError:
        return None
    return number if number > 0 else None


def extract_stock_pe(page_text: str):
    """Extract a positive Stock P/E value from normalized Screener page text."""
    match = re.search(r"Stock\s+P\s*/\s*E\s+([\d,]+(?:\.\d+)?)", page_text, flags=re.I)
    return parse_positive_number(match.group(1)) if match else None


def classify_relative_pe(own_pe, peer_pes):
    valid = [float(x) for x in peer_pes if parse_positive_number(x) is not None]
    if parse_positive_number(own_pe) is None or len(valid) < 3:
        return "DATA_INSUFFICIENT", None, None
    peer_median = statistics.median(valid)
    ratio = float(own_pe) / peer_median
    if ratio <= 0.80:
        status = "RELATIVELY_UNDERVALUED"
    elif ratio <= 1.20:
        status = "FAIRLY_VALUED"
    else:
        status = "RELATIVELY_OVERVALUED"
    return status, peer_median, ratio
