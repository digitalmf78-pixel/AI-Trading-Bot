"""NSE Volume Gainers page scanner for ECMS. No orders; shared inputs are read-only."""
from __future__ import annotations
import argparse, json, os, re, shutil
from datetime import datetime
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
    attach_valuation, collect_upcoming_events, collect_bulk_block_deals,
)
from nse_trading_calendar import is_trading_session
NSE_PAGE = "https://www.nseindia.in/market-data/volume-gainers-spurts"
NSE_API = "https://www.nseindia.in/api/live-analysis-volume-gainers"
STATE_DIR = Path("data/cache/ecms")
STATE_FILE = STATE_DIR / "volume_gainers_previous_eod.csv"
REQUEST_TIMEOUT = (8, 20)
ALIASES = {
 "symbol": ("symbol","tradingSymbol","ticker"),
 "company": ("securityName","companyName","company","name"),
 "series": ("series","securitySeries"),
 "volume": ("volume","totalTradedVolume","totalTradedQty","tradedVolume","quantity"),
 "ltp": ("ltp","lastPrice","lastTradedPrice","closePrice"),
 "change_pct": ("pChange","perChange","changePercent","percentChange"),
 "turnover": ("turnover","totalTradedValue","value"),
 "avg_volume_1w": ("avgVolume1W","averageVolume1W","weekAvgVolume","avgVolume"),
 "change_times_1w": ("change1W","volumeChange1W","changeInVolume1W"),
 "avg_volume_2w": ("avgVolume2W","averageVolume2W","twoWeekAvgVolume","averageVolume"),
 "change_times_2w": ("change2W","volumeChange2W","changeInVolume2W"),
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
def fetch_volume_gainers(session=None):
    client = session or requests.Session()
    client.headers.update(HEADERS)
    client.headers["Referer"] = NSE_PAGE
    landing = client.get(NSE_PAGE, timeout=REQUEST_TIMEOUT); landing.raise_for_status()
    response = client.get(NSE_API, timeout=REQUEST_TIMEOUT); response.raise_for_status()
    rows = _find_records(response.json())
    if not rows: raise RuntimeError("WAIT_FOR_DATA: NSE Volume Gainers API returned no recognizable symbol rows")
    normalized=[]
    for row in rows:
        symbol=str(_get(row,ALIASES["symbol"]) or "").strip().upper()
        if not symbol or symbol in {"-","NAN","NONE"}: continue
        normalized.append({
          "TckrSymb":symbol, "CompanyName":str(_get(row,ALIASES["company"]) or ""),
          "Series":str(_get(row,ALIASES["series"]) or "").strip().upper(),
          "PageVolume":_number(_get(row,ALIASES["volume"])), "LTP":_number(_get(row,ALIASES["ltp"])),
          "ChangePct":_number(_get(row,ALIASES["change_pct"])), "Turnover":_number(_get(row,ALIASES["turnover"])),
          "AvgVolume1W":_number(_get(row,ALIASES["avg_volume_1w"])),
          "VolumeChangeTimes1W":_number(_get(row,ALIASES["change_times_1w"])),
          "AvgVolume2W":_number(_get(row,ALIASES["avg_volume_2w"])),
          "VolumeChangeTimes2W":_number(_get(row,ALIASES["change_times_2w"])),
          "NSEUpdatedAt":str(_get(row,ALIASES["updated_at"]) or ""),
        })
    frame=pd.DataFrame(normalized)
    if frame.empty: raise RuntimeError("WAIT_FOR_DATA: NSE response contained no valid symbols")
    return frame.drop_duplicates("TckrSymb",keep="first")
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
            force_retry_incomplete=True,
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
        failed["StrongFundamentalHandOffStatus"] = "NOT_FORWARDED"
        failed["StrongFundamentalNotForwardedReason"] = "FUNDAMENTAL_COLLECTION_ERROR"
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
    # FundamentalShortlistStatus is the sole stock-level decision gate.
    # Research scores, catalysts, RVOL and all other context are informational.
    fundamental_pass = assessed["FundamentalShortlistStatus"].astype(str).str.upper().eq("PASS")
    assessed["FundamentalPassStatus"] = fundamental_pass.map({
        True: "FUNDAMENTAL_PASS", False: "NOT_FUNDAMENTAL_PASS"
    })
    assessed["StrongFundamentalHandOffStatus"] = fundamental_pass.map({
        True: "PASS_FUNDAMENTAL", False: "NOT_PASS_FUNDAMENTAL"
    })
    assessed["StrongFundamentalNotForwardedReason"] = assessed.apply(
        lambda row: "" if str(row.get("FundamentalShortlistStatus", "")).upper() == "PASS"
        else "FUNDAMENTAL_" + str(row.get("FundamentalShortlistStatus", "MISSING")).upper(),
        axis=1,
    )

    # Publish current-page candidate snapshots, not the full persistent cache
    # or filing register. The workspace itself remains intact for later reuse.
    candidate_metrics.to_csv(ecms_output_dir / "fundamental_metrics_ecms.csv", index=False)
    candidate_filings.to_csv(ecms_output_dir / "fundamental_filings_ecms.csv", index=False)
    candidate_evidence.to_csv(ecms_output_dir / "fundamental_evidence_ecms.csv", index=False)

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
    """Attach the six informational groups without changing fundamental decisions."""
    result = attach_valuation(assessed)
    symbols = result["TckrSymb"].astype(str).str.strip().str.upper()
    passed = result.get(
        "FundamentalShortlistStatus", pd.Series("", index=result.index)
    ).astype(str).str.upper().eq("PASS")
    pass_symbols = sorted(set(symbols.loc[passed]))

    news_columns = [
        "TckrSymb", "NewsWindowStart", "NewsWindowEnd", "OfficialStatus",
        "SecondaryStatus", "CatalystStatus", "CatalystSignalStatus",
        "StrongCatalystCount", "NegativeRiskCount", "OfficialCount", "SecondaryCount",
    ]
    if pass_symbols:
        news, news_audit = collect_catalysts(result.loc[passed].copy(), as_of_date)
        events, event_audit = collect_upcoming_events(pass_symbols, as_of_date)
        deals, deal_audit = collect_bulk_block_deals(pass_symbols, as_of_date)
    else:
        news = pd.DataFrame(columns=[
            "TckrSymb", "PublishedDate", "Headline", "Source", "SourceType",
            "URL", "Impact", "CatalystSignalStatus", "RiskFlags",
        ])
        news_audit = pd.DataFrame(columns=news_columns)
        events = pd.DataFrame(columns=[
            "TckrSymb", "EventDate", "EventType", "EventDetails",
            "Source", "SourceType", "SourceURL", "IsResultEvent",
        ])
        event_audit = pd.DataFrame(columns=[
            "TckrSymb", "UpcomingEventsStatus", "UpcomingEvents", "NextResultDate",
            "NextResultDetails", "EventCalendarSourceURL",
        ])
        deals = pd.DataFrame(columns=[
            "TckrSymb", "DealDate", "DealType", "ClientName", "Side", "Quantity",
            "PriceINR", "Remarks", "Source", "SourceType", "SourceURL",
        ])
        deal_audit = pd.DataFrame(columns=[
            "TckrSymb", "BulkBlockDealStatus", "BulkDealCount", "BlockDealCount",
            "BulkBuyers", "BulkSellers", "BlockBuyers", "BlockSellers",
            "BulkBlockLookbackStart", "BulkBlockLookbackEnd", "BulkBlockSourceURL",
        ])

    result["Last5DayNews"] = "NOT COLLECTED_FUNDAMENTAL_NOT_PASS"
    if not news.empty:
        summaries = {}
        for symbol, rows in news.groupby(news["TckrSymb"].astype(str).str.upper()):
            summaries[symbol] = " | ".join(
                f"{row.get('PublishedDate','')}: {row.get('Headline','')}"
                for _, row in rows.sort_values("PublishedDate", ascending=False).head(5).iterrows()
            )
        result["Last5DayNews"] = [
            summaries.get(symbol, "NO_MATCHED_NEWS_IN_LAST_5_DAYS") if is_pass
            else "NOT COLLECTED_FUNDAMENTAL_NOT_PASS"
            for symbol, is_pass in zip(symbols, passed)
        ]

    news_defaults = {
        "NewsWindowStart": "", "NewsWindowEnd": "",
        "OfficialStatus": "NOT_COLLECTED_FUNDAMENTAL_NOT_PASS",
        "SecondaryStatus": "NOT_COLLECTED_FUNDAMENTAL_NOT_PASS",
        "CatalystStatus": "NOT_COLLECTED_FUNDAMENTAL_NOT_PASS",
        "CatalystSignalStatus": "NOT_COLLECTED_FUNDAMENTAL_NOT_PASS",
        "StrongCatalystCount": 0, "NegativeRiskCount": 0,
        "OfficialCount": 0, "SecondaryCount": 0,
    }
    for column, default in news_defaults.items():
        result[column] = default
    if not news_audit.empty:
        result = result.drop(columns=[c for c in news_audit.columns if c != "TckrSymb" and c in result.columns])
        result = result.merge(news_audit, on="TckrSymb", how="left", validate="one_to_one")
    for column, default in news_defaults.items():
        result[column] = result[column].fillna(default)
    result.loc[passed & result["CatalystStatus"].astype(str).str.upper().eq("WAIT_FOR_DATA"), "Last5DayNews"] = "WAIT_FOR_DATA"
    result.loc[passed & result["CatalystStatus"].astype(str).str.upper().eq("NO_NEWS_FOUND"), "Last5DayNews"] = "NO_NEWS_FOUND"
    event_defaults = {
        "UpcomingEventsStatus": "NOT_COLLECTED_FUNDAMENTAL_NOT_PASS",
        "UpcomingEvents": "NOT COLLECTED_FUNDAMENTAL_NOT_PASS",
        "NextResultDate": "NOT COLLECTED_FUNDAMENTAL_NOT_PASS",
        "NextResultDetails": "",
        "EventCalendarSourceURL": "",
    }
    if not event_audit.empty:
        result = result.drop(columns=[c for c in event_audit.columns if c != "TckrSymb" and c in result.columns])
        result = result.merge(event_audit, on="TckrSymb", how="left", validate="one_to_one")
    for column, default in event_defaults.items():
        result[column] = result[column].fillna(default)
    deal_defaults = {
        "BulkBlockDealStatus": "NOT_COLLECTED_FUNDAMENTAL_NOT_PASS",
        "BulkDealCount": 0, "BlockDealCount": 0,
        "BulkBuyers": "", "BulkSellers": "", "BlockBuyers": "", "BlockSellers": "",
        "BulkBlockDealSummary": "",
        "BulkBlockLookbackStart": "", "BulkBlockLookbackEnd": "", "BulkBlockSourceURL": "",
    }
    if not deal_audit.empty:
        result = result.drop(columns=[c for c in deal_audit.columns if c != "TckrSymb" and c in result.columns])
        result = result.merge(deal_audit, on="TckrSymb", how="left", validate="one_to_one")
    for column, default in deal_defaults.items():
        result[column] = result[column].fillna(default)
    result["RVOLInformationStatus"] = result.get("RVOLDataStatus", pd.Series("NOT AVAILABLE", index=result.index))
    return result, news, events, deals


def run_eod():
    page=fetch_volume_gainers()
    eligible,board_source=_eligible_page_equities(page)
    if eligible.empty: raise RuntimeError("WAIT_FOR_DATA: no official Main Board equity symbols found on NSE Volume Gainers page")
    # Manual runs may be started on weekends/holidays. The NSE Volume Gainers
    # page then represents the most recently completed cash-market session.
    # Tag research with that official session date instead of rejecting today's
    # calendar date when today is not a trading day.
    eod_date=expected_latest_completed_session()
    if not is_trading_session(eod_date):
        raise RuntimeError(f"WAIT_FOR_DATA: resolved EOD date {eod_date} is not an official NSE equity trading session")
    eligible["EODDate"]=eod_date.isoformat(); eligible["PageSource"]=NSE_PAGE
    eligible["MainBoardSource"]=board_source
    eligible=attach_page_rvol(eligible,eod_date)
    assessed=assess_page_fundamentals(eligible,eod_date)
    assessed["EODConfirmationLabel"] = assessed["FundamentalShortlistStatus"].astype(str).str.upper().map({
      "PASS":"EOD_FUNDAMENTAL_PASS", "FAIL":"EOD_FUNDAMENTAL_FAIL"
    }).fillna("EOD_FUNDAMENTAL_WAIT_FOR_DATA")
    assessed, news, events, deals = attach_information(assessed, eod_date)
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
    news.to_csv(OUTPUT_DIR/"volume_gainers_catalysts.csv",index=False)
    events.to_csv(OUTPUT_DIR/"volume_gainers_upcoming_events.csv",index=False)
    deals.to_csv(OUTPUT_DIR/"volume_gainers_bulk_block_deals.csv",index=False)
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    state_columns=["TckrSymb","CompanyName","PageVolume","LTP","ChangePct","AvgVolume1W",
      "VolumeChangeTimes1W","AvgVolume2W","VolumeChangeTimes2W","AvgVolume20D","RVOL",
      "RVOLDataStatus","EODDate"]
    for column in ("FundamentalShortlistStatus", "StrongFundamentalNotForwardedReason",
                   "FundamentalPassStatus"):
        if column in assessed.columns:
            state_columns.append(column)
    state=assessed[state_columns].copy()
    state=state.rename(columns={
      "FundamentalShortlistStatus":"EODFundamentalShortlistStatus",
      "StrongFundamentalNotForwardedReason":"EODFundamentalNotForwardedReason"})
    state["EODStrongFundamentalStatus"] = state["EODFundamentalShortlistStatus"].astype(str).str.upper().map({
        "PASS": "EOD_FUNDAMENTAL_PASS",
        "FAIL": "EOD_FUNDAMENTAL_FAIL",
    }).fillna("EOD_FUNDAMENTAL_WAIT_FOR_DATA")
    state.to_csv(STATE_FILE,index=False)
    provider_diag_path = OUTPUT_DIR / "fundamental_provider_diagnostics.csv"
    provider_diag = pd.read_csv(provider_diag_path) if provider_diag_path.exists() and provider_diag_path.stat().st_size else pd.DataFrame()
    provider_status = provider_diag.get("ProviderStatus", pd.Series(dtype=str)).astype(str).str.upper()
    free_attempted = provider_diag.get("FreeSourcesAttempted", pd.Series(False, index=provider_diag.index)).astype(str).str.lower().isin({"true", "1", "yes"})
    shortlist_status = assessed["FundamentalShortlistStatus"].astype(str).str.upper()
    summary={"status":"PASS","eod_date_ist":eod_date.isoformat(),"nse_page":NSE_PAGE,
      "page_rows":int(len(page)),"eligible_mainboard_equities":int(len(eligible)),
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
      "page_limit_note":"Processes every row returned by NSE page; page currently labels table Top 25.",
      "generated_at_ist":datetime.now(IST).isoformat(),"state_file":str(STATE_FILE)}
    (OUTPUT_DIR/"volume_gainers_eod_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2)); return summary
def _strong_fundamental_mask(frame):
    """Fundamental PASS alone defines the morning pass; no score/coverage gate."""
    if frame.empty:
        return pd.Series(False, index=frame.index)
    shortlist = frame.get("FundamentalShortlistStatus", pd.Series("", index=frame.index)).astype(str).str.upper()
    return shortlist.eq("PASS")


def _confirmation_status(eod_pass, present, morning_pass):
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
    expected_eod = expected_latest_completed_session().isoformat()
    stored_dates = set(previous.get("EODDate", pd.Series(dtype=str)).dropna().astype(str))
    if stored_dates != {expected_eod}:
        raise RuntimeError(f"WAIT_FOR_DATA: cached EOD page snapshot dates {sorted(stored_dates)} do not match latest completed NSE session {expected_eod}")
    live=fetch_volume_gainers()
    mainboard,board_source=load_official_mainboard_symbols()
    live=live[live["TckrSymb"].isin(mainboard)].copy()
    if live.empty:
        raise RuntimeError("WAIT_FOR_DATA: no eligible Main Board candidates on 09:20 Volume Gainers page")

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
    morning_assessed, morning_news, morning_events, morning_deals = attach_information(morning_assessed, today)
    morning_news.to_csv(OUTPUT_DIR/"volume_gainers_morning_news.csv", index=False)
    morning_events.to_csv(OUTPUT_DIR/"volume_gainers_morning_upcoming_events.csv", index=False)
    morning_deals.to_csv(OUTPUT_DIR/"volume_gainers_morning_bulk_block_deals.csv", index=False)
    morning_assessed["MorningStrongFundamentalStatus"] = (
        _strong_fundamental_mask(morning_assessed).map({True:"MORNING_FUNDAMENTAL_PASS",False:"MORNING_NOT_FUNDAMENTAL_PASS"})
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
             "EOD_FUNDAMENTAL_PASS_REPEAT" if symbol in previous_symbols and present and eod_strong else
             "EOD_REPEAT_NOT_FUNDAMENTAL_PASS" if symbol in previous_symbols and present else
             "EOD_ONLY_NOT_ON_MORNING_PAGE" if symbol in previous_symbols else "NEW_MORNING_ENTRY"
          ),
          "EODPageVolume":old.get("PageVolume"),
          "MorningPageVolume":current.get("PageVolume"),
          "EODLTP":old.get("LTP"),"MorningLTP":current.get("LTP"),
          "EODRVOL":old.get("RVOL"),
          "MorningRVOL":"NOT AVAILABLE",
          "MorningRVOLDataStatus":"PARTIAL_SESSION_NOT_COMPARABLE_TO_FULL_DAY_20D_AVERAGE",
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
          "EODFundamentalShortlistStatus":old.get("EODFundamentalShortlistStatus",""),
          "EODStrongFundamentalStatus":old.get("EODStrongFundamentalStatus",""),
          "EODFundamentalNotForwardedReason":old.get("EODFundamentalNotForwardedReason",""),
          "MorningFundamentalShortlistStatus":assessed.get("FundamentalShortlistStatus","NOT_ASSESSED"),
          "MorningFundamentalNotForwardedReason":assessed.get("StrongFundamentalNotForwardedReason",""),
          "MorningStrongFundamentalStatus":assessed.get("MorningStrongFundamentalStatus","NOT_ASSESSED"),
          "ConfirmationStatus":confirmation,
          "MorningChangePct":current.get("ChangePct"),
          "MorningVolumeChangeTimes1W":current.get("VolumeChangeTimes1W"),
          "MorningVolumeChangeTimes2W":current.get("VolumeChangeTimes2W"),
          "DataQuality":"LIVE_PAGE_AND_FUNDAMENTALS" if present and assessed else
            "NOT_ON_CURRENT_PAGE" if not present else "PARTIAL_LIVE_DATA"})
    report=pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    report.to_csv(OUTPUT_DIR/"volume_gainers_morning_recheck.csv",index=False)
    # Preserve the original EOD snapshot; only the fundamental workspace cache
    # is enriched by the morning assessment.
    summary={"status":"PASS","morning_time_ist":datetime.now(IST).isoformat(),
      "previous_eod_symbols":len(previous_symbols),"current_page_eligible_symbols":len(live_symbols),
      "new_entries":int(report["MorningStatus"].eq("NEW_MORNING_ENTRY").sum()),
      "morning_assessed_candidates":int(len(morning_assessed)),
      "morning_assessment_rows":int(report["MorningStrongFundamentalStatus"].ne("NOT_ASSESSED").sum()),
      "morning_fundamental_pass":int(report["MorningStrongFundamentalStatus"].eq("MORNING_FUNDAMENTAL_PASS").sum()),
      "morning_wait_for_data":int(morning_assessed["FundamentalShortlistStatus"].astype(str).str.upper().eq("WAIT_FOR_DATA").sum()),
      "morning_new_entries":int(report["MorningStatus"].eq("NEW_MORNING_ENTRY").sum()),
      "eod_fundamental_pass_repeats":int(report["MorningStatus"].eq("EOD_FUNDAMENTAL_PASS_REPEAT").sum()),
      "eod_only_not_on_morning_page":int(report["MorningStatus"].eq("EOD_ONLY_NOT_ON_MORNING_PAGE").sum()),
      "double_confirmed":int(report["ConfirmationStatus"].eq("DOUBLE_CONFIRMED_EOD_MORNING").sum()),
      "eod_pass_not_morning_pass":int(report["ConfirmationStatus"].eq("EOD_PASS_MORNING_NOT_PASS").sum()),
      "nse_page":NSE_PAGE,
      "note":"Every eligible 09:20 page candidate receives the same fundamental-only gate. Repeat/new/disappeared labels are informational; no other data field rejects a stock."}
    (OUTPUT_DIR/"volume_gainers_morning_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2)); return summary
def main():
    parser=argparse.ArgumentParser(description="ECMS NSE Volume Gainers scanner")
    parser.add_argument("--mode",choices=("eod","morning"),required=True)
    args=parser.parse_args()
    run_eod() if args.mode=="eod" else run_morning()
if __name__=="__main__": main()
