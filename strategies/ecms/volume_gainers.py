"""NSE Volume Gainers page scanner for ECMS. No orders; shared inputs are read-only."""
from __future__ import annotations
import argparse, json, os, re, shutil
from email.utils import parsedate_to_datetime
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from strategies.ecms.eod import (
    IST, HEADERS, OUTPUT_DIR, METRICS_PATH, THRESHOLDS_PATH, FILINGS_PATH, EVIDENCE_PATH,
    expected_latest_completed_session,
    collect_catalysts, load_official_mainboard_symbols,
    discover_latest_session, load_prior_sessions, _read_valid_bhavcopy, calculate_rvol,
)
from fundamental_metric_verification import run_audit as run_fundamental_xbrl_audit
from fundamental_shortlist import build_fundamental_shortlist
from strategies.ecms.fundamental_source_compilation import build_fundamental_source_compilation
from strategies.ecms.debt_equity_xbrl_audit import AUDIT_COLUMNS as DEBT_EQUITY_AUDIT_COLUMNS, audit_ecms_debt_to_equity
from strategies.ecms.ratio_xbrl_discovery_audit import OUTPUT_COLUMNS as RATIO_XBRL_DISCOVERY_COLUMNS, discover_ecms_ratio_xbrl_facts
from strategies.ecms.filing_metadata_audit import OUTPUT_COLUMNS as FILING_METADATA_AUDIT_COLUMNS, audit_ecms_filing_metadata, fetch_ecms_candidate_filing_metadata, fetch_ecms_details_remarks
from strategies.ecms.information import (
    attach_valuation, collect_upcoming_events, collect_bulk_block_deals, collect_corporate_actions,
)
from nse_trading_calendar import is_trading_session, expected_scan_time, calendar_coverage_warnings, CalendarCoverageError
NSE_PAGE = "https://www.nseindia.in/market-data/volume-gainers-spurts"
NSE_API = "https://www.nseindia.in/api/live-analysis-volume-gainers"
STATE_DIR = Path("data/cache/ecms")
STATE_FILE = STATE_DIR / "volume_gainers_previous_eod.csv"
CONSUMED_EOD_MARKER_FILE = STATE_DIR / "volume_gainers_previous_eod_consumed.json"
MORNING_STATE_FILE = STATE_DIR / "volume_gainers_same_day_morning.csv"
REQUEST_TIMEOUT = (8, 20)
ALIASES = {
 "symbol": ("symbol","tradingSymbol","ticker"),
 "company": ("securityName","companyName","company","name"),
 "series": ("series","securitySeries"),
 "volume": ("volume","totalTradedVolume","totalTradedQty","totalTradedQuantity","tradedVolume","tradedQty","tradedQuantity","quantityTraded","qtyTraded","volumeTraded","totalVolume","quantity"),
 "ltp": ("ltp","lastPrice","lastTradedPrice","closePrice"),
 "change_pct": ("pChange","perChange","changePercent","percentChange"),
 "turnover": ("turnover","totalTradedValue","value"),
 "avg_volume_1w": ("week1AvgVolume","avgVolume1W","averageVolume1W","weekAvgVolume","avgVolume"),
 "change_pct_1w": ("week1volChange","week1VolChange","volumeChangePct1W","volumeChange1W","change1W","changeInVolume1W"),
 "avg_volume_2w": ("week2AvgVolume","avgVolume2W","averageVolume2W","twoWeekAvgVolume","averageVolume"),
 "change_pct_2w": ("week2volChange","week2VolChange","volumeChangePct2W","volumeChange2W","change2W","changeInVolume2W"),
 "change_times_1w": ("volumeChangeTimes1W","changeTimes1W"),
 "change_times_2w": ("volumeChangeTimes2W","changeTimes2W"),
 "updated_at": ("updatedAt","updated_at","timestamp"),
}
def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())
def _find_records(payload):
    if isinstance(payload, list):
        rows = [x for x in payload if isinstance(x, dict)]
        if rows and any(_key(k) in {"symbol","tradingsymbol","ticker"} for r in rows for k in r):
            return rows
        for item in payload:
            found = _find_records(item)
            if found: return found
    elif isinstance(payload, dict):
        for name in ("data","volumeGainers","records","rows","tableData","result"):
            if name in payload:
                found = _find_records(payload[name])
                if found: return found
        for value in payload.values():
            found = _find_records(value)
            if found: return found
    return []
def _get(row, aliases):
    normalized = {_key(k): v for k,v in row.items()}
    for alias in aliases:
        if _key(alias) in normalized: return normalized[_key(alias)]
    return None
def _number(value):
    if value is None or str(value).strip() in {"","-","NA","None"}: return None
    try: return float(str(value).replace(",","").replace("%","").strip())
    except (TypeError,ValueError): return None

def _metric_value_provenance(metric_row, metric_name):
    """Resolve the displayed value's own provenance, not the separate XBRL audit source."""
    def _mapping(field):
        try:
            value = json.loads(str(metric_row.get(field, "{}") or "{}"))
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    sources = _mapping("MetricSourcesJSON")
    urls = _mapping("MetricSourceURLsJSON")
    periods = _mapping("MetricSourcePeriodsJSON")
    bases = _mapping("MetricCalculationBasesJSON")
    currencies = _mapping("MetricSourceCurrenciesJSON")
    unit = (
        "PERCENT" if metric_name.endswith("Pct") or metric_name in {"ROEPercent", "ROCEPercent"}
        else "RATIO" if metric_name in {"DebtToEquity", "InterestCoverage"}
        else "INR" if metric_name == "OperatingCashFlowINR"
        else "NOT_SPECIFIED"
    )
    return {
        "ValueSource": str(sources.get(metric_name, "") or "NOT_AVAILABLE"),
        "ValueSourceURL": str(urls.get(metric_name, "") or ""),
        "ValuePeriodEnd": str(periods.get(metric_name, "") or ""),
        "ValueBasis": str(bases.get(metric_name, "") or ""),
        "ValueCurrency": str(currencies.get(metric_name, "") or ""),
        "ValueUnit": unit,
    }

def _volume_number(value):
    """Parse NSE quantity values, including compact Indian lakh/crore display units."""
    if value is None:
        return None
    raw = str(value).strip().replace(",", "").replace(" ", "")
    if raw.upper() in {"", "-", "NA", "NONE", "NAN"}:
        return None
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))([A-Za-z]*)", raw)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {
        "": 1.0, "unit": 1.0, "units": 1.0,
        "k": 1_000.0, "thousand": 1_000.0,
        "l": 100_000.0, "lac": 100_000.0, "lacs": 100_000.0,
        "lakh": 100_000.0, "lakhs": 100_000.0,
        "m": 1_000_000.0, "mn": 1_000_000.0, "million": 1_000_000.0,
        "cr": 10_000_000.0, "crore": 10_000_000.0, "crores": 10_000_000.0,
        "b": 1_000_000_000.0, "bn": 1_000_000_000.0, "billion": 1_000_000_000.0,
    }
    multiplier = multipliers.get(unit)
    return amount * multiplier if multiplier is not None else None
def fetch_volume_gainers(session=None):
    client = session or requests.Session()
    client.headers.update(HEADERS)
    client.headers["Referer"] = NSE_PAGE
    landing = client.get(NSE_PAGE, timeout=REQUEST_TIMEOUT); landing.raise_for_status()
    response = client.get(NSE_API, timeout=REQUEST_TIMEOUT); response.raise_for_status()
    server_date_raw = getattr(response, "headers", {}).get("Date", "")
    try:
        server_date = parsedate_to_datetime(server_date_raw).astimezone(IST).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        server_date = ""
    fetched_at = datetime.now(IST).isoformat()
    rows = _find_records(response.json())
    if not rows: raise RuntimeError("WAIT_FOR_DATA: NSE Volume Gainers API returned no recognizable symbol rows")
    normalized=[]
    for row in rows:
        symbol=str(_get(row,ALIASES["symbol"]) or "").strip().upper()
        if not symbol or symbol in {"-","NAN","NONE"}: continue
        exact_volume_field = next((
            str(key) for key in row
            if _key(key) in {_key(alias) for alias in ALIASES["volume"]}
            and _volume_number(row.get(key)) is not None
        ), "")
        fuzzy_volume_fields = [
            str(key) for key in row
            if any(token in _key(key) for token in ("volume", "tradedqty", "tradedquantity", "qtytraded"))
            and not any(token in _key(key) for token in ("avg", "average", "week", "change", "percent"))
            and _volume_number(row.get(key)) is not None
        ]
        volume_field = exact_volume_field or (fuzzy_volume_fields[0] if len(fuzzy_volume_fields) == 1 else "")
        volume_raw = row.get(volume_field) if volume_field else _get(row, ALIASES["volume"])
        payload_keys = "|".join(sorted(str(key) for key in row))
        volume_like_fields = "|".join(sorted(
            str(key) for key in row
            if any(token in _key(key) for token in ("volume", "tradedqty", "tradedquantity", "qtytraded"))
        ))
        normalized.append({
          "TckrSymb":symbol, "CompanyName":str(_get(row,ALIASES["company"]) or ""),
          "Series":str(_get(row,ALIASES["series"]) or "").strip().upper(),
          "PageVolume":_volume_number(volume_raw), "LTP":_number(_get(row,ALIASES["ltp"])),
          "ChangePct":_number(_get(row,ALIASES["change_pct"])), "Turnover":_number(_get(row,ALIASES["turnover"])),
          "AvgVolume1W":_number(_get(row,ALIASES["avg_volume_1w"])),
          "VolumeChangePct1W":_number(_get(row,ALIASES["change_pct_1w"])),
          "AvgVolume2W":_number(_get(row,ALIASES["avg_volume_2w"])),
          "VolumeChangePct2W":_number(_get(row,ALIASES["change_pct_2w"])),
          "VolumeChangeTimes1W":_number(_get(row,ALIASES["change_times_1w"])),
          "VolumeChangeTimes2W":_number(_get(row,ALIASES["change_times_2w"])),
          "PageVolumeDataStatus":"DATA_FOUND" if _volume_number(volume_raw) is not None else "MISSING_FROM_NSE_RESPONSE",
          "PageVolumeSourceField":volume_field,
          "PageVolumeRawValue":"" if volume_raw is None else str(volume_raw),
          "NSEPayloadKeys":payload_keys,
          "NSEPayloadVolumeLikeFields":volume_like_fields,
          "NSEUpdatedAt":str(_get(row,ALIASES["updated_at"]) or ""),
          "NSEServerDateIST":server_date,
          "NSEFetchCapturedAtIST":fetched_at,
        })
    frame=pd.DataFrame(normalized)
    if frame.empty: raise RuntimeError("WAIT_FOR_DATA: NSE response contained no valid symbols")
    return frame.drop_duplicates("TckrSymb",keep="first")
def _build_nse_page_download(page, mainboard_symbols, mode, scan_date, captured_at, board_source):
    """Preserve every NSE Volume Gainers page row and label Main Board eligibility."""
    result = page.copy()
    eligible_symbols = {str(symbol).strip().upper() for symbol in mainboard_symbols}
    result["ScanMode"] = str(mode).strip().upper()
    result["ScanDateIST"] = str(scan_date)
    result["PageCapturedAtIST"] = str(captured_at)
    result["NSEPageURL"] = NSE_PAGE
    result["MainBoardEligible"] = result["TckrSymb"].astype(str).str.strip().str.upper().isin(eligible_symbols)
    result["PageUniverseStatus"] = result["MainBoardEligible"].map({
        True: "PASS_MAIN_BOARD_EQUITY",
        False: "PAGE_ROW_NOT_IN_OFFICIAL_MAIN_BOARD_UNIVERSE",
    })
    result["MainBoardSource"] = board_source
    return result


def _eligible_page_equities(page):
    mainboard, source=load_official_mainboard_symbols()
    eligible=page[page["TckrSymb"].isin(mainboard)].copy()
    eligible["PageUniverseStatus"]="PASS_MAIN_BOARD_EQUITY"
    return eligible,source
def _ecms_free_source_evidence(row):
    """Describe free-source evidence without rewriting the shared provider status."""
    raw = row.get("FreeSourcesAlternatesJSON", "")
    try:
        parsed = json.loads(str(raw)) if str(raw).strip() not in {"", "nan", "None"} else {}
    except (TypeError, ValueError):
        parsed = {}
    observed = {
        str(metric): values for metric, values in parsed.items()
        if isinstance(values, list) and values
    } if isinstance(parsed, dict) else {}
    count = len(observed)
    existing = str(row.get("FreeSourcesStatus", "") or "").strip().upper()
    if existing == "DATA_FOUND":
        status = "DATA_FOUND_CURRENT_ATTEMPT"
    elif count:
        status = "HISTORICAL_ALTERNATES_PRESENT_NO_CURRENT_METRICS"
    elif existing:
        status = existing
    else:
        status = "NO_RECORDED_FREE_SOURCE_EVIDENCE"
    return pd.Series({
        "ECMSFreeSourcesEvidenceStatus": status,
        "ECMSFreeSourcesObservedMetricCount": count,
        "ECMSFreeSourcesObservedMetrics": ";".join(sorted(observed)),
    })


def assess_page_fundamentals(candidates, eod_date):
    """Collect and verify fundamentals for Volume Gainers candidates only.

    Reuses the repository's tested fundamental_data_provider and XBRL verifier,
    but runs them inside an ECMS-only workspace so production caches/reports are
    never modified by this shadow scanner.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ecms_output_dir = OUTPUT_DIR.resolve()
    candidate_symbols = set(candidates["TckrSymb"].astype(str).str.strip().str.upper())
    workspace = (STATE_DIR / "fundamental_workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    workspace_metrics = workspace / "data" / "inputs" / "fundamental_metrics.csv"
    workspace_filings = workspace / "outputs" / "v8_official_financial_results_filings.csv"
    workspace_evidence = workspace / "data" / "inputs" / "fundamental_metric_verification_evidence.csv"
    workspace_metrics.parent.mkdir(parents=True, exist_ok=True)
    workspace_filings.parent.mkdir(parents=True, exist_ok=True)
    workspace_evidence.parent.mkdir(parents=True, exist_ok=True)

    # Seed only the current Volume Gainers symbols from the shared read-only cache.
    # Once ECMS has its own cache, keep it as the source for subsequent EOD runs.
    if not workspace_metrics.exists() and METRICS_PATH.exists():
        shared = pd.read_csv(METRICS_PATH)
        if "TckrSymb" not in shared.columns:
            raise RuntimeError("Shared fundamental cache has no TckrSymb column")
        shared["TckrSymb"] = shared["TckrSymb"].astype(str).str.strip().str.upper()
        shared = shared[shared["TckrSymb"].isin(candidate_symbols)].copy()
        shared.to_csv(workspace_metrics, index=False)

    # Reuse official filing/evidence rows for these symbols only; the collector
    # refreshes missing filing metadata inside the isolated workspace.
    if not workspace_filings.exists() and FILINGS_PATH.exists():
        filings = pd.read_csv(FILINGS_PATH)
        if "TckrSymb" in filings.columns:
            filings["TckrSymb"] = filings["TckrSymb"].astype(str).str.strip().str.upper()
            filings = filings[filings["TckrSymb"].isin(candidate_symbols)].copy()
        filings.to_csv(workspace_filings, index=False)
    if not workspace_evidence.exists() and EVIDENCE_PATH.exists():
        evidence = pd.read_csv(EVIDENCE_PATH, keep_default_na=False)
        if "TckrSymb" in evidence.columns:
            evidence["TckrSymb"] = evidence["TckrSymb"].astype(str).str.strip().str.upper()
            evidence = evidence[evidence["TckrSymb"].isin(candidate_symbols)].copy()
        evidence.to_csv(workspace_evidence, index=False)

    repo_root = Path.cwd().resolve()
    ephemeral_root = (ecms_output_dir / "xbrl_ephemeral" / eod_date.isoformat()).resolve()
    if ephemeral_root.exists():
        shutil.rmtree(ephemeral_root)
    ephemeral_root.mkdir(parents=True, exist_ok=True)

    previous_free_budget = os.environ.get("FREE_FUNDAMENTAL_MAX_SYMBOLS_PER_RUN")
    try:
        configured_budget = int(previous_free_budget or "10")
    except (TypeError, ValueError):
        configured_budget = 10
    # The shared provider has a per-run secondary-source budget. Raise it only
    # inside this ECMS process to at least the current page size, so no current
    # Volume Gainers candidate is deferred solely because the page grew.
    os.environ["FREE_FUNDAMENTAL_MAX_SYMBOLS_PER_RUN"] = str(
        max(0, configured_budget, len(candidate_symbols))
    )
    try:
        # Relative paths used by the production collector now resolve beneath
        # data/cache/ecms/fundamental_workspace, not production data/inputs/outputs.
        os.chdir(workspace)
        from fundamental_data_provider import collect_missing_fundamentals
        from strategies.ecms.free_fundamental_sources import fetch_ecms_free_fundamental_sources
        collect_missing_fundamentals(
            candidates,
            metrics_path=Path("data/inputs/fundamental_metrics.csv"),
            enabled=True,
            asof_date=eod_date,
            free_source_fetcher=fetch_ecms_free_fundamental_sources,
            force_retry_incomplete=False,
            free_source_audit_metrics=[
                "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
                "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
            ],
        )
    except Exception as exc:
        failed = candidates.copy()
        failed["FundamentalShortlistStatus"] = "WAIT_FOR_DATA"
        failed["FundamentalShortlistReason"] = (
            f"FUNDAMENTAL_COLLECTION_ERROR:{type(exc).__name__}:{str(exc)[:300]}"
        )
        failed["FundamentalAssessmentStatus"] = failed["FundamentalShortlistStatus"]
        failed["FundamentalAssessmentReason"] = failed["FundamentalShortlistReason"]
        failed["FundamentalResearchClassification"] = "INSUFFICIENT_DATA"
        failed["FundamentalResearchScore"] = pd.NA
        failed["FundamentalResearchCoveragePct"] = 0.0
        failed["FundamentalResearchProvenanceStatus"] = "NO_ELIGIBLE_METRICS"
        decision_fields = pd.DataFrame(
            failed["FundamentalShortlistStatus"].map(_fundamental_decision_fields).tolist(),
            index=failed.index,
        )
        for column in decision_fields.columns:
            failed[column] = decision_fields[column]
        pd.DataFrame([{
            "Status": "FUNDAMENTAL_COLLECTION_ERROR",
            "Reason": f"{type(exc).__name__}: {str(exc)[:500]}",
        }]).to_csv(ecms_output_dir / "fundamental_collection_error.csv", index=False)
        return failed
    finally:
        os.chdir(repo_root)
        if previous_free_budget is None:
            os.environ.pop("FREE_FUNDAMENTAL_MAX_SYMBOLS_PER_RUN", None)
        else:
            os.environ["FREE_FUNDAMENTAL_MAX_SYMBOLS_PER_RUN"] = previous_free_budget

    if not workspace_metrics.exists():
        raise RuntimeError("Fundamental provider completed without creating its ECMS metrics cache")

    # Copy only prior evidence XMLs referenced by the candidate ledger into an
    # ephemeral root. New XBRL downloads are also written there by run_audit.
    if workspace_evidence.exists() and workspace_evidence.stat().st_size > 0:
        evidence = pd.read_csv(workspace_evidence, keep_default_na=False)
        if "TckrSymb" in evidence.columns:
            evidence["TckrSymb"] = evidence["TckrSymb"].astype(str).str.strip().str.upper()
            evidence = evidence[evidence["TckrSymb"].isin(candidate_symbols)].copy()
        if "EvidenceFilePath" in evidence.columns:
            for raw_path in evidence["EvidenceFilePath"].dropna().astype(str).unique():
                if not raw_path.strip():
                    continue
                source = (repo_root / raw_path).resolve()
                try:
                    source.relative_to(repo_root)
                except ValueError:
                    continue
                if source.is_file():
                    destination = ephemeral_root / raw_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)

    metrics = pd.read_csv(workspace_metrics)
    if "TckrSymb" not in metrics.columns:
        raise RuntimeError("ECMS fundamental cache has no TckrSymb column")
    metrics["TckrSymb"] = metrics["TckrSymb"].astype(str).str.strip().str.upper()
    duplicate_symbols = set(metrics.loc[metrics["TckrSymb"].duplicated(keep=False), "TckrSymb"])
    metrics_unique = metrics.drop_duplicates("TckrSymb", keep="first").copy()

    # The ECMS workspace cache is intentionally persistent and may contain
    # symbols seen on earlier Volume Gainers pages. The verifier's symbols
    # argument limits generated XML evidence, not the rows it audits. Build
    # candidate-scoped input snapshots so this run's verification detail and
    # summaries can never include stale/non-page symbols. Keep the persistent
    # workspace untouched for safe cache reuse on later runs.
    audit_input_dir = ephemeral_root / "audit_input"
    audit_input_dir.mkdir(parents=True, exist_ok=True)
    candidate_metrics = metrics[metrics["TckrSymb"].isin(candidate_symbols)].copy()
    if not candidate_metrics.empty:
        free_source_evidence = candidate_metrics.apply(_ecms_free_source_evidence, axis=1)
        candidate_metrics = pd.concat([candidate_metrics, free_source_evidence], axis=1)
    else:
        candidate_metrics["ECMSFreeSourcesEvidenceStatus"] = pd.Series(dtype=str)
        candidate_metrics["ECMSFreeSourcesObservedMetricCount"] = pd.Series(dtype=int)
        candidate_metrics["ECMSFreeSourcesObservedMetrics"] = pd.Series(dtype=str)
    audit_metrics_path = audit_input_dir / "fundamental_metrics.csv"
    candidate_metrics.to_csv(audit_metrics_path, index=False)

    candidate_filings = (
        pd.read_csv(workspace_filings)
        if workspace_filings.exists() and workspace_filings.stat().st_size > 0 else pd.DataFrame()
    )
    if "TckrSymb" in candidate_filings.columns:
        candidate_filings["TckrSymb"] = candidate_filings["TckrSymb"].astype(str).str.strip().str.upper()
        candidate_filings = candidate_filings[
            candidate_filings["TckrSymb"].isin(candidate_symbols)
        ].copy()
    audit_filings_path = audit_input_dir / "official_filings.csv"
    if len(candidate_filings.columns):
        candidate_filings.to_csv(audit_filings_path, index=False)

    candidate_evidence = (
        pd.read_csv(workspace_evidence, keep_default_na=False)
        if workspace_evidence.exists() and workspace_evidence.stat().st_size > 0 else pd.DataFrame()
    )
    if "TckrSymb" in candidate_evidence.columns:
        candidate_evidence["TckrSymb"] = candidate_evidence["TckrSymb"].astype(str).str.strip().str.upper()
        candidate_evidence = candidate_evidence[
            candidate_evidence["TckrSymb"].isin(candidate_symbols)
        ].copy()
    audit_evidence_path = audit_input_dir / "metric_verification_evidence.csv"
    if len(candidate_evidence.columns):
        candidate_evidence.to_csv(audit_evidence_path, index=False)

    verification = pd.DataFrame()
    try:
        verification, verification_summary, filing_summary = run_fundamental_xbrl_audit(
            metrics_path=audit_metrics_path,
            filings_path=audit_filings_path,
            evidence_path=audit_evidence_path,
            output_dir=ecms_output_dir,
            repo_root=ephemeral_root,
            symbols=candidate_symbols,
        )
        verification_summary.to_csv(ecms_output_dir / "fundamental_metric_verification_summary.csv", index=False)
        filing_summary.to_csv(ecms_output_dir / "fundamental_filing_metadata_summary.csv", index=False)
    except Exception as exc:
        pd.DataFrame([{
            "Status": "XBRL_AUDIT_WAIT_FOR_DATA",
            "Reason": f"{type(exc).__name__}: {str(exc)[:500]}",
        }]).to_csv(ecms_output_dir / "fundamental_xbrl_audit_error.csv", index=False)

    candidate_verification = verification[
        verification["TckrSymb"].astype(str).str.upper().isin(candidate_symbols)
    ] if "TckrSymb" in verification.columns else verification.iloc[0:0]

    # Separate ECMS-only Debt/Equity reconciliation. This diagnostic does not
    # alter the strict shortlist or the shared V8 verifier.
    try:
        debt_equity_metrics = metrics_unique[
            metrics_unique["TckrSymb"].astype(str).str.upper().isin(candidate_symbols)
        ].copy()
        debt_equity_audit = audit_ecms_debt_to_equity(
            metrics=debt_equity_metrics,
            filings=candidate_filings,
            repo_root=ephemeral_root,
            symbols=candidate_symbols,
        )
    except Exception as exc:
        debt_equity_audit = pd.DataFrame([
            {
                **{column: "" for column in DEBT_EQUITY_AUDIT_COLUMNS},
                "TckrSymb": symbol,
                "DebtToEquityAuditStatus": "AUDIT_EXECUTION_ERROR",
                "DebtToEquityAuditReason": f"{type(exc).__name__}: {str(exc)[:400]}",
            }
            for symbol in sorted(candidate_symbols)
        ], columns=DEBT_EQUITY_AUDIT_COLUMNS)
    if "TckrSymb" not in debt_equity_audit.columns:
        debt_equity_audit = pd.DataFrame(columns=DEBT_EQUITY_AUDIT_COLUMNS)
    else:
        debt_equity_audit["TckrSymb"] = debt_equity_audit["TckrSymb"].astype(str).str.strip().str.upper()
    # Keep exactly one diagnostic row per current page symbol, including
    # candidates with no fundamental metrics yet.
    debt_equity_audit = debt_equity_audit.drop_duplicates("TckrSymb", keep="first")
    missing_debt_symbols = candidate_symbols - set(debt_equity_audit["TckrSymb"])
    if missing_debt_symbols:
        missing_rows = pd.DataFrame([
            {
                **{column: "" for column in DEBT_EQUITY_AUDIT_COLUMNS},
                "TckrSymb": symbol,
                "DebtToEquityAuditStatus": "CANDIDATE_METRICS_MISSING",
                "DebtToEquityAuditReason": "No candidate-scoped fundamental metrics row is available",
            }
            for symbol in sorted(missing_debt_symbols)
        ], columns=DEBT_EQUITY_AUDIT_COLUMNS)
        debt_equity_audit = pd.concat([debt_equity_audit, missing_rows], ignore_index=True)
    debt_equity_audit = debt_equity_audit[
        debt_equity_audit["TckrSymb"].isin(candidate_symbols)
    ].sort_values("TckrSymb").reset_index(drop=True)
    debt_equity_audit.to_csv(
        ecms_output_dir / "fundamental_debt_equity_xbrl_audit.csv", index=False
    )
    # Compile each source as a separate metric observation. Free Screener and
    # BSE values are optional manual observations; neither can satisfy XBRL verification.
    manual_observations_path = Path("strategies/ecms/inputs/fundamental_manual_observations.csv")
    manual_observations = (
        pd.read_csv(manual_observations_path, keep_default_na=False)
        if manual_observations_path.is_file() else pd.DataFrame()
    )
    source_compilation = build_fundamental_source_compilation(
        candidate_metrics,
        candidate_verification,
        manual_observations,
        debt_equity_audit,
    )
    source_compilation.to_csv(
        ecms_output_dir / "fundamental_source_compilation.csv", index=False
    )

    # Filing metadata is audited independently: XML attachment, Details URL,
    # audit label and reporting basis must remain separate explicit fields.
    # The current shared cache may not contain these fields; that is reported
    # as incomplete and never promotes any metric to verified.
    try:
        # Discover filings by symbol even when the fundamental cache has no
        # FinancialPeriodEnd. The NSE API's period_ended=all response is filtered
        # locally to the latest eligible period at/before the ECMS as-of date.
        # Standalone/consolidated and original/revised variants remain separate.
        filing_lookup_candidates = candidates[["TckrSymb"]].copy()
        filing_lookup_candidates["TckrSymb"] = (
            filing_lookup_candidates["TckrSymb"].astype(str).str.strip().str.upper()
        )
        filing_metadata_source = fetch_ecms_candidate_filing_metadata(
            filing_lookup_candidates, eod_date.isoformat()
        )
        filing_metadata_audit = audit_ecms_filing_metadata(filing_metadata_source)
        filing_metadata_audit = fetch_ecms_details_remarks(filing_metadata_audit)
    except Exception as exc:
        filing_metadata_audit = pd.DataFrame([{
            **{column: "" for column in FILING_METADATA_AUDIT_COLUMNS},
            "TckrSymb": symbol,
            "FilingMetadataStatus": "AUDIT_EXECUTION_ERROR",
            "VerificationStatus": "NOT_VERIFIED",
            "VerificationWarning": f"{type(exc).__name__}: {str(exc)[:250]}",
        } for symbol in sorted(candidate_symbols)], columns=FILING_METADATA_AUDIT_COLUMNS)
    filing_metadata_audit.to_csv(
        ecms_output_dir / "fundamental_filing_metadata_audit.csv", index=False
    )

    # Feed this run's fresh NSE filing lookup into ratio discovery. Never fall
    # back to the older V8 cache here: that was the previous integration gap.
    # Only explicit, non-ambiguous metadata with an official XML URL and a
    # publication date on/before the run date can enter candidate discovery.
    try:
        filing_rows = filing_metadata_audit.copy()
        if not filing_rows.empty:
            publication_dates = pd.to_datetime(
                filing_rows.get("PublicationDate", pd.Series(index=filing_rows.index, dtype=str)),
                errors="coerce",
            ).dt.date
            filing_rows["PublicationDateStatus"] = [
                "VERIFIED" if (
                    pd.notna(value)
                    and value <= eod_date
                    and str(filing_rows.iloc[index].get("FilingMetadataStatus", "")) == "EXPLICIT_METADATA_CAPTURED"
                    and str(filing_rows.iloc[index].get("XBRLURLStatus", "")) == "PASS"
                ) else "BLOCKED"
                for index, value in enumerate(publication_dates)
            ]
            filing_rows["OfficialFilingURL"] = filing_rows.get("XBRLURL", "")
            ratio_filings = filing_rows
            ratio_candidates = filing_rows[["TckrSymb", "FinancialPeriodEnd"]].drop_duplicates().copy()
        else:
            ratio_filings = pd.DataFrame()
            ratio_candidates = pd.DataFrame(columns=["TckrSymb", "FinancialPeriodEnd"])
        represented = set(ratio_candidates.get("TckrSymb", pd.Series(dtype=str)).astype(str).str.upper())
        missing = sorted(candidate_symbols - represented)
        if missing:
            ratio_candidates = pd.concat([
                ratio_candidates,
                pd.DataFrame([{"TckrSymb": symbol, "FinancialPeriodEnd": ""} for symbol in missing]),
            ], ignore_index=True)
        ratio_discovery = discover_ecms_ratio_xbrl_facts(
            candidates=ratio_candidates,
            filings=ratio_filings,
            repo_root=ephemeral_root,
            symbols=candidate_symbols,
        )
    except Exception as exc:
        ratio_discovery = pd.DataFrame([
            {
                **{column: "" for column in RATIO_XBRL_DISCOVERY_COLUMNS},
                "TckrSymb": symbol,
                "DiscoveryStatus": "DISCOVERY_EXECUTION_ERROR",
                "VerificationWarning": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
            for symbol in sorted(candidate_symbols)
        ], columns=RATIO_XBRL_DISCOVERY_COLUMNS)
    ratio_discovery.to_csv(
        ecms_output_dir / "fundamental_ratio_xbrl_discovery.csv", index=False
    )

    joined = candidates.merge(metrics_unique, on="TckrSymb", how="left", suffixes=("", "_fundamental"))
    assessed = build_fundamental_shortlist(
        joined, eod_date.isoformat(), write=False,
        metric_verification=candidate_verification,
        require_explicit_thresholds=True,
        thresholds_path=THRESHOLDS_PATH.resolve(),
    )
    expected_symbols = candidates["TckrSymb"].astype(str).str.strip().str.upper().tolist()
    actual_symbols = assessed["TckrSymb"].astype(str).str.strip().str.upper().tolist()
    if len(actual_symbols) != len(expected_symbols) or set(actual_symbols) != set(expected_symbols) or len(actual_symbols) != len(set(actual_symbols)):
        raise RuntimeError(
            "ECMS_ASSESSMENT_INTEGRITY_ERROR: candidate and assessment row/symbol sets differ"
        )
    duplicated = assessed["TckrSymb"].astype(str).str.upper().isin(duplicate_symbols)
    assessed.loc[duplicated, "FundamentalShortlistStatus"] = "WAIT_FOR_DATA"
    assessed.loc[duplicated, "FundamentalShortlistReason"] = "DUPLICATE_FUNDAMENTAL_CACHE_ROWS"
    assessed.loc[duplicated, "FundamentalAssessmentStatus"] = assessed.loc[duplicated, "FundamentalShortlistStatus"]
    assessed.loc[duplicated, "FundamentalAssessmentReason"] = assessed.loc[duplicated, "FundamentalShortlistReason"]
    # Fundamentals are one evidence layer, not the overall stock decision.
    # Only a complete, current, aligned and officially verified FAIL may act as
    # a fundamental rejection gate. WAIT_FOR_DATA must continue through every
    # other research layer; PASS still requires balanced downstream review.
    fundamental_pass = assessed["FundamentalShortlistStatus"].astype(str).str.upper().eq("PASS")
    assessed["FundamentalPassStatus"] = fundamental_pass.map({
        True: "FUNDAMENTAL_PASS", False: "NOT_FUNDAMENTAL_PASS"
    })
    decision_fields = pd.DataFrame(
        assessed["FundamentalShortlistStatus"].map(_fundamental_decision_fields).tolist(),
        index=assessed.index,
    )
    for column in decision_fields.columns:
        assessed[column] = decision_fields[column]

    # Publish current-page candidate snapshots, not the full persistent cache
    # or filing register. The workspace itself remains intact for later reuse.
    candidate_metrics.to_csv(ecms_output_dir / "fundamental_metrics_ecms.csv", index=False)
    comparison_rows = []
    comparison_metrics = [
        "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
        "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
    ]
    for _, metric_row in candidate_metrics.iterrows():
        raw_comparison = metric_row.get("FreeSourcesComparisonJSON", "{}")
        try:
            comparison = json.loads(str(raw_comparison)) if pd.notna(raw_comparison) else {}
        except (TypeError, ValueError):
            comparison = {}
        metadata_maps = {}
        for field_name in ("MetricSourcesJSON", "MetricSourcePeriodsJSON", "MetricCalculationBasesJSON"):
            try:
                parsed = json.loads(str(metric_row.get(field_name, "{}")))
                metadata_maps[field_name] = parsed if isinstance(parsed, dict) else {}
            except (TypeError, ValueError):
                metadata_maps[field_name] = {}
        for metric_name in comparison_metrics:
            observed = comparison.get(metric_name, {}) if isinstance(comparison, dict) else {}
            yahoo = observed.get("YahooFinance", {}) if isinstance(observed, dict) else {}
            secondary = observed.get("secondary_sources", []) if isinstance(observed, dict) else []
            base = {
                "TckrSymb": str(metric_row.get("TckrSymb", "")).strip().upper(),
                "MetricName": metric_name,
                "YahooValue": yahoo.get("value", metric_row.get(metric_name, "")),
                "YahooSource": yahoo.get("source", metadata_maps["MetricSourcesJSON"].get(metric_name, "NOT_AVAILABLE")),
                "YahooPeriod": yahoo.get("period", metadata_maps["MetricSourcePeriodsJSON"].get(metric_name, "")),
                "YahooCalculationBasis": yahoo.get("calculation_basis", metadata_maps["MetricCalculationBasesJSON"].get(metric_name, "")),
                "ComparisonStatus": observed.get("comparison_status", "NO_SECONDARY_OBSERVATION") if isinstance(observed, dict) else "NO_SECONDARY_OBSERVATION",
            }
            if isinstance(secondary, list) and secondary:
                for item in secondary:
                    comparison_rows.append({
                        **base,
                        "SecondarySource": item.get("source", ""),
                        "SecondaryValue": item.get("value", ""),
                        "SecondaryPeriod": item.get("period", ""),
                        "SecondarySourceURL": item.get("source_url", ""),
                        "ReconciliationStatus": "NOT_OFFICIALLY_VERIFIED",
                    })
            else:
                comparison_rows.append({
                    **base, "SecondarySource": "", "SecondaryValue": "",
                    "SecondaryPeriod": "", "SecondarySourceURL": "",
                    "ReconciliationStatus": "NO_SECONDARY_OBSERVATION",
                })
    pd.DataFrame(comparison_rows, columns=[
        "TckrSymb", "MetricName", "YahooValue", "YahooSource", "YahooPeriod",
        "YahooCalculationBasis", "SecondarySource", "SecondaryValue",
        "SecondaryPeriod", "SecondarySourceURL", "ComparisonStatus",
        "ReconciliationStatus",
    ]).to_csv(ecms_output_dir / "fundamental_source_comparison_ecms.csv", index=False)
    candidate_filings.to_csv(ecms_output_dir / "fundamental_filings_ecms.csv", index=False)
    candidate_evidence.to_csv(ecms_output_dir / "fundamental_evidence_ecms.csv", index=False)

    # Per-stock/per-metric coverage report shared by both scan modes.
    required_metrics = [
        "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
        "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
    ]
    metric_audit_rows = source_compilation[
        source_compilation.get("Source", pd.Series("", index=source_compilation.index))
        .astype(str).str.upper().str.startswith("NSE_OFFICIAL_XBRL")
    ].copy()
    metric_detail_rows, metric_summary_rows = [], []
    metrics_by_symbol = candidate_metrics.set_index("TckrSymb", drop=False)
    for symbol in sorted(candidate_symbols):
        metric_row = metrics_by_symbol.loc[symbol] if symbol in metrics_by_symbol.index else pd.Series(dtype=object)
        if isinstance(metric_row, pd.DataFrame):
            metric_row = metric_row.iloc[0]
        populated = verified = mismatch = reconciliation = filing_unconfirmed = 0
        missing_names = []
        for metric_name in required_metrics:
            raw_value = metric_row.get(metric_name, pd.NA)
            value = pd.to_numeric(pd.Series([raw_value]), errors="coerce").iloc[0]
            has_value = pd.notna(value)
            populated += int(has_value)
            if not has_value:
                missing_names.append(metric_name)
            audit_match = metric_audit_rows[
                metric_audit_rows["TckrSymb"].astype(str).str.upper().eq(symbol)
                & metric_audit_rows["MetricName"].astype(str).eq(metric_name)
            ]
            audit = audit_match.iloc[0].to_dict() if not audit_match.empty else {}
            verification_status = str(audit.get("VerificationStatus", "NOT_VERIFIED") or "NOT_VERIFIED").upper()
            verified += int(verification_status == "OFFICIAL_XBRL_VERIFIED")
            mismatch += int(verification_status == "PROVIDER_VALUE_MISMATCH")
            reconciliation += int(verification_status == "DERIVED_RECONCILIATION_REQUIRED")
            filing_unconfirmed += int(verification_status == "FILING_METADATA_NOT_CONFIRMED")
            value_provenance = _metric_value_provenance(metric_row, metric_name)
            metric_detail_rows.append({
                "TckrSymb": symbol, "MetricName": metric_name,
                "MetricValue": raw_value if has_value else "",
                "ValueAvailable": bool(has_value),
                "FinancialPeriodEnd": value_provenance["ValuePeriodEnd"] or metric_row.get("FinancialPeriodEnd", ""),
                "PublicationDate": metric_row.get("PublicationDate", ""),
                "CalculationBasis": value_provenance["ValueBasis"] or metric_row.get("MetricCalculationBasis", ""),
                "MetricSource": value_provenance["ValueSource"],
                "MetricSourceURL": value_provenance["ValueSourceURL"],
                "MetricSourcePeriodEnd": value_provenance["ValuePeriodEnd"],
                "MetricSourceBasis": value_provenance["ValueBasis"],
                "MetricUnit": value_provenance["ValueUnit"],
                "MetricCurrency": value_provenance["ValueCurrency"],
                "OfficialFilingSource": audit.get("Source", "NOT_FOUND"),
                "OfficialFilingURL": audit.get("SourceURL", ""),
                "VerificationStatus": verification_status,
                "MismatchReason": audit.get("MismatchReason", ""),
            })
        metric_summary_rows.append({
            "TckrSymb": symbol,
            "FundamentalMetricsPopulatedCount": populated,
            "FundamentalMetricsMissingCount": len(required_metrics) - populated,
            "FundamentalMetricsOfficiallyVerifiedCount": verified,
            "FundamentalMetricsMismatchCount": mismatch,
            "FundamentalMetricsReconciliationRequiredCount": reconciliation,
            "FundamentalMetricsFilingMetadataNotConfirmedCount": filing_unconfirmed,
            "FundamentalMetricsMissingNames": ";".join(missing_names),
            "FundamentalMetricsCoverageStatus": "ALL_7_POPULATED" if populated == len(required_metrics) else "PARTIAL_DATA",
            "FundamentalMetricPeriod": metric_row.get("FinancialPeriodEnd", ""),
            "FundamentalMetricBasis": metric_row.get("MetricCalculationBasis", ""),
        })
    pd.DataFrame(metric_detail_rows).to_csv(
        ecms_output_dir / "fundamental_metric_coverage_by_stock.csv", index=False
    )
    metric_summary = pd.DataFrame(metric_summary_rows)
    assessed = assessed.merge(metric_summary, on="TckrSymb", how="left", validate="one_to_one")

    provider_diagnostics = workspace / "outputs" / "v8_fundamental_provider_diagnostics.csv"
    if provider_diagnostics.exists():
        diagnostics = pd.read_csv(provider_diagnostics)
        symbol_column = "TckrSymb" if "TckrSymb" in diagnostics.columns else (
            "Symbol" if "Symbol" in diagnostics.columns else None
        )
        if symbol_column:
            diagnostics[symbol_column] = diagnostics[symbol_column].astype(str).str.strip().str.upper()
            diagnostics = diagnostics[diagnostics[symbol_column].isin(candidate_symbols)].copy()
        diagnostics.to_csv(ecms_output_dir / "fundamental_provider_diagnostics.csv", index=False)
    return assessed

def attach_page_rvol(candidates, eod_date):
    """Attach the repository's 20-session Bhavcopy RVOL without changing page membership."""
    result = candidates.copy()
    try:
        latest, latest_path = discover_latest_session()
        if latest != eod_date:
            raise RuntimeError(f"Bhavcopy latest session {latest} does not match page EOD date {eod_date}")
        history = load_prior_sessions(latest)
        current = _read_valid_bhavcopy(latest_path, latest)
        rvol = calculate_rvol(current, [frame for _, frame in history])
        rvol = rvol[rvol["TckrSymb"].astype(str).str.upper().isin(
            set(result["TckrSymb"].astype(str).str.upper())
        )][["TckrSymb", "AvgVolume20D", "RVOL", "VolumeScreenStatus"]]
        result = result.merge(rvol, on="TckrSymb", how="left", validate="one_to_one")
        result["RVOLDataStatus"] = result["VolumeScreenStatus"].fillna("WAIT_FOR_DATA")
    except Exception as exc:
        result["AvgVolume20D"] = pd.NA
        result["RVOL"] = pd.NA
        result["VolumeScreenStatus"] = "WAIT_FOR_DATA"
        result["RVOLDataStatus"] = f"WAIT_FOR_DATA:{type(exc).__name__}:{str(exc)[:180]}"
    return result

def attach_information(assessed, as_of_date):
    """Attach research to every eligible page symbol, independent of fundamentals."""
    result = attach_valuation(assessed)
    symbols = result["TckrSymb"].astype(str).str.strip().str.upper()
    all_symbols = sorted(set(symbols))

    news, news_audit = collect_catalysts(result.copy(), as_of_date)
    events, event_audit = collect_upcoming_events(all_symbols, as_of_date)
    deals, deal_audit = collect_bulk_block_deals(all_symbols, as_of_date)
    corporate_actions, corporate_actions_audit = collect_corporate_actions(all_symbols, as_of_date)

    news_defaults = {
        "NewsWindowStart": "", "NewsWindowEnd": "",
        "OfficialStatus": "SOURCE_UNAVAILABLE",
        "SecondaryStatus": "SOURCE_UNAVAILABLE",
        "CatalystStatus": "SOURCE_UNAVAILABLE",
        "CatalystSignalStatus": "NOT_VERIFIED",
        "StrongCatalystCount": 0, "NegativeRiskCount": 0,
        "OfficialCount": 0, "SecondaryCount": 0,
    }
    if not news_audit.empty:
        result = result.drop(columns=[
            c for c in news_audit.columns if c != "TckrSymb" and c in result.columns
        ]).merge(news_audit, on="TckrSymb", how="left", validate="one_to_one")
    for column, default in news_defaults.items():
        if column not in result.columns:
            result[column] = default
        else:
            result[column] = result[column].fillna(default)

    summaries = {}
    if not news.empty:
        for symbol, rows in news.groupby(news["TckrSymb"].astype(str).str.upper()):
            summaries[symbol] = " | ".join(
                f"{row.get('PublishedDate','')}: {row.get('Headline','')}"
                for _, row in rows.sort_values("PublishedDate", ascending=False).head(5).iterrows()
            )
    result["Last5DayNews"] = [
        summaries.get(symbol, "NO_NEWS_FOUND" if str(status).upper() == "NO_NEWS_FOUND"
                      else "WAIT_FOR_DATA" if str(status).upper() == "WAIT_FOR_DATA"
                      else "NO_MATCHED_NEWS_IN_LOOKBACK")
        for symbol, status in zip(symbols, result["CatalystStatus"])
    ]
    result["NewsResearchStatus"] = result["CatalystStatus"].astype(str).str.upper().map(
        lambda status: "DATA_FOUND" if status in {
            "CATALYST_FOUND", "CATALYST_FOUND_SECONDARY_ONLY"
        } else "NO_DATA_FOUND" if status == "NO_NEWS_FOUND"
        else "SOURCE_UNAVAILABLE" if status == "WAIT_FOR_DATA"
        else "NOT_VERIFIED"
    )

    # Explicit corporate-action view over official disclosures in the same
    # five-trading-session window; this is not a substitute for a dedicated
    # corporate-actions feed until that endpoint is independently validated.
    corporate_pattern = re.compile(
        r"dividend|bonus|stock split|share split|buyback|buy-back|rights issue|"
        r"preferential issue|merger|amalgamation|demerger|scheme of arrangement|"
        r"record date|ex-date|capital reduction|delisting",
        re.IGNORECASE,
    )
    corporate_summaries = {}
    corporate_counts = {}
    if not news.empty:
        official_news = news[
            news.get("SourceType", pd.Series("", index=news.index)).astype(str).str.upper().eq("OFFICIAL")
        ]
        for symbol, rows in official_news.groupby(official_news["TckrSymb"].astype(str).str.upper()):
            matched = rows[
                rows["Headline"].astype(str).apply(lambda headline: bool(corporate_pattern.search(headline)))
            ]
            if not matched.empty:
                corporate_counts[symbol] = int(len(matched))
                corporate_summaries[symbol] = " | ".join(
                    f"{row.get('PublishedDate','')}: {row.get('Headline','')}"
                    for _, row in matched.sort_values("PublishedDate", ascending=False).iterrows()
                )
    result["CorporateActionAnnouncementCount"] = [
        corporate_counts.get(symbol, 0) for symbol in symbols
    ]
    result["CorporateActionAnnouncementSummary"] = [
        corporate_summaries.get(symbol, "") for symbol in symbols
    ]
    result["CorporateActionDisclosureStatus"] = [
        "DATA_FOUND" if symbol in corporate_summaries
        else "NO_DATA_FOUND" if str(official_status).upper() == "AVAILABLE"
        else "SOURCE_UNAVAILABLE"
        for symbol, official_status in zip(symbols, result["OfficialStatus"])
    ]

    corporate_action_defaults = {
        "CorporateActionsStatus": "SOURCE_UNAVAILABLE",
        "CorporateActionCount": 0,
        "CorporateActionSummary": "NOT AVAILABLE",
        "CorporateActionWindowStart": "",
        "CorporateActionWindowEnd": "",
        "CorporateActionSourceURL": "",
    }
    if not corporate_actions_audit.empty:
        result = result.drop(columns=[
            c for c in corporate_actions_audit.columns if c != "TckrSymb" and c in result.columns
        ]).merge(corporate_actions_audit, on="TckrSymb", how="left", validate="one_to_one")
    for column, default in corporate_action_defaults.items():
        if column not in result.columns:
            result[column] = default
        else:
            result[column] = result[column].fillna(default)
    result["CorporateActionResearchStatus"] = result["CorporateActionsStatus"].astype(str).str.upper().map(
        lambda status: "DATA_FOUND" if status == "DATA_FOUND"
        else "NO_DATA_FOUND" if status == "NO_DATA_FOUND"
        else "SOURCE_UNAVAILABLE" if status.startswith("SOURCE_UNAVAILABLE")
        else "NOT_VERIFIED"
    )

    event_defaults = {
        "UpcomingEventsStatus": "SOURCE_UNAVAILABLE",
        "UpcomingEvents": "NOT AVAILABLE",
        "NextResultDate": "NOT ANNOUNCED",
        "NextResultDetails": "",
        "EventCalendarSourceURL": "",
        "UpcomingEventsSourceCoverageStatus": "UNAVAILABLE",
        "EventCalendarSourceStatus": "NOT_VERIFIED",
        "BoardMeetingSourceStatus": "NOT_VERIFIED",
    }
    if not event_audit.empty:
        result = result.drop(columns=[
            c for c in event_audit.columns if c != "TckrSymb" and c in result.columns
        ]).merge(event_audit, on="TckrSymb", how="left", validate="one_to_one")
    for column, default in event_defaults.items():
        if column not in result.columns:
            result[column] = default
        else:
            result[column] = result[column].fillna(default)
    result["UpcomingEventsResearchStatus"] = result["UpcomingEventsStatus"].astype(str).str.upper().map(
        lambda status: "DATA_FOUND" if status == "AVAILABLE"
        else "NO_DATA_FOUND" if status == "NO_CONFIRMED_UPCOMING_EVENTS"
        else "SOURCE_UNAVAILABLE" if status.startswith("WAIT_FOR_DATA")
        else "NOT_VERIFIED"
    )

    deal_defaults = {
        "BulkBlockDealStatus": "SOURCE_UNAVAILABLE",
        "BulkDealCount": 0, "BlockDealCount": 0,
        "BulkDealCountLast5Days": 0, "BlockDealCountLast5Days": 0,
        "BulkBlockSummaryLast5Days": "",
        "BulkBuyers": "", "BulkSellers": "", "BlockBuyers": "", "BlockSellers": "",
        "BulkBlockDealSummary": "",
        "BulkBlockLookbackStart": "", "BulkBlockLookbackEnd": "", "BulkBlockSourceURL": "",
        "BulkDealsSourceStatus": "NOT_VERIFIED", "BlockDealsSourceStatus": "NOT_VERIFIED",
        "BulkBlockSourceCoverageStatus": "UNAVAILABLE",
    }
    if not deal_audit.empty:
        result = result.drop(columns=[
            c for c in deal_audit.columns if c != "TckrSymb" and c in result.columns
        ]).merge(deal_audit, on="TckrSymb", how="left", validate="one_to_one")
    for column, default in deal_defaults.items():
        if column not in result.columns:
            result[column] = default
        else:
            result[column] = result[column].fillna(default)
    def _deal_research_status(row):
        status = str(row.get("BulkBlockDealStatus", "")).upper()
        bulk_count = pd.to_numeric(row.get("BulkDealCount", 0), errors="coerce")
        block_count = pd.to_numeric(row.get("BlockDealCount", 0), errors="coerce")
        count = (0 if pd.isna(bulk_count) else int(bulk_count)) + (0 if pd.isna(block_count) else int(block_count))
        if count > 0:
            return "DATA_FOUND"
        if status == "NO_DISCLOSED_DEALS_IN_LOOKBACK":
            return "NO_DATA_FOUND"
        if status == "WAIT_FOR_DATA":
            return "SOURCE_UNAVAILABLE"
        return "NOT_VERIFIED"
    result["BulkBlockDealsResearchStatus"] = result.apply(_deal_research_status, axis=1)
    result["RVOLInformationStatus"] = result.get(
        "RVOLDataStatus", pd.Series("NOT AVAILABLE", index=result.index)
    )
    return result, news, events, deals, corporate_actions

def _verified_nse_page_session_date(page, scan_date):
    """Require the live NSE API response Date header to match today's IST scan date."""
    if page.empty or "NSEServerDateIST" not in page.columns:
        raise RuntimeError("WAIT_FOR_DATA: NSE live page has no verifiable server Date header")
    server_dates = set(page["NSEServerDateIST"].fillna("").astype(str).str.strip())
    expected = scan_date.isoformat()
    if server_dates != {expected}:
        raise RuntimeError(f"WAIT_FOR_DATA: NSE live page server date {sorted(server_dates)} does not match scan date {expected}")
    return scan_date


def _is_current_run_eod_snapshot_cacheable(marker, rows, github_run_id):
    """Accept only a complete, current-run EOD snapshot for its actual scan session."""
    if not isinstance(marker, dict) or not rows:
        return False
    eod_date = str(marker.get("eod_date", ""))
    try:
        symbol_count = int(marker.get("symbol_count", 0))
    except (TypeError, ValueError):
        return False
    if (
        marker.get("snapshot_type") != "EOD"
        or marker.get("snapshot_status") != "VALID"
        or not github_run_id
        or marker.get("github_run_id") != str(github_run_id)
        or symbol_count <= 0
        or len(rows) != symbol_count
        or not eod_date
        or marker.get("scan_date", "") != eod_date
    ):
        return False
    dates = {str(row.get("EODDate", "")) for row in rows}
    return (
        dates == {eod_date}
        and all(
            row.get("SnapshotType") == "EOD"
            and row.get("SnapshotStatus") == "VALID"
            for row in rows
        )
    )


def _save_eod_snapshot(frame, eod_date):
    """Atomically persist the EOD page universe before optional enrichment can fail."""
    if frame.empty or "TckrSymb" not in frame.columns:
        raise RuntimeError("ECMS_EOD_SNAPSHOT_ERROR: empty page or missing TckrSymb")
    snapshot = frame.copy()
    snapshot["TckrSymb"] = snapshot["TckrSymb"].astype(str).str.strip().str.upper()
    if snapshot["TckrSymb"].eq("").any() or snapshot["TckrSymb"].duplicated().any():
        raise RuntimeError("ECMS_EOD_SNAPSHOT_ERROR: blank or duplicate symbols")
    snapshot["EODDate"] = eod_date.isoformat()
    keep = ["TckrSymb", "CompanyName", "PageVolume", "LTP", "ChangePct", "EODScanDate", "EODScanCapturedAtIST",
            "AvgVolume1W", "VolumeChangePct1W", "AvgVolume2W", "VolumeChangePct2W",
            "VolumeChangeTimes1W", "VolumeChangeTimes2W", "PageVolumeDataStatus",
            "PageVolumeSourceField", "PageVolumeRawValue", "NSEPayloadKeys", "NSEPayloadVolumeLikeFields",
            "NSEServerDateIST", "NSEFetchCapturedAtIST", "BhavcopyDate", "FundamentalMetricsPopulatedCount",
            "FundamentalMetricsMissingCount", "FundamentalMetricsOfficiallyVerifiedCount",
            "FundamentalMetricsMismatchCount", "FundamentalMetricsReconciliationRequiredCount",
            "FundamentalMetricsFilingMetadataNotConfirmedCount", "FundamentalMetricsMissingNames",
            "FundamentalMetricsCoverageStatus", "FundamentalMetricPeriod", "FundamentalMetricBasis",
            "FundamentalDecisionRole", "ResearchContinuationStatus",
            "AvgVolume20D", "RVOL", "RVOLDataStatus", "EODDate"]
    keep = [column for column in keep if column in snapshot.columns]
    state = snapshot[keep].copy()
    if "FundamentalShortlistStatus" in snapshot.columns:
        state["EODFundamentalShortlistStatus"] = snapshot["FundamentalShortlistStatus"].values
    elif "EODFundamentalShortlistStatus" not in state.columns:
        state["EODFundamentalShortlistStatus"] = "NOT_ASSESSED"
    if "StrongFundamentalNotForwardedReason" in snapshot.columns:
        state["EODFundamentalNotForwardedReason"] = snapshot["StrongFundamentalNotForwardedReason"].values
    if "FundamentalPassStatus" in snapshot.columns:
        state["FundamentalPassStatus"] = snapshot["FundamentalPassStatus"].values
    state["EODStrongFundamentalStatus"] = state["EODFundamentalShortlistStatus"].astype(str).str.upper().map({
        "PASS": "EOD_FUNDAMENTAL_PASS", "FAIL": "EOD_FUNDAMENTAL_FAIL",
    }).fillna("EOD_FUNDAMENTAL_WAIT_FOR_DATA")
    if "FundamentalDecisionRole" in snapshot.columns:
        state["FundamentalDecisionRole"] = snapshot["FundamentalDecisionRole"].values
    if "ResearchContinuationStatus" in snapshot.columns:
        state["ResearchContinuationStatus"] = snapshot["ResearchContinuationStatus"].values
    state["SnapshotType"] = "EOD"
    state["SnapshotStatus"] = "VALID"
    state["SnapshotCapturedAtIST"] = datetime.now(IST).isoformat()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    state.to_csv(temporary, index=False)
    temporary.replace(STATE_FILE)
    marker = {
        "snapshot_type": "EOD", "snapshot_status": "VALID",
        "eod_date": eod_date.isoformat(),
        "symbol_count": int(state["TckrSymb"].nunique()),
        "github_run_id": os.getenv("GITHUB_RUN_ID", ""),
        "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", ""),
        "scan_date": str(snapshot.get("EODScanDate", pd.Series([datetime.now(IST).date().isoformat()])).iloc[0]),
        "captured_at_ist": datetime.now(IST).isoformat(),
    }
    (STATE_DIR / "eod_snapshot_run_marker.json").write_text(
        json.dumps(marker, indent=2) + "\n", encoding="utf-8"
    )
    return state



def _consume_previous_eod_snapshot(expected_eod_date):
    """Consume the prior EOD reference only after Morning comparison is complete."""
    if not STATE_FILE.exists():
        raise RuntimeError("ECMS_MORNING_STATE_ERROR: prior EOD reference disappeared before consumption")
    previous = pd.read_csv(STATE_FILE, dtype={"TckrSymb": str})
    if previous.empty or "EODDate" not in previous.columns:
        raise RuntimeError("ECMS_MORNING_STATE_ERROR: prior EOD reference is empty or has no EODDate")
    dates = set(previous["EODDate"].dropna().astype(str))
    if dates != {str(expected_eod_date)}:
        raise RuntimeError(
            f"ECMS_MORNING_STATE_ERROR: refusing to consume EOD reference dates {sorted(dates)}; "
            f"expected {expected_eod_date}"
        )
    # Persist a tombstone before deleting the active CSV. GitHub Actions cache
    # extraction is additive: an older cache can resurrect a deleted file.
    # The consumed-through date prevents that stale EOD CSV being reused.
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    consumed_marker = {
        "consumed_eod_date": str(expected_eod_date),
        "consumed_at_ist": datetime.now(IST).isoformat(),
        "morning_run_id": os.getenv("GITHUB_RUN_ID", ""),
        "morning_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", ""),
        "status": "CONSUMED",
    }
    temporary_marker = CONSUMED_EOD_MARKER_FILE.with_name(
        CONSUMED_EOD_MARKER_FILE.name + ".tmp"
    )
    temporary_marker.write_text(json.dumps(consumed_marker, indent=2) + "\n", encoding="utf-8")
    temporary_marker.replace(CONSUMED_EOD_MARKER_FILE)
    STATE_FILE.unlink()
    marker_path = STATE_DIR / "eod_snapshot_run_marker.json"
    try:
        marker_path.unlink()
    except FileNotFoundError:
        pass
    return True


def _save_same_day_morning_snapshot(frame, morning_date):
    """Persist the full same-day morning page and its assessment/context for EOD reuse."""
    if frame.empty or "TckrSymb" not in frame.columns:
        raise RuntimeError("ECMS_MORNING_SNAPSHOT_ERROR: empty page or missing TckrSymb")
    snapshot = frame.copy()
    snapshot["TckrSymb"] = snapshot["TckrSymb"].astype(str).str.strip().str.upper()
    if snapshot["TckrSymb"].eq("").any() or snapshot["TckrSymb"].duplicated().any():
        raise RuntimeError("ECMS_MORNING_SNAPSHOT_ERROR: blank or duplicate symbols")
    snapshot["MorningDate"] = morning_date.isoformat()
    snapshot["MorningSnapshotSavedAtIST"] = datetime.now(IST).isoformat()
    snapshot["MorningRunId"] = os.getenv("GITHUB_RUN_ID", "")
    snapshot["MorningRunAttempt"] = os.getenv("GITHUB_RUN_ATTEMPT", "")
    snapshot["MorningSnapshotType"] = "MORNING"
    snapshot["MorningSnapshotStatus"] = "VALID"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = MORNING_STATE_FILE.with_name(MORNING_STATE_FILE.name + ".tmp")
    snapshot.to_csv(temporary, index=False)
    temporary.replace(MORNING_STATE_FILE)
    return snapshot


def _load_same_day_morning_snapshot(morning_date):
    """Load only a valid, unique Morning snapshot from the current IST trading date."""
    if not MORNING_STATE_FILE.exists():
        return pd.DataFrame()
    snapshot = pd.read_csv(MORNING_STATE_FILE, dtype={"TckrSymb": str})
    if snapshot.empty or "TckrSymb" not in snapshot.columns:
        return pd.DataFrame()
    snapshot["TckrSymb"] = snapshot["TckrSymb"].astype(str).str.strip().str.upper()
    if snapshot["TckrSymb"].eq("").any() or snapshot["TckrSymb"].duplicated().any():
        return pd.DataFrame()
    if set(snapshot.get("MorningDate", pd.Series(dtype=str)).dropna().astype(str)) != {morning_date.isoformat()}:
        return pd.DataFrame()
    if "MorningSnapshotType" in snapshot and not snapshot["MorningSnapshotType"].astype(str).eq("MORNING").all():
        return pd.DataFrame()
    if "MorningSnapshotStatus" in snapshot and not snapshot["MorningSnapshotStatus"].astype(str).eq("VALID").all():
        return pd.DataFrame()
    return snapshot


def _attach_same_day_morning_confirmation(eod_frame, morning_date, eod_data_date=None):
    """Compare Morning/EOD page presence only when EOD data belongs to this session."""
    result = eod_frame.copy()
    data_date = eod_data_date or morning_date
    if data_date != morning_date:
        # A manual EOD run may still receive the prior session's cached NSE page.
        # Never label those stale rows as same-day repeats or new EOD entries.
        result["MorningSeenSameDay"] = False
        result["MorningToEODStatus"] = "EOD_DATA_DATE_MISMATCH_NOT_COMPARED"
        result["MorningComparisonStatus"] = "STALE_EOD_DATA_NOT_COMPARED"
        result["MorningScanTimeIST"] = ""
        result["MorningPageVolume"] = ""
        result["MorningFundamentalStatus"] = "NOT_AVAILABLE"
        result["MorningNewsContext"] = "NOT AVAILABLE"
        result["MorningUpcomingEvents"] = "NOT AVAILABLE"
        result["MorningNextResultDate"] = "NOT AVAILABLE"
        return result
    morning = _load_same_day_morning_snapshot(morning_date)
    if morning.empty:
        result["MorningSeenSameDay"] = False
        result["MorningToEODStatus"] = "NO_VALID_SAME_DAY_MORNING_SNAPSHOT"
        result["MorningComparisonStatus"] = "NO_VALID_SAME_DAY_MORNING_SNAPSHOT"
        result["MorningScanTimeIST"] = ""
        result["MorningPageVolume"] = ""
        result["MorningFundamentalStatus"] = "NOT_AVAILABLE"
        result["MorningNewsContext"] = "NOT AVAILABLE"
        result["MorningUpcomingEvents"] = "NOT AVAILABLE"
        result["MorningNextResultDate"] = "NOT AVAILABLE"
        return result
    morning_by_symbol = morning.set_index("TckrSymb", drop=False)
    symbols = result["TckrSymb"].astype(str).str.strip().str.upper()
    result["MorningSeenSameDay"] = symbols.isin(set(morning_by_symbol.index))
    result["MorningToEODStatus"] = result["MorningSeenSameDay"].map({
        True: "MORNING_AND_EOD_REPEAT", False: "EOD_NEW_ENTRY"
    })
    result["MorningComparisonStatus"] = "COMPLETED"
    def morning_value(symbol, column, default=""):
        if symbol not in morning_by_symbol.index or column not in morning_by_symbol.columns:
            return default
        value = morning_by_symbol.at[symbol, column]
        return default if pd.isna(value) else value
    result["MorningScanTimeIST"] = symbols.map(
        lambda symbol: morning_value(symbol, "MorningPageCapturedAtIST", "")
    )
    result["MorningPageVolume"] = symbols.map(
        lambda symbol: morning_value(symbol, "PageVolume", "")
    )
    result["MorningFundamentalStatus"] = symbols.map(
        lambda symbol: morning_value(symbol, "FundamentalShortlistStatus", "NOT AVAILABLE")
    )
    result["MorningNewsContext"] = symbols.map(
        lambda symbol: morning_value(symbol, "Last5DayNews", "NOT AVAILABLE")
    )
    result["MorningUpcomingEvents"] = symbols.map(
        lambda symbol: morning_value(symbol, "UpcomingEvents", "NOT AVAILABLE")
    )
    result["MorningNextResultDate"] = symbols.map(
        lambda symbol: morning_value(symbol, "NextResultDate", "NOT AVAILABLE")
    )
    return result


def run_eod():
    # ScanDate identifies the actual scan session. DataAsOfDate remains the
    # latest completed NSE session and is used only for completed-session data.
    scan_date = datetime.now(IST).date()
    scan_captured_at = datetime.now(IST).isoformat()
    page=fetch_volume_gainers()
    eligible,board_source=_eligible_page_equities(page)
    page_download = _build_nse_page_download(
        page, eligible["TckrSymb"], "EOD", scan_date, scan_captured_at, board_source
    )
    if eligible.empty: raise RuntimeError("WAIT_FOR_DATA: no official Main Board equity symbols found on NSE Volume Gainers page")
    # Separate the live NSE page session from the completed Bhavcopy session.
    # Only compare same-day Morning/EOD when NSE's HTTP Date header verifies it.
    page_session_date = _verified_nse_page_session_date(page, scan_date)
    bhavcopy_date = expected_latest_completed_session()
    eod_date = page_session_date
    if not is_trading_session(eod_date):
        raise RuntimeError(f"WAIT_FOR_DATA: resolved EOD date {eod_date} is not an official NSE equity trading session")
    eligible["EODDate"]=eod_date.isoformat()
    eligible["BhavcopyDate"]=bhavcopy_date.isoformat()
    eligible["EODScanDate"]=scan_date.isoformat()
    eligible["EODScanCapturedAtIST"]=scan_captured_at
    eligible["PageSource"]=NSE_PAGE
    eligible["MainBoardSource"]=board_source
    # Save the raw EOD universe first. Fundamental/news/RVOL enrichment must
    # never be able to prevent tomorrow's 09:20 scanner from seeing this list.
    _save_eod_snapshot(eligible, eod_date)
    eligible=attach_page_rvol(eligible,bhavcopy_date)
    # Fundamentals and event/news windows are evaluated as of this scan date;
    # completed-session RVOL remains tied to bhavcopy_date above.
    assessed=assess_page_fundamentals(eligible,scan_date)
    assessed["EODConfirmationLabel"] = assessed["FundamentalShortlistStatus"].astype(str).str.upper().map({
      "PASS":"EOD_FUNDAMENTAL_PASS", "FAIL":"EOD_FUNDAMENTAL_FAIL"
    }).fillna("EOD_FUNDAMENTAL_WAIT_FOR_DATA")
    # Research windows (news, announcements, deals, events and actions) use
    # the current scan date, not a potentially older completed Bhavcopy date.
    assessed, news, events, deals, corporate_actions = attach_information(assessed, scan_date)
    # Compare against the Morning scan from this scan's IST calendar date,
    # not the older completed-session date used by Bhavcopy/RVOL.
    assessed = _attach_same_day_morning_confirmation(assessed, scan_date, eod_data_date=eod_date)
    if (len(assessed) != len(eligible)
            or set(assessed["TckrSymb"].astype(str).str.upper()) != set(eligible["TckrSymb"].astype(str).str.upper())
            or assessed["TckrSymb"].astype(str).str.upper().duplicated().any()):
        raise RuntimeError("ECMS_EOD_REPORT_INTEGRITY_ERROR: joined report differs from eligible page candidates")
    if "NegativeRiskCount" not in assessed: assessed["NegativeRiskCount"]=0
    assessed["NegativeRiskCount"]=pd.to_numeric(assessed["NegativeRiskCount"],errors="coerce").fillna(0)
    assessed["EODResearchStatus"] = assessed["FundamentalShortlistStatus"].astype(str).str.upper().map({
        "PASS": "FUNDAMENTAL_PASS",
        "FAIL": "FUNDAMENTAL_FAIL",
    }).fillna("FUNDAMENTAL_WAIT_FOR_DATA")
    # Keep NSE page order; RVOL/news/events/valuation/deals never rank or reject.
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    assessed.to_csv(OUTPUT_DIR/"volume_gainers_eod_research.csv",index=False)
    page.to_csv(OUTPUT_DIR/"volume_gainers_page_raw.csv",index=False)
    page_download.to_csv(OUTPUT_DIR/"volume_gainers_eod_nse_page.csv", index=False)
    news.to_csv(OUTPUT_DIR/"volume_gainers_catalysts.csv",index=False)
    events.to_csv(OUTPUT_DIR/"volume_gainers_upcoming_events.csv",index=False)
    deals.to_csv(OUTPUT_DIR/"volume_gainers_bulk_block_deals.csv",index=False)
    corporate_actions.to_csv(OUTPUT_DIR/"volume_gainers_corporate_actions.csv",index=False)
    # Refresh the EOD snapshot with available assessment fields, but keep the
    # snapshot valid even if later informational enrichment or Telegram fails.
    _save_eod_snapshot(assessed, eod_date)
    provider_diag_path = OUTPUT_DIR / "fundamental_provider_diagnostics.csv"
    provider_diag = pd.read_csv(provider_diag_path) if provider_diag_path.exists() and provider_diag_path.stat().st_size else pd.DataFrame()
    provider_status = provider_diag.get("ProviderStatus", pd.Series(dtype=str)).astype(str).str.upper()
    free_attempted = provider_diag.get("FreeSourcesAttempted", pd.Series(False, index=provider_diag.index)).astype(str).str.lower().isin({"true", "1", "yes"})
    shortlist_status = assessed["FundamentalShortlistStatus"].astype(str).str.upper()
    summary={"status":"PASS","scan_date_ist":scan_date.isoformat(),
      "eod_date_ist":eod_date.isoformat(),"page_session_date_ist":page_session_date.isoformat(),
      "bhavcopy_date_ist":bhavcopy_date.isoformat(),"data_as_of_date_ist":bhavcopy_date.isoformat(),
      "eod_scan_captured_at_ist":scan_captured_at,
      "morning_comparison_date_ist":scan_date.isoformat(),
      "eod_data_current_for_scan_date":page_session_date == scan_date,
      "page_freshness_evidence":"NSE_API_HTTP_DATE_HEADER_MATCH" if page_session_date == scan_date else "WAIT_FOR_DATA",
      "data_freshness_status":"CURRENT_SESSION_PAGE_VERIFIED" if page_session_date == scan_date else "WAIT_FOR_CURRENT_SESSION_PAGE_DATA",
      "morning_comparison_status":(
        "STALE_EOD_DATA_NOT_COMPARED" if page_session_date != scan_date else
        "COMPLETED" if not _load_same_day_morning_snapshot(scan_date).empty else
        "NO_VALID_SAME_DAY_MORNING_SNAPSHOT"
      ),
      "morning_comparison_performed":(
        page_session_date == scan_date and not _load_same_day_morning_snapshot(scan_date).empty
      ),
      "morning_repeat_count":int(assessed.get("MorningToEODStatus", pd.Series(dtype=str)).eq("MORNING_AND_EOD_REPEAT").sum()),
      "eod_new_entry_count":int(assessed.get("MorningToEODStatus", pd.Series(dtype=str)).eq("EOD_NEW_ENTRY").sum()),
      "morning_snapshot_found":not _load_same_day_morning_snapshot(scan_date).empty,
      "morning_page_symbols":int(len(_load_same_day_morning_snapshot(scan_date))),
      "nse_page":NSE_PAGE,
      "page_rows":int(len(page)),"eligible_mainboard_equities":int(len(eligible)),
      "page_volume_data_found":int(eligible.get("PageVolumeDataStatus", pd.Series("", index=eligible.index)).eq("DATA_FOUND").sum()),
      "page_volume_data_missing":int(eligible.get("PageVolumeDataStatus", pd.Series("", index=eligible.index)).eq("MISSING_FROM_NSE_RESPONSE").sum()),
      "avg_volume_1w_data_found":int(pd.to_numeric(eligible.get("AvgVolume1W", pd.Series(index=eligible.index)), errors="coerce").notna().sum()),
      "volume_change_pct_1w_data_found":int(pd.to_numeric(eligible.get("VolumeChangePct1W", pd.Series(index=eligible.index)), errors="coerce").notna().sum()),
      "avg_volume_2w_data_found":int(pd.to_numeric(eligible.get("AvgVolume2W", pd.Series(index=eligible.index)), errors="coerce").notna().sum()),
      "volume_change_pct_2w_data_found":int(pd.to_numeric(eligible.get("VolumeChangePct2W", pd.Series(index=eligible.index)), errors="coerce").notna().sum()),
      "fundamental_metrics_all_7_populated":int(assessed.get("FundamentalMetricsCoverageStatus", pd.Series("", index=assessed.index)).eq("ALL_7_POPULATED").sum()),
      "fundamental_metrics_partially_populated":int(assessed.get("FundamentalMetricsCoverageStatus", pd.Series("", index=assessed.index)).eq("PARTIAL_DATA").sum()),
      "fundamental_metric_officially_verified_observations":int(pd.to_numeric(assessed.get("FundamentalMetricsOfficiallyVerifiedCount", pd.Series(0, index=assessed.index)), errors="coerce").fillna(0).sum()),
      "fundamental_metric_mismatch_observations":int(pd.to_numeric(assessed.get("FundamentalMetricsMismatchCount", pd.Series(0, index=assessed.index)), errors="coerce").fillna(0).sum()),
      "assessment_rows":int(len(assessed)),
      "assessment_unique_symbols":int(assessed["TckrSymb"].astype(str).str.upper().nunique()),
      "assessment_missing_or_duplicate_count":int(max(0, len(eligible) - assessed["TckrSymb"].astype(str).str.upper().nunique())),
      "fundamental_pass":int(shortlist_status.eq("PASS").sum()),
      "fundamental_fail":int(shortlist_status.eq("FAIL").sum()),
      "wait_for_data":int(shortlist_status.eq("WAIT_FOR_DATA").sum()),
      "official_xbrl_fully_verified":int(assessed.get("FundamentalVerificationStatus", pd.Series("", index=assessed.index)).astype(str).str.upper().eq("FULLY_VERIFIED").sum()),
      "official_xbrl_partially_verified":int(assessed.get("FundamentalVerificationStatus", pd.Series("", index=assessed.index)).astype(str).str.upper().eq("PARTIALLY_VERIFIED").sum()),
      "official_xbrl_not_verified":int(assessed.get("FundamentalVerificationStatus", pd.Series("", index=assessed.index)).astype(str).str.upper().eq("NOT_VERIFIED").sum()),
      "provider_attempted":int((~provider_status.isin({"EXISTING_RECORD_COMPLETE", "RETRY_COOLDOWN", "DISABLED"})).sum()),
      "provider_cache_reused":int(provider_status.eq("EXISTING_RECORD_COMPLETE").sum()),
      "provider_cooldown_deferred":int(provider_status.eq("RETRY_COOLDOWN").sum()),
      "provider_failed":int(provider_status.str.contains("ERROR|FAILED", regex=True).sum()),
      "free_source_attempted":int(free_attempted.sum()),
      "news_data_found":int(assessed.get("NewsResearchStatus", pd.Series("", index=assessed.index)).eq("DATA_FOUND").sum()),
      "news_no_data_found":int(assessed.get("NewsResearchStatus", pd.Series("", index=assessed.index)).eq("NO_DATA_FOUND").sum()),
      "news_source_unavailable":int(assessed.get("NewsResearchStatus", pd.Series("", index=assessed.index)).eq("SOURCE_UNAVAILABLE").sum()),
      "upcoming_events_data_found":int(assessed.get("UpcomingEventsResearchStatus", pd.Series("", index=assessed.index)).eq("DATA_FOUND").sum()),
      "upcoming_events_source_coverage_partial":int(assessed.get("UpcomingEventsSourceCoverageStatus", pd.Series("", index=assessed.index)).eq("PARTIAL").sum()),
      "upcoming_events_no_data_found":int(assessed.get("UpcomingEventsResearchStatus", pd.Series("", index=assessed.index)).eq("NO_DATA_FOUND").sum()),
      "bulk_block_deals_data_found":int(assessed.get("BulkBlockDealsResearchStatus", pd.Series("", index=assessed.index)).eq("DATA_FOUND").sum()),
      "bulk_block_source_coverage_complete":int(assessed.get("BulkBlockSourceCoverageStatus", pd.Series("", index=assessed.index)).eq("COMPLETE").sum()),
      "bulk_block_source_coverage_partial":int(assessed.get("BulkBlockSourceCoverageStatus", pd.Series("", index=assessed.index)).eq("PARTIAL").sum()),
      "bulk_block_deals_no_data_found":int(assessed.get("BulkBlockDealsResearchStatus", pd.Series("", index=assessed.index)).eq("NO_DATA_FOUND").sum()),
      "corporate_actions_data_found":int(assessed.get("CorporateActionResearchStatus", pd.Series("", index=assessed.index)).eq("DATA_FOUND").sum()),
      "corporate_action_disclosures_found":int(assessed.get("CorporateActionDisclosureStatus", pd.Series("", index=assessed.index)).eq("DATA_FOUND").sum()),
      "page_limit_note":"Processes every row returned by NSE page; page currently labels table Top 25.",
      "generated_at_ist":datetime.now(IST).isoformat(),"state_file":str(STATE_FILE)}
    (OUTPUT_DIR/"volume_gainers_eod_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2)); return summary
def _fundamental_decision_fields(status):
    """Map the verified fundamental result without suppressing WAIT research."""
    value = "WAIT_FOR_DATA" if status is None or pd.isna(status) else str(status).strip().upper()
    if value == "PASS":
        return {
            "FundamentalDecisionRole": "VERIFIED_FUNDAMENTAL_PASS",
            "ResearchContinuationStatus": "CONTINUE_BALANCED_RESEARCH",
            "StrongFundamentalHandOffStatus": "FORWARDED_TO_BALANCED_RESEARCH",
            "StrongFundamentalNotForwardedReason": "",
        }
    if value == "FAIL":
        return {
            "FundamentalDecisionRole": "VERIFIED_FUNDAMENTAL_FAIL",
            "ResearchContinuationStatus": "FUNDAMENTAL_REJECTION_GATE",
            "StrongFundamentalHandOffStatus": "REJECTED_BY_VERIFIED_FUNDAMENTALS",
            "StrongFundamentalNotForwardedReason": "VERIFIED_FUNDAMENTAL_RULE_FAIL",
        }
    return {
        "FundamentalDecisionRole": "FUNDAMENTAL_PENDING_OTHER_RESEARCH_CONTINUES",
        "ResearchContinuationStatus": "CONTINUE_BALANCED_RESEARCH",
        "StrongFundamentalHandOffStatus": "FORWARDED_PENDING_FUNDAMENTAL_DATA",
        "StrongFundamentalNotForwardedReason": "",
    }


def _strong_fundamental_mask(frame):
    """Return a fundamental-PASS indicator only; not an overall stock gate."""
    if frame.empty:
        return pd.Series(False, index=frame.index)
    shortlist = frame.get("FundamentalShortlistStatus", pd.Series("", index=frame.index)).astype(str).str.upper()
    return shortlist.eq("PASS")


def _page_presence_confirmation_status(eod_present, morning_present):
    """Workflow-only confirmation: the same symbol appeared at both checkpoints."""
    if eod_present and morning_present:
        return "DOUBLE_CONFIRMED_EOD_MORNING"
    if eod_present:
        return "EOD_ONLY_NOT_ON_MORNING_PAGE"
    if morning_present:
        return "NEW_MORNING_ENTRY"
    return "NOT_PRESENT"


def _confirmation_status(eod_pass, present, morning_pass):
    """Fundamental-layer confirmation only; never an overall stock decision."""
    if eod_pass and present and morning_pass:
        return "DOUBLE_CONFIRMED_EOD_MORNING"
    if morning_pass:
        return "MORNING_FUNDAMENTAL_PASS"
    if eod_pass and present:
        return "EOD_PASS_MORNING_NOT_PASS"
    if eod_pass and not present:
        return "EOD_PASS_NOT_ON_MORNING_PAGE"
    return "NO_FUNDAMENTAL_PASS"


def run_morning():
    today = datetime.now(IST).date()
    if not is_trading_session(today):
        raise RuntimeError(f"WAIT_FOR_DATA: {today} is not an official NSE equity trading session")
    if not STATE_FILE.exists(): raise RuntimeError("WAIT_FOR_DATA: previous EOD Volume Gainers snapshot missing from ECMS state cache")
    previous=pd.read_csv(STATE_FILE,dtype={"TckrSymb":str})
    if previous.empty or "TckrSymb" not in previous: raise RuntimeError("WAIT_FOR_DATA: previous EOD snapshot empty or invalid")
    previous["TckrSymb"] = previous["TckrSymb"].astype(str).str.strip().str.upper()
    if previous["TckrSymb"].eq("").any() or previous["TckrSymb"].duplicated().any():
        raise RuntimeError("WAIT_FOR_DATA: previous EOD snapshot has blank or duplicate symbols")
    if "SnapshotType" in previous and not previous["SnapshotType"].astype(str).eq("EOD").all():
        raise RuntimeError("WAIT_FOR_DATA: cached snapshot is not tagged as EOD")
    if "SnapshotStatus" in previous and not previous["SnapshotStatus"].astype(str).eq("VALID").all():
        raise RuntimeError("WAIT_FOR_DATA: cached EOD snapshot is not marked VALID")
    expected_eod = expected_latest_completed_session().isoformat()
    stored_dates = set(previous.get("EODDate", pd.Series(dtype=str)).dropna().astype(str))
    if CONSUMED_EOD_MARKER_FILE.exists():
        try:
            consumed_marker = json.loads(CONSUMED_EOD_MARKER_FILE.read_text(encoding="utf-8"))
            consumed_through = str(consumed_marker.get("consumed_eod_date", ""))
        except Exception as exc:
            raise RuntimeError(
                f"WAIT_FOR_DATA: consumed-EOD cache marker is unreadable: {type(exc).__name__}: {exc}"
            ) from exc
        if consumed_through and stored_dates and max(stored_dates) <= consumed_through:
            raise RuntimeError(
                f"WAIT_FOR_DATA: cached EOD reference {sorted(stored_dates)} was already consumed "
                f"through {consumed_through}; refusing stale cache resurrection"
            )
    if stored_dates != {expected_eod}:
        raise RuntimeError(f"WAIT_FOR_DATA: cached EOD page snapshot dates {sorted(stored_dates)} do not match latest completed NSE session {expected_eod}")
    live_page=fetch_volume_gainers()
    mainboard,board_source=load_official_mainboard_symbols()
    morning_page_captured_at = datetime.now(IST).isoformat()
    page_download = _build_nse_page_download(
        live_page, mainboard, "MORNING", today.isoformat(), morning_page_captured_at, board_source
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    page_download.to_csv(OUTPUT_DIR/"volume_gainers_morning_nse_page.csv", index=False)
    live=live_page[live_page["TckrSymb"].isin(mainboard)].copy()
    if live.empty:
        raise RuntimeError("WAIT_FOR_DATA: no eligible Main Board candidates on 09:20 Volume Gainers page")
    # Morning RVOL is based on the latest completed Bhavcopy session. It is
    # explicitly labelled as prior-session context, never as partial intraday RVOL.
    live = attach_page_rvol(live, expected_latest_completed_session())
    # Record the page-capture time before fundamental and information enrichment.
    live["MorningPageCapturedAtIST"] = morning_page_captured_at

    # Run the same fundamental framework on every eligible symbol visible now,
    # including repeated EOD symbols and new morning entries. The collector
    # reuses complete ECMS cache rows and retries incomplete rows under ECMS policy.
    live["EODDate"]=expected_eod
    live["MorningDate"]=today.isoformat()
    live["MainBoardSource"]=board_source
    morning_assessed=assess_page_fundamentals(live,today)
    if "FundamentalShortlistStatus" not in morning_assessed:
        morning_assessed["FundamentalShortlistStatus"]="WAIT_FOR_DATA"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    morning_assessed, morning_news, morning_events, morning_deals, morning_corporate_actions = attach_information(morning_assessed, today)
    _save_same_day_morning_snapshot(morning_assessed, today)
    morning_news.to_csv(OUTPUT_DIR/"volume_gainers_morning_news.csv", index=False)
    morning_events.to_csv(OUTPUT_DIR/"volume_gainers_morning_upcoming_events.csv", index=False)
    morning_deals.to_csv(OUTPUT_DIR/"volume_gainers_morning_bulk_block_deals.csv", index=False)
    morning_corporate_actions.to_csv(OUTPUT_DIR/"volume_gainers_morning_corporate_actions.csv", index=False)
    morning_assessed["MorningStrongFundamentalStatus"] = (
        _strong_fundamental_mask(morning_assessed).map({True:"MORNING_FUNDAMENTAL_PASS",False:"MORNING_NOT_FUNDAMENTAL_PASS"})
    )
    morning_assessed["MorningFundamentalGateStatus"] = (
        morning_assessed["FundamentalShortlistStatus"].astype(str).str.upper().map({
            "PASS": "VERIFIED_FUNDAMENTAL_PASS",
            "FAIL": "VERIFIED_FUNDAMENTAL_FAIL",
        }).fillna("FUNDAMENTAL_WAIT_OTHER_RESEARCH_CONTINUES")
    )

    previous_symbols=set(previous["TckrSymb"].astype(str).str.upper())
    live_symbols=set(live["TckrSymb"].astype(str).str.upper())
    live_by_symbol=live.set_index("TckrSymb",drop=False)
    morning_by_symbol=morning_assessed.set_index("TckrSymb",drop=False)
    previous_by_symbol=previous.set_index("TckrSymb",drop=False)
    rows=[]
    all_symbols=sorted(previous_symbols | live_symbols)
    for symbol in all_symbols:
        old=previous_by_symbol.loc[symbol].to_dict() if symbol in previous_by_symbol.index else {}
        current=live_by_symbol.loc[symbol].to_dict() if symbol in live_by_symbol.index else {}
        assessed=morning_by_symbol.loc[symbol].to_dict() if symbol in morning_by_symbol.index else {}
        present=symbol in live_symbols
        # Backward-compatible: prior EOD snapshots already carry the strict
        # FundamentalShortlistStatus even if their legacy research label differs.
        eod_strong=(
            str(old.get("EODFundamentalShortlistStatus","")).upper()=="PASS"
            or str(old.get("EODStrongFundamentalStatus","")).upper()=="EOD_FUNDAMENTAL_PASS"
        )
        morning_strong=str(assessed.get("MorningStrongFundamentalStatus","")).upper()=="MORNING_FUNDAMENTAL_PASS"
        confirmation=_confirmation_status(eod_strong,present,morning_strong)
        rows.append({
          "TckrSymb":symbol,
          "CompanyName":current.get("CompanyName",old.get("CompanyName","")),
          "EODDate":old.get("EODDate",""),
          "MorningDate":today.isoformat(),
          "MorningStatus":(
             "EOD_AND_MORNING_PAGE_REPEAT" if symbol in previous_symbols and present else
             "EOD_ONLY_NOT_ON_MORNING_PAGE" if symbol in previous_symbols else "NEW_MORNING_ENTRY"
          ),
          "PagePresenceConfirmationStatus": _page_presence_confirmation_status(
             symbol in previous_symbols, present
          ),
          "PagePresenceDoubleConfirmed": bool(symbol in previous_symbols and present),
          "EODPageVolume":old.get("PageVolume"),
          "EODPageVolumeDataStatus":old.get("PageVolumeDataStatus","NOT_AVAILABLE_IN_PREVIOUS_SNAPSHOT"),
          "EODAvgVolume1W":old.get("AvgVolume1W"),
          "EODVolumeChangePct1W":old.get("VolumeChangePct1W"),
          "EODAvgVolume2W":old.get("AvgVolume2W"),
          "EODVolumeChangePct2W":old.get("VolumeChangePct2W"),
          "MorningPageVolume":current.get("PageVolume"),
          "MorningAvgVolume1W":current.get("AvgVolume1W"),
          "MorningVolumeChangePct1W":current.get("VolumeChangePct1W"),
          "MorningAvgVolume2W":current.get("AvgVolume2W"),
          "MorningVolumeChangePct2W":current.get("VolumeChangePct2W"),
          "EODLTP":old.get("LTP"),"MorningLTP":current.get("LTP"),
          "EODRVOL":old.get("RVOL"),
          "MorningRVOL":assessed.get("RVOL","NOT AVAILABLE"),
          "MorningRVOLDataStatus":(
              "PRIOR_COMPLETED_SESSION_" + str(assessed.get("RVOLDataStatus","WAIT_FOR_DATA"))
              if str(assessed.get("RVOLDataStatus","")).strip()
              else "PRIOR_COMPLETED_SESSION_RVOL_NOT_AVAILABLE"
          ),
          "ValuationLabel":assessed.get("ValuationLabel","NOT AVAILABLE"),
          "ValuationBasis":assessed.get("ValuationBasis","NOT AVAILABLE"),
          "Last5DayNews":assessed.get("Last5DayNews","NOT AVAILABLE"),
          "CatalystStatus":assessed.get("CatalystStatus","NOT AVAILABLE"),
          "UpcomingEventsStatus":assessed.get("UpcomingEventsStatus","NOT AVAILABLE"),
          "UpcomingEvents":assessed.get("UpcomingEvents","NOT AVAILABLE"),
          "NextResultDate":assessed.get("NextResultDate","NOT ANNOUNCED"),
          "NextResultDetails":assessed.get("NextResultDetails",""),
          "BulkBlockDealStatus":assessed.get("BulkBlockDealStatus","NOT AVAILABLE"),
          "BulkDealCount":assessed.get("BulkDealCount",0),
          "BlockDealCount":assessed.get("BlockDealCount",0),
          "BulkBuyers":assessed.get("BulkBuyers",""),
          "BulkSellers":assessed.get("BulkSellers",""),
          "BlockBuyers":assessed.get("BlockBuyers",""),
          "BlockSellers":assessed.get("BlockSellers",""),
          "BulkBlockDealSummary":assessed.get("BulkBlockDealSummary",""),
          "BulkDealCountLast5Days":assessed.get("BulkDealCountLast5Days",0),
          "BlockDealCountLast5Days":assessed.get("BlockDealCountLast5Days",0),
          "BulkBlockSummaryLast5Days":assessed.get("BulkBlockSummaryLast5Days",""),
          "CorporateActionResearchStatus":assessed.get("CorporateActionResearchStatus","NOT_VERIFIED"),
          "CorporateActionCount":assessed.get("CorporateActionCount",0),
          "CorporateActionSummary":assessed.get("CorporateActionSummary",""),
          "CorporateActionWindowStart":assessed.get("CorporateActionWindowStart",""),
          "CorporateActionWindowEnd":assessed.get("CorporateActionWindowEnd",""),
          "CorporateActionDisclosureStatus":assessed.get("CorporateActionDisclosureStatus","NOT_VERIFIED"),
          "EODFundamentalShortlistStatus":old.get("EODFundamentalShortlistStatus",""),
          "EODStrongFundamentalStatus":old.get("EODStrongFundamentalStatus",""),
          "EODFundamentalNotForwardedReason":old.get("EODFundamentalNotForwardedReason",""),
          "MorningFundamentalShortlistStatus":assessed.get("FundamentalShortlistStatus","NOT_ASSESSED"),
          "MorningFundamentalMetricsPopulatedCount":assessed.get("FundamentalMetricsPopulatedCount",""),
          "MorningFundamentalMetricsMissingNames":assessed.get("FundamentalMetricsMissingNames",""),
          "MorningFundamentalMetricsOfficiallyVerifiedCount":assessed.get("FundamentalMetricsOfficiallyVerifiedCount",""),
          "MorningFundamentalMetricsMismatchCount":assessed.get("FundamentalMetricsMismatchCount",""),
          "MorningFundamentalNotForwardedReason":assessed.get("StrongFundamentalNotForwardedReason",""),
          "MorningFundamentalDecisionRole":assessed.get("FundamentalDecisionRole","NOT_ASSESSED"),
          "MorningResearchContinuationStatus":assessed.get("ResearchContinuationStatus","NOT_ASSESSED"),
          "MorningFundamentalGateStatus":assessed.get("MorningFundamentalGateStatus","NOT_ASSESSED"),
          "MorningStrongFundamentalStatus":assessed.get("MorningStrongFundamentalStatus","NOT_ASSESSED"),
          "FundamentalConfirmationStatus":confirmation,
          "ConfirmationStatus":confirmation,
          "MorningChangePct":current.get("ChangePct"),
          "MorningVolumeChangeTimes1W":current.get("VolumeChangeTimes1W"),
          "MorningVolumeChangeTimes2W":current.get("VolumeChangeTimes2W"),
          "MorningPageVolumeDataStatus":current.get("PageVolumeDataStatus","MISSING_FROM_NSE_RESPONSE"),
          "MorningPageVolumeSourceField":current.get("PageVolumeSourceField",""),
           "MorningPagePayloadKeys":current.get("NSEPayloadKeys",""),
           "MorningPageVolumeLikeFields":current.get("NSEPayloadVolumeLikeFields",""),
          "DataQuality":"LIVE_PAGE_AND_FUNDAMENTALS" if present and assessed else
            "NOT_ON_CURRENT_PAGE" if not present else "PARTIAL_LIVE_DATA"})
    report=pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    report.to_csv(OUTPUT_DIR/"volume_gainers_morning_recheck.csv",index=False)
    # Preserve the original EOD snapshot; only the fundamental workspace cache
    # is enriched by the morning assessment.
    summary={"status":"PASS","scan_date_ist":today.isoformat(),
      "data_as_of_date_ist":expected_eod,
      "morning_time_ist":datetime.now(IST).isoformat(),
      "morning_rvol_data_found":int(pd.to_numeric(morning_assessed.get("RVOL", pd.Series(index=morning_assessed.index)), errors="coerce").notna().sum()),
      "morning_rvol_data_missing":int(pd.to_numeric(morning_assessed.get("RVOL", pd.Series(index=morning_assessed.index)), errors="coerce").isna().sum()),
      "previous_eod_symbols":len(previous_symbols),"current_page_eligible_symbols":len(live_symbols),
      "morning_page_volume_data_found":int(morning_assessed.get("PageVolumeDataStatus", pd.Series("", index=morning_assessed.index)).eq("DATA_FOUND").sum()),
      "morning_page_volume_data_missing":int(morning_assessed.get("PageVolumeDataStatus", pd.Series("", index=morning_assessed.index)).eq("MISSING_FROM_NSE_RESPONSE").sum()),
      "morning_avg_volume_1w_data_found":int(pd.to_numeric(morning_assessed.get("AvgVolume1W", pd.Series(index=morning_assessed.index)), errors="coerce").notna().sum()),
      "morning_volume_change_pct_1w_data_found":int(pd.to_numeric(morning_assessed.get("VolumeChangePct1W", pd.Series(index=morning_assessed.index)), errors="coerce").notna().sum()),
      "morning_avg_volume_2w_data_found":int(pd.to_numeric(morning_assessed.get("AvgVolume2W", pd.Series(index=morning_assessed.index)), errors="coerce").notna().sum()),
      "morning_volume_change_pct_2w_data_found":int(pd.to_numeric(morning_assessed.get("VolumeChangePct2W", pd.Series(index=morning_assessed.index)), errors="coerce").notna().sum()),
      "new_entries":int(report["MorningStatus"].eq("NEW_MORNING_ENTRY").sum()),
      "morning_assessed_candidates":int(len(morning_assessed)),
      "morning_assessment_rows":int(report["MorningStrongFundamentalStatus"].ne("NOT_ASSESSED").sum()),
      "morning_fundamental_pass":int(report["MorningStrongFundamentalStatus"].eq("MORNING_FUNDAMENTAL_PASS").sum()),
      "morning_fundamental_fail":int(report["MorningFundamentalGateStatus"].eq("VERIFIED_FUNDAMENTAL_FAIL").sum()),
      "morning_wait_continues_research":int(report["MorningResearchContinuationStatus"].eq("CONTINUE_BALANCED_RESEARCH").sum()),
      "morning_verified_fundamental_rejections":int(report["MorningResearchContinuationStatus"].eq("FUNDAMENTAL_REJECTION_GATE").sum()),
      "morning_fundamental_metrics_all_7_populated":int(morning_assessed.get("FundamentalMetricsCoverageStatus", pd.Series("", index=morning_assessed.index)).eq("ALL_7_POPULATED").sum()),
      "morning_fundamental_metrics_partially_populated":int(morning_assessed.get("FundamentalMetricsCoverageStatus", pd.Series("", index=morning_assessed.index)).eq("PARTIAL_DATA").sum()),
      "morning_fundamental_metric_officially_verified_observations":int(pd.to_numeric(morning_assessed.get("FundamentalMetricsOfficiallyVerifiedCount", pd.Series(0, index=morning_assessed.index)), errors="coerce").fillna(0).sum()),
      "morning_fundamental_metric_mismatch_observations":int(pd.to_numeric(morning_assessed.get("FundamentalMetricsMismatchCount", pd.Series(0, index=morning_assessed.index)), errors="coerce").fillna(0).sum()),
      "morning_wait_for_data":int(morning_assessed["FundamentalShortlistStatus"].astype(str).str.upper().eq("WAIT_FOR_DATA").sum()),
      "news_data_found":int(morning_assessed.get("NewsResearchStatus", pd.Series("", index=morning_assessed.index)).eq("DATA_FOUND").sum()),
      "news_no_data_found":int(morning_assessed.get("NewsResearchStatus", pd.Series("", index=morning_assessed.index)).eq("NO_DATA_FOUND").sum()),
      "news_source_unavailable":int(morning_assessed.get("NewsResearchStatus", pd.Series("", index=morning_assessed.index)).eq("SOURCE_UNAVAILABLE").sum()),
      "upcoming_events_data_found":int(morning_assessed.get("UpcomingEventsResearchStatus", pd.Series("", index=morning_assessed.index)).eq("DATA_FOUND").sum()),
      "upcoming_events_no_data_found":int(morning_assessed.get("UpcomingEventsResearchStatus", pd.Series("", index=morning_assessed.index)).eq("NO_DATA_FOUND").sum()),
      "bulk_block_deals_data_found":int(morning_assessed.get("BulkBlockDealsResearchStatus", pd.Series("", index=morning_assessed.index)).eq("DATA_FOUND").sum()),
      "bulk_block_deals_no_data_found":int(morning_assessed.get("BulkBlockDealsResearchStatus", pd.Series("", index=morning_assessed.index)).eq("NO_DATA_FOUND").sum()),
      "corporate_actions_data_found":int(morning_assessed.get("CorporateActionResearchStatus", pd.Series("", index=morning_assessed.index)).eq("DATA_FOUND").sum()),
      "corporate_action_disclosures_found":int(morning_assessed.get("CorporateActionDisclosureStatus", pd.Series("", index=morning_assessed.index)).eq("DATA_FOUND").sum()),
      "morning_new_entries":int(report["MorningStatus"].eq("NEW_MORNING_ENTRY").sum()),
      "eod_fundamental_pass_repeats":int(report["FundamentalConfirmationStatus"].eq("DOUBLE_CONFIRMED_EOD_MORNING").sum()),
      "eod_morning_page_repeats":int(report["PagePresenceDoubleConfirmed"].sum()),
       "same_day_morning_snapshot_saved":MORNING_STATE_FILE.exists(),
      "eod_only_not_on_morning_page":int(report["MorningStatus"].eq("EOD_ONLY_NOT_ON_MORNING_PAGE").sum()),
      "double_confirmed":int(report["FundamentalConfirmationStatus"].eq("DOUBLE_CONFIRMED_EOD_MORNING").sum()),
      "fundamental_double_confirmed":int(report["FundamentalConfirmationStatus"].eq("DOUBLE_CONFIRMED_EOD_MORNING").sum()),
      "page_presence_double_confirmed":int(report["PagePresenceDoubleConfirmed"].sum()),
      "page_presence_eod_only":int(report["PagePresenceConfirmationStatus"].eq("EOD_ONLY_NOT_ON_MORNING_PAGE").sum()),
      "page_presence_morning_only":int(report["PagePresenceConfirmationStatus"].eq("NEW_MORNING_ENTRY").sum()),
      "eod_pass_not_morning_pass":int(report["ConfirmationStatus"].eq("EOD_PASS_MORNING_NOT_PASS").sum()),
      "nse_page":NSE_PAGE,
      "note":"Every eligible 09:20 page candidate receives fundamental assessment. Verified complete FAIL may invoke the fundamental rejection rule; WAIT/PARTIAL continues through other research. Page repeat/new/disappeared labels are independent of fundamental status. ConfirmationStatus is a legacy alias for FundamentalConfirmationStatus, not an overall stock decision."}
    # The comparison report and same-day Morning snapshot are now persisted.
    # Only now consume the previous EOD reference; failures above leave it intact.
    summary["previous_eod_reference_consumed"] = _consume_previous_eod_snapshot(expected_eod)
    (OUTPUT_DIR/"volume_gainers_morning_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2)); return summary
def _write_execution_status(mode, status, reason="", **details):
    """Persist an explicit run outcome so skipped scans cannot be mistaken for completed scans."""
    payload = {
        "status": str(status).upper(),
        "mode": str(mode).upper(),
        "reason": str(reason),
        "date_ist": datetime.now(IST).date().isoformat(),
        "recorded_at_ist": datetime.now(IST).isoformat(),
        "github_run_id": os.getenv("GITHUB_RUN_ID", ""),
        "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", ""),
        **details,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    status_path = OUTPUT_DIR / "ecms_execution_status.json"
    temporary = status_path.with_name(status_path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(status_path)
    print("ECMS_EXECUTION_STATUS=" + json.dumps(payload, sort_keys=True))
    return payload


def _reuse_previous_eod_snapshot():
    """Publish the verified latest EOD snapshot without refreshing live NSE data."""
    import json
    if not STATE_FILE.is_file():
        _write_execution_status("eod", "WAIT_FOR_DATA", "EOD_SNAPSHOT_NOT_FOUND_FOR_REUSE")
        return None
    try:
        snapshot = pd.read_csv(STATE_FILE, dtype={"TckrSymb": str})
    except Exception as exc:
        _write_execution_status(
            "eod", "WAIT_FOR_DATA", "EOD_SNAPSHOT_UNREADABLE_FOR_REUSE",
            detail=f"{type(exc).__name__}: {exc}",
        )
        return None
    if snapshot.empty or "EODDate" not in snapshot.columns:
        _write_execution_status("eod", "WAIT_FOR_DATA", "EOD_SNAPSHOT_INVALID_FOR_REUSE")
        return None
    expected_date = expected_latest_completed_session()
    dates = set(snapshot["EODDate"].dropna().astype(str))
    if dates != {expected_date.isoformat()}:
        _write_execution_status(
            "eod", "WAIT_FOR_DATA", "EOD_SNAPSHOT_DATE_MISMATCH_FOR_REUSE",
            expected_eod_date=expected_date.isoformat(), snapshot_dates=sorted(dates),
        )
        return None
    valid = (
        "TckrSymb" in snapshot
        and snapshot["TckrSymb"].astype(str).str.strip().ne("").all()
        and not snapshot["TckrSymb"].astype(str).str.upper().duplicated().any()
        and "SnapshotType" in snapshot
        and snapshot["SnapshotType"].astype(str).eq("EOD").all()
        and "SnapshotStatus" in snapshot
        and snapshot["SnapshotStatus"].astype(str).eq("VALID").all()
        and "SnapshotCapturedAtIST" in snapshot
        and snapshot["SnapshotCapturedAtIST"].astype(str).str.strip().ne("").all()
    )
    if not valid:
        _write_execution_status(
            "eod", "WAIT_FOR_DATA", "EOD_SNAPSHOT_VALIDATION_FAILED_FOR_REUSE",
            expected_eod_date=expected_date.isoformat(), snapshot_dates=sorted(dates),
        )
        return None
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = snapshot.copy()
    report["ScanMode"] = "EOD_REUSED"
    report["ScanDateIST"] = expected_date.isoformat()
    report["DataAsOfDateIST"] = expected_date.isoformat()
    report["EODSnapshotReuse"] = True
    if "FundamentalShortlistStatus" not in report and "EODFundamentalShortlistStatus" in report:
        report["FundamentalShortlistStatus"] = report["EODFundamentalShortlistStatus"]
    report.to_csv(OUTPUT_DIR / "volume_gainers_eod_nse_page.csv", index=False)
    report.to_csv(OUTPUT_DIR / "volume_gainers_eod_research.csv", index=False)
    summary = {
        "status": "REUSED",
        "scan_date_ist": expected_date.isoformat(),
        "eod_date_ist": expected_date.isoformat(),
        "data_as_of_date_ist": expected_date.isoformat(),
        "snapshot_reused": True,
        "snapshot_refresh_performed": False,
        "eligible_mainboard_equities": int(len(report)),
        "state_file": str(STATE_FILE),
        "generated_at_ist": datetime.now(IST).isoformat(),
    }
    (OUTPUT_DIR / "volume_gainers_eod_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    _write_execution_status(
        "eod", "REUSED", "PREVIOUS_EOD_SNAPSHOT_REUSED",
        actual_time_ist=datetime.now(IST).strftime("%H:%M"),
        data_as_of_date_ist=expected_date.isoformat(),
    )
    print("ECMS_EOD_SNAPSHOT_REUSED=" + json.dumps(summary, sort_keys=True))
    return summary


def _resolve_manual_scan_mode(now):
    """Resolve one-click manual scans using the ECMS IST operating windows."""
    current = now.time().replace(tzinfo=None)
    if current >= time(15, 30):
        return "eod"
    if current < time(8, 0):
        return "eod-reuse"
    if time(9, 15) <= current < time(12, 0):
        return "morning"
    return None


def main():
    parser=argparse.ArgumentParser(description="ECMS NSE Volume Gainers scanner")
    parser.add_argument("--mode",choices=("auto","eod","eod-reuse","morning"),required=True)
    args=parser.parse_args()
    now = datetime.now(IST)
    if args.mode == "auto" and os.getenv("GITHUB_EVENT_NAME", "").lower() == "workflow_dispatch":
        args.mode = _resolve_manual_scan_mode(now)
        if args.mode is None:
            current = now.time().replace(tzinfo=None)
            reason = (
                "EOD_SNAPSHOT_LOCKED_AFTER_0800"
                if time(8, 0) <= current < time(9, 15)
                else "OUTSIDE_ECMS_SCAN_WINDOW"
            )
            print(f"ECMS_MANUAL_SCAN_SKIPPED reason={reason} at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            _write_execution_status(
                "auto", "SKIPPED", reason,
                actual_time_ist=now.strftime("%H:%M"),
            )
            return
        print(f"ECMS_MANUAL_MODE_RESOLVED={args.mode.upper()} at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    # GitHub Actions cron also fires on weekday NSE holidays. Never treat the
    # last available page/session as a fresh scan for a non-trading date.
    today = datetime.now(IST).date()
    for warning in calendar_coverage_warnings(today):
        print(warning)
    try:
        trading_session = is_trading_session(today)
    except CalendarCoverageError as exc:
        _write_execution_status(args.mode, "SKIPPED", "OFFICIAL_NSE_CALENDAR_UNAVAILABLE", detail=str(exc))
        return
    if not trading_session:
        _write_execution_status(args.mode, "SKIPPED", "OFFICIAL_NSE_NON_TRADING_DAY")
        return
    if args.mode == "eod-reuse":
        return _reuse_previous_eod_snapshot()
    # Scheduled runs must match the calendar's session-specific scan slot.
    # Manual dispatch is intentionally allowed at any time on a trading date.
    if os.getenv("GITHUB_EVENT_NAME", "").lower() == "schedule":
        try:
            expected_time = expected_scan_time(today, args.mode)
        except CalendarCoverageError as exc:
            expected_time = None
            schedule_detail = str(exc)
        else:
            schedule_detail = ""
        if not expected_time:
            _write_execution_status(args.mode, "SKIPPED", "OFFICIAL_NSE_SPECIAL_SESSION_SCAN_TIME_NOT_CONFIGURED", detail=schedule_detail)
            return
        expected_hour, expected_minute = (int(part) for part in expected_time.split(":"))
        now = datetime.now(IST)
        difference = abs((now.hour * 60 + now.minute) - (expected_hour * 60 + expected_minute))
        if difference > 15:
            _write_execution_status(
                args.mode, "SKIPPED", "NOT_OFFICIAL_NSE_SESSION_SCAN_SLOT",
                expected_time_ist=expected_time, actual_time_ist=now.strftime("%H:%M"),
            )
            return
    result = run_eod() if args.mode=="eod" else run_morning()
    _write_execution_status(args.mode, "SUCCESS", "SCAN_COMPLETED")
    return result
if __name__=="__main__": main()
