import io
import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup
from delivery_filter import get_delivery_sessions
from valuation_parsing import parse_positive_number, extract_stock_pe, classify_relative_pe

OUTPUT = Path("delivery_60_valuation_watchlist.csv")
VALUATION_CACHE = Path("data/cache/valuation/screener_relative_valuation.json")
VALUATION_CACHE_TTL_SECONDS = 36 * 60 * 60
VALUATION_WORKERS = 6
MIN_DELIVERY = 60.0
REQUIRED_SESSIONS = 5
MAX_ASOF_LOOKBACK_DAYS = 10
SCREENER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def normalise_columns(df):
    df = df.copy()
    df.columns = [str(c).strip().upper().replace(" ", "_") for c in df.columns]
    return df

def is_fund_or_etf(row):
    symbol = str(row.get("SYMBOL", "")).upper().strip()
    security = str(row.get("SECURITY", "")).upper().strip()
    if any(term in security for term in (" ETF", "EXCHANGE TRADED FUND", "MUTUAL FUND")):
        return True
    # Common NSE ETF/fund naming patterns, not price/technical filters.
    if symbol.endswith(("BEES", "IETF", "ETF", "LIQUIDCASE", "LIQUIDETF")):
        return True
    if symbol in {"GOLDETF", "SILVERETF", "GOLDIETF", "SILVERIETF"}:
        return True
    return False

def parse_number(value):
    return parse_positive_number(value)

def load_valuation_cache():
    try:
        data = json.loads(VALUATION_CACHE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        # Ignore entries written by the earlier version, which cached transient
        # network failures as DATA_INSUFFICIENT for 36 hours.
        return {
            symbol: item for symbol, item in data.items()
            if isinstance(item, dict) and item.get("cacheable") is True
        }
    except (OSError, json.JSONDecodeError):
        return {}

valuation_cache = load_valuation_cache()

def save_valuation_cache():
    VALUATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    temporary = VALUATION_CACHE.with_suffix(".tmp")
    temporary.write_text(json.dumps(valuation_cache, sort_keys=True), encoding="utf-8")
    temporary.replace(VALUATION_CACHE)

def relative_valuation(symbol):
    """Use only validated cache entries; never cache transient network failures."""
    now = time.time()
    cached = valuation_cache.get(symbol)
    if (
        isinstance(cached, dict)
        and cached.get("cacheable") is True
        and now - float(cached.get("timestamp", 0)) < VALUATION_CACHE_TTL_SECONDS
    ):
        return cached.get("valuation", "DATA_INSUFFICIENT"), "CACHE"

    url = f"https://www.screener.in/company/{symbol}/"
    cacheable = False
    try:
        with requests.Session() as http:
            http.headers.update(SCREENER_HEADERS)
            response = http.get(url, timeout=8)

        if response.status_code != 200 or len(response.text) < 1000:
            result = "DATA_INSUFFICIENT"
            reason = f"Screener unavailable (HTTP {response.status_code})"
        else:
            # A valid page response is safe to cache even when its financial fields
            # are absent; connection/HTTP failures are not.
            cacheable = True
            soup = BeautifulSoup(response.text, "lxml")
            page_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            own_pe = extract_stock_pe(page_text)
            if own_pe is None:
                result, reason = "DATA_INSUFFICIENT", "current positive P/E unavailable"
            else:
                peer_pes = []
                try:
                    tables = pd.read_html(io.StringIO(response.text))
                except Exception:
                    tables = []
                for table in tables:
                    table.columns = [re.sub(r"\s+", " ", str(c)).strip().upper() for c in table.columns]
                    pe_col = next((c for c in table.columns if "STOCK P/E" in c or c == "P/E" or c.endswith(" P/E")), None)
                    if pe_col is None or len(table) < 3:
                        continue
                    for value in table[pe_col].tolist():
                        pe = parse_number(value)
                        if pe is not None:
                            peer_pes.append(pe)
                if len(peer_pes) < 3:
                    result, reason = "DATA_INSUFFICIENT", f"insufficient peer P/E observations ({len(peer_pes)})"
                else:
                    result, peer_median, ratio = classify_relative_pe(own_pe, peer_pes)
                    if peer_median is None or ratio is None:
                        reason = "peer median invalid"
                    else:
                        reason = f"own P/E={own_pe:.2f}, peer median={peer_median:.2f}, ratio={ratio:.2f}"
    except Exception as exc:
        result, reason = "DATA_INSUFFICIENT", f"{type(exc).__name__}: {exc}"
        cacheable = False

    if cacheable:
        valuation_cache[symbol] = {
            "valuation": result,
            "timestamp": now,
            "cacheable": True,
        }
    else:
        # Remove stale/bad entries produced by older versions, so they do not
        # freeze a temporary outage as a 36-hour valuation result.
        valuation_cache.pop(symbol, None)
    print(f"[VALUATION] {symbol}: {reason} => {result}" + ("" if cacheable else " [NOT CACHED]"))
    return result, "FETCH"


def write_empty(status):
    pd.DataFrame(columns=["SYMBOL", "VALUATION"]).to_csv(OUTPUT, index=False)
    print(f"[RESULT] {status}; output is an empty SYMBOL,VALUATION CSV")

# Reuse the project's delivery_filter.py and data/cache/delivery/.
# Do not create a second Bhavcopy downloader or a second cache.
today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
sessions = None
asof = today_ist
last_error = None
for offset in range(MAX_ASOF_LOOKBACK_DAYS + 1):
    candidate_date = today_ist - timedelta(days=offset)
    if candidate_date.weekday() >= 5:
        continue
    try:
        sessions = get_delivery_sessions(candidate_date, required_sessions=REQUIRED_SESSIONS)
        asof = candidate_date
        break
    except RuntimeError as exc:
        last_error = exc
        print(f"[DELIVERY] No complete five-session window ending {candidate_date}: {exc}")

if not sessions or len(sessions) < REQUIRED_SESSIONS:
    write_empty(f"WAIT_FOR_DATA: existing project delivery cache/source did not provide five valid sessions; last_error={last_error}")
    raise SystemExit(0)

# Existing delivery_filter returns validated reports from its existing cache/download path.
sessions = [(day, frame.copy()) for day, frame in sessions]
for day, frame in sessions:
    print(f"[BHAVCOPY-REUSE] {day}: reused delivery_filter.py report, {len(frame)} rows")

sessions.sort(key=lambda item: item[0])
print("[SESSIONS] oldest-to-newest: " + ", ".join(day.isoformat() for day, _ in sessions))

# Build a strict intersection: a symbol must have one unambiguous EQ delivery value
# on every one of the five accepted dates, and every value must be >=60.00%.
per_day = []
for day, frame in sessions:
    frame = frame.copy()
    frame.columns = [str(c).strip().upper().replace(" ", "_") for c in frame.columns]
    required = {"SYMBOL", "SERIES", "DELIV_PER"}
    if not required.issubset(frame.columns):
        print(f"[DELIVERY] {day}: required fields missing in existing cache; fail closed")
        write_empty("WAIT_FOR_DATA: existing delivery report missing required fields")
        raise SystemExit(0)
    frame["SYMBOL"] = frame["SYMBOL"].astype(str).str.strip().str.upper()
    frame["SERIES"] = frame["SERIES"].astype(str).str.strip().str.upper()
    frame["DELIV_PER"] = pd.to_numeric(frame["DELIV_PER"], errors="coerce")
    frame = frame[(frame["SERIES"] == "EQ") & frame["DELIV_PER"].between(0, 100)]
    if "SECURITY" not in frame.columns:
        frame["SECURITY"] = ""
    frame = frame[~frame.apply(is_fund_or_etf, axis=1)]
    counts = frame.groupby("SYMBOL").size()
    ambiguous = set(counts[counts != 1].index)
    if ambiguous:
        frame = frame[~frame["SYMBOL"].isin(ambiguous)]
        print(f"[DELIVERY] {day}: excluded {len(ambiguous)} duplicate/ambiguous symbols")
    day_values = frame.set_index("SYMBOL")["DELIV_PER"].to_dict()
    per_day.append(day_values)

common_symbols = set(per_day[0])
for day_values in per_day[1:]:
    common_symbols.intersection_update(day_values)
qualifying = sorted(
    symbol for symbol in common_symbols
    if all(day_values[symbol] >= MIN_DELIVERY for day_values in per_day)
)
print(f"[DELIVERY] qualifying stocks with all five sessions >= {MIN_DELIVERY:.2f}%: {len(qualifying)}")

if not qualifying:
    write_empty("NO_STOCKS_MET_ALL_FIVE_DAYS")
    raise SystemExit(0)

rows_by_symbol = {}
cache_hits = 0
fetches = 0

# One quick connectivity probe prevents hundreds of doomed requests when the
# Actions runner cannot reach Screener. It does not classify any stock.
screener_available = False
try:
    probe = requests.get("https://www.screener.in/", headers=SCREENER_HEADERS, timeout=5)
    screener_available = probe.status_code == 200 and len(probe.text) >= 1000
    print(f"[VALUATION-PREFLIGHT] HTTP {probe.status_code}; reachable={screener_available}")
except Exception as exc:
    print(f"[VALUATION-PREFLIGHT] unreachable ({type(exc).__name__}: {exc}); skipping per-stock requests")

if screener_available:
    with ThreadPoolExecutor(max_workers=VALUATION_WORKERS) as pool:
        future_map = {pool.submit(relative_valuation, symbol): symbol for symbol in qualifying}
        for future in as_completed(future_map):
            symbol = future_map[future]
            try:
                valuation, source = future.result()
            except Exception as exc:
                valuation, source = "DATA_INSUFFICIENT", "ERROR"
                print(f"[VALUATION] {symbol}: worker error {type(exc).__name__}: {exc}")
            rows_by_symbol[symbol] = {"SYMBOL": symbol, "VALUATION": valuation}
            cache_hits += source == "CACHE"
            fetches += source == "FETCH"
    save_valuation_cache()
else:
    # Keep the delivery watchlist useful even if external valuation is offline.
    # No stock gets a guessed label and no outage result is cached.
    for symbol in qualifying:
        rows_by_symbol[symbol] = {"SYMBOL": symbol, "VALUATION": "DATA_INSUFFICIENT"}
    # Overwrite any legacy outage-cache file with only validated cache entries.
    save_valuation_cache()

print(f"[VALUATION-SUMMARY] cache_hits={cache_hits}; fetched={fetches}; workers={VALUATION_WORKERS}; screener_reachable={screener_available}")

result = pd.DataFrame([rows_by_symbol[s] for s in qualifying], columns=["SYMBOL", "VALUATION"])
result.to_csv(OUTPUT, index=False)
print("\n===== FINAL OUTPUT: qualifying stock names and relative valuation only =====")
if result.empty:
    print("No qualifying stocks.")
else:
    print(result.to_string(index=False))
print(f"[DONE] wrote {OUTPUT} with {len(result)} rows")