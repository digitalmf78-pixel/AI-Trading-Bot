"""Research-first Telegram sections and per-run research watchlist export."""
from pathlib import Path
import pandas as pd

OUT = Path("outputs")
WATCHLIST = OUT / "v8_telegram_research_watchlist.csv"
SNAPSHOT_DIR = OUT / "research_watchlists"

def _read(name):
    try:
        frame = pd.read_csv(OUT / name)
        return frame if not frame.empty else pd.DataFrame()
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()

def _delivery():
    files = sorted(OUT.glob("v8_delivery_quantity_observations_*.csv"))
    return _read(files[-1].name) if files else pd.DataFrame()

def _v(row, key, default="WAIT_FOR_DATA"):
    value = row.get(key, default)
    return default if value is None or pd.isna(value) or str(value).strip().lower() in {"", "nan", "none"} else str(value).strip()

def _n(row, key, suffix="", digits=1):
    value = pd.to_numeric(pd.Series([row.get(key)]), errors="coerce").iloc[0]
    return f"{value:,.{digits}f}{suffix}" if pd.notna(value) else "WAIT"

def _join(left, right, suffix):
    if right.empty or "TckrSymb" not in right:
        return left
    part = right.copy()
    part["TckrSymb"] = part["TckrSymb"].astype(str).str.strip().str.upper()
    part = part.drop_duplicates("TckrSymb", keep="last").set_index("TckrSymb").add_suffix(suffix)
    if left.empty:
        left = pd.DataFrame(index=part.index)
    elif "TckrSymb" in left:
        left = left.set_index("TckrSymb")
    return left.join(part, how="outer").rename_axis("TckrSymb").reset_index()

def _build_watchlist(result, news, eod_date):
    sources = {
        "delivery": _delivery(),
        "acc": _read("v8_hybrid_potential_accumulation_watchlist.csv"),
        "base": _read("v8_hybrid_base_vcp_watchlist.csv"),
        "setup": _read("v8_hybrid_breakout_ready_watchlist.csv"),
        "entry": _read("v8_hybrid_confirmed_entry_watchlist.csv"),
        "fund": _read("v8_fundamental_report.csv"),
        "events": _read("v8_upcoming_corporate_events.csv"),
    }
    frames = [result, *sources.values()]
    symbols = sorted({str(x).strip().upper() for frame in frames
                      if frame is not None and not frame.empty and "TckrSymb" in frame
                      for x in frame["TckrSymb"].dropna() if str(x).strip()})
    watch = pd.DataFrame({"TckrSymb": symbols})
    for key, suffix in (("delivery", "_Delivery"), ("acc", "_Accumulation"),
                        ("base", "_BaseVCP"), ("setup", "_Setup"),
                        ("entry", "_Entry"), ("fund", "_Fundamental")):
        watch = _join(watch, sources[key], suffix)
    ref = pd.to_datetime(eod_date, errors="coerce")
    event_map = {}
    for _, row in sources["events"].iterrows():
        sym = _v(row, "TckrSymb", "")
        day = pd.to_datetime(row.get("EventDate"), errors="coerce")
        if not sym:
            continue
        if pd.notna(ref) and pd.notna(day):
            delta = (day.normalize() - ref.normalize()).days
            if 0 < delta <= 20 and _v(row, "Status", "") == "OFFICIAL_DATE_CONFIRMED":
                event_map.setdefault(sym, []).append(f"{day.date()} ({delta}d): {_v(row, 'EventType', 'Event')}")
        elif _v(row, "Status", "") not in {"", "NO_MATCHING_UPCOMING_EVENT_FOUND"}:
            event_map.setdefault(sym, []).append("DATE_NOT_CONFIRMED")
    if not sources["events"].empty:
        watch["UpcomingEvents20D"] = watch["TckrSymb"].map(
            lambda s: " | ".join(dict.fromkeys(event_map.get(s, []))) or "NO_CONFIRMED_EVENT_IN_20D")
    if news is not None and not news.empty and {"TckrSymb", "Headline"}.issubset(news.columns):
        nm = {}
        for _, row in news.iterrows():
            sym, headline = _v(row, "TckrSymb", ""), _v(row, "Headline", "")
            if sym and headline:
                nm.setdefault(sym, []).append(f"{_v(row, 'Impact', 'unverified')} | {headline} | {_v(row, 'URL', '')}")
        watch["NewsEvidence"] = watch["TckrSymb"].map(lambda s: " || ".join(nm.get(s, [])[:3]))
    watch = watch.drop(columns=["AsOfDate"], errors="ignore")
    tags = []
    for _, row in watch.iterrows():
        labels = []
        for col, label in (("WatchlistStatus_Accumulation", "ACCUMULATION"), ("WatchlistStatus_BaseVCP", "BASE_VCP"), ("WatchlistStatus_Setup", "BREAKOUT_PULLBACK"), ("WatchlistStatus_Entry", "FINAL_ENTRY")):
            if str(row.get(col, "")).upper() not in {"", "NAN", "NONE", "NO_SETUP", "WAIT_FOR_DATA"}:
                labels.append(label)
        tags.append("|".join(labels) if labels else "RESEARCH_ONLY")
    watch["ResearchWatchlistCategories"] = tags
    watch.insert(0, "AsOfDate", str(eod_date))
    OUT.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    watch.to_csv(WATCHLIST, index=False)
    date_key = pd.to_datetime(eod_date, errors="coerce")
    if pd.notna(date_key):
        watch.to_csv(SNAPSHOT_DIR / f"v8_telegram_research_watchlist_{date_key:%Y%m%d}.csv", index=False)
    return watch


def select_summary_stocks(rows, max_stocks=10):
    """Select only final WATCH/ENTRY_CANDIDATE rows; entry first, then V8Score."""
    if rows is None or rows.empty or "TckrSymb" not in rows.columns:
        return pd.DataFrame()
    selected = rows.copy()
    status_col = "EODWatchlistStatus" if "EODWatchlistStatus" in selected.columns else None
    if status_col is None:
        return selected.iloc[0:0].copy()
    status = selected[status_col].fillna("").astype(str).str.strip().str.upper()
    selected = selected[status.isin({"ENTRY_CANDIDATE", "WATCH"})].copy()
    if selected.empty:
        return selected
    selected["_final_rank"] = selected[status_col].fillna("").astype(str).str.upper().map(
        {"ENTRY_CANDIDATE": 0, "WATCH": 1}
    ).fillna(2)
    if "V8Score" in selected.columns:
        selected["_v8_sort"] = pd.to_numeric(selected["V8Score"], errors="coerce")
        selected = selected.sort_values(
            ["_final_rank", "_v8_sort", "TckrSymb"],
            ascending=[True, False, True], na_position="last", kind="stable",
        )
    else:
        selected = selected.sort_values(
            ["_final_rank", "TckrSymb"], ascending=[True, True], kind="stable"
        )
    selected = selected.drop(columns=["_final_rank", "_v8_sort"], errors="ignore")
    if max_stocks is not None:
        selected = selected.head(max(0, int(max_stocks)))
    return selected.reset_index(drop=True)


def build_telegram_research_sections(result, news, eod_date, company_names=None):
    """Render the research summary; source reports remain the evidence of record."""
    watch = _build_watchlist(result if result is not None else pd.DataFrame(), news, eod_date)
    company_names = company_names or {}
    def identity(symbol):
        symbol = str(symbol or "").strip().upper()
        official_name = company_names.get(symbol)
        return f"{official_name} | NSE: {symbol}" if official_name else f"NAME_NOT_VERIFIED_IN_NSE_MASTER | NSE: {symbol}"
    lines = ["", "━━━━━━━━━━━━━━━━━━━━", "🔬 RESEARCH BRIEF • पुराव्यावर आधारित निरीक्षण",
             "", "📦 DELIVERY + PRICE RESPONSE • 5D / 10D / 20D"]
    delivery = _delivery()
    if delivery.empty:
        lines.append("Delivery quantity report उपलब्ध नाही; WAIT_FOR_DATA.")
    for _, row in delivery.head(12).iterrows():
        sym = _v(row, "TckrSymb", "")
        if not sym:
            continue
        bits = []
        for days in (5, 10, 20):
            p = f"DeliveryQty{days}D"
            if _v(row, p + "Status", "") == "COMPLETE":
                bits.append(f"{days}D Qty Δ {_n(row,p+'ChangePct','%')} | Del% {_n(row,p+'DeliveryPctAverage','%')} | Price {_n(row,p+'CloseChangePct','%')}")
            else:
                bits.append(f"{days}D WAIT_FOR_DATA")
        lines.append(f"• {identity(sym)}: " + " ; ".join(bits))
    acc = _read("v8_hybrid_potential_accumulation_watchlist.csv")
    lines.extend(["", f"🟢 EARLY ACCUMULATION WATCH • {len(acc)} rows | observation only"])
    if acc.empty:
        lines.append("Accumulation observation report उपलब्ध नाही.")
    else:
        counts = acc.get("WatchlistStatus", pd.Series("WAIT_FOR_DATA", index=acc.index)).fillna("WAIT_FOR_DATA").value_counts().to_dict()
        lines.append(f"ACCUMULATION_WATCH {counts.get('ACCUMULATION_WATCH',0)} | WAIT {counts.get('WAIT_FOR_DATA',0)}")
        for _, row in acc.head(12).iterrows():
            lines.append(f"• {identity(_v(row,'TckrSymb',''))}: {_v(row,'WatchlistStatus')} | High-delivery days {_n(row,'HighDeliverySessionCount','',0)} | Up/Down {_n(row,'HighDeliveryUpDayCount','',0)}/{_n(row,'HighDeliveryDownDayCount','',0)} | {_v(row,'WatchlistReason')}")
    setup = _read("v8_hybrid_breakout_ready_watchlist.csv")
    lines.extend(["", "🎯 BREAKOUT / PULLBACK WATCHLIST"])
    if setup.empty:
        lines.append("Breakout/Pullback report उपलब्ध नाही.")
    for _, row in setup.head(15).iterrows():
        lines.append(f"• {identity(_v(row,'TckrSymb',''))}: {_v(row,'WatchlistStatus')} | Breakout {_v(row,'BreakoutStatus')} | Pullback {_v(row,'PullbackStatus')} | Chase {_v(row,'ChaseStatus')}")
    entry = _read("v8_hybrid_confirmed_entry_watchlist.csv")
    eligible = entry[entry.get("WatchlistStatus", pd.Series("", index=entry.index)).astype(str).eq("ENTRY_CANDIDATE")] if not entry.empty else entry
    lines.extend(["", f"✅ FINAL ENTRY WATCHLIST • {len(eligible)} candidate(s)"])
    if eligible.empty:
        lines.append("विद्यमान final gates नुसार ENTRY_CANDIDATE नाही.")
    else:
        for _, row in eligible.head(15).iterrows():
            lines.append(f"• {identity(_v(row,'TckrSymb',''))}: {_v(row,'WatchlistReason')}")
    fund = _read("v8_fundamental_report.csv")
    lines.extend(["", f"📊 FUNDAMENTAL RESEARCH • {len(fund)} collected rows"])
    if not fund.empty:
        counts = fund.get("FundamentalStatus", pd.Series("WAIT_FOR_DATA", index=fund.index)).fillna("WAIT_FOR_DATA").value_counts().to_dict()
        lines.append(f"COMPLETE {counts.get('COMPLETE',0)} | PARTIAL {counts.get('PARTIAL_DATA',0)} | MISSING {counts.get('MISSING_DATA',0)}")
        for _, row in fund.head(10).iterrows():
            metrics = [f"{label} {_n(row,col,suffix)}" for col,label,suffix in
                       (("RevenueGrowthPct","Revenue","%"),("ProfitGrowthPct","Profit","%"),
                        ("ROEPercent","ROE","%"),("ROCEPercent","ROCE","%"),
                        ("DebtToEquity","D/E","x"),("InterestCoverage","Interest Cov.","x"),("TrailingPE","P/E","x"),("PriceToBook","P/B","x"),("PromoterHoldingPct","Promoter","%"),("FIIHoldingPct","FII","%"),("DIIHoldingPct","DII","%")) if col in fund.columns]
            lines.append(f"• {identity(_v(row,'TckrSymb',''))}: {_v(row,'FundamentalStatus')} | Score {_n(row,'FundamentalScore','/100')} | " + " | ".join(metrics))
    events = _read("v8_upcoming_corporate_events.csv")
    ref = pd.to_datetime(eod_date, errors="coerce")
    confirmed = []
    for _, row in events.iterrows():
        day = pd.to_datetime(row.get("EventDate"), errors="coerce")
        if pd.notna(ref) and pd.notna(day) and 0 < (day.normalize()-ref.normalize()).days <= 20 and _v(row,"Status","") == "OFFICIAL_DATE_CONFIRMED":
            confirmed.append(row)
    lines.extend(["", f"📅 CORPORATE EVENTS • पुढील 20 दिवस | confirmed {len(confirmed)}"])
    if not confirmed:
        lines.append("पुढील 20 दिवसांत अधिकृत तारीख पुष्टी झालेला event उपलब्ध नाही.")
    for row in confirmed[:15]:
        lines.append(f"• {identity(_v(row,'TckrSymb',''))} | {_v(row,'EventDate')} | {_v(row,'EventType','Event')} | {_v(row,'Headline','')[:130]}")
        url = _v(row,"URL","")
        if url:
            lines.append(f"  Source: {_v(row,'Source','NSE')} | {url[:900]}")
    lines.extend(["", "📰 NEWS & CATALYST • issuer-matched headlines"])
    shown = 0
    if news is not None and not news.empty and "TckrSymb" in news.columns:
        ordered = news.copy()
        if "PublishedAt" in ordered.columns:
            ordered["_sort"] = pd.to_datetime(ordered["PublishedAt"], errors="coerce", utc=True)
            ordered = ordered.sort_values("_sort", ascending=False, na_position="last")
        for _, row in ordered.iterrows():
            headline = _v(row,"Headline","")
            if not headline or shown >= 15:
                continue
            lines.append(f"• {identity(_v(row,'TckrSymb',''))} | {_v(row,'Impact','unverified').upper()} | {_v(row,'SourceType','source')} | {_v(row,'PublishedAt','')}")
            lines.append(f"  {headline[:180]}")
            url = _v(row,"URL","")
            if url:
                lines.append(f"  Link: {url[:900]}")
            shown += 1
    if not shown:
        lines.append("या scan window मध्ये issuer-matched headline नाही.")
    lines.extend(["", f"📌 RESEARCH WATCHLIST EXPORT: {len(watch)} symbols",
                  "पूर्ण per-stock report: outputs/v8_telegram_research_watchlist.csv",
                  "Delivery वाढ + Price वाढ हा price-response observation आहे; एकट्या Delivery % वर Accumulation सिद्ध होत नाही.",
                  "Possible Pullback आणि Confirmed Pullback वेगळे आहेत. WAIT_FOR_DATA म्हणजे पुरावा अपुरा; FAIL नाही.",
                  "ही Research/Watchlist माहिती आहे; BUY शिफारस किंवा automatic order नाही."])
    return lines
