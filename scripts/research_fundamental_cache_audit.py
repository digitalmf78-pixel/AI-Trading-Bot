"""Read-only inventory of persisted NSE fundamental cache and dated snapshots.

Research only: this script never fetches data and never modifies cache inputs.
It emits coverage/provenance summaries so a full-universe refresh plan can be
based on actual cache contents rather than assumptions.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CURRENT = Path("data/inputs/fundamental_metrics.csv")
HISTORY = Path("data/cache/fundamental_history")
OUT = Path("outputs/research_fundamental_cache_audit")
METRICS = (
    "RevenueGrowthPct", "ProfitGrowthPct", "ROEPercent", "ROCEPercent",
    "DebtToEquity", "InterestCoverage", "OperatingCashFlowINR",
    "FreeCashFlowINR", "RevenueTTMINR", "NetProfitTTMINR",
    "PromoterHoldingPct", "FIIHoldingPct", "DIIHoldingPct",
    "PublicHoldingPct", "TrailingPE", "PriceToBook",
)
STATUS_FIELDS = (
    "PublicationDateStatus", "MetricPeriodAlignmentStatus",
    "MetricCalculationBasis", "TTMQuarterlyAlignmentStatus",
    "ValuationDataStatus", "ValuationPointInTimeStatus",
)
SNAPSHOT_RE = re.compile(r"fundamental_metrics_(\d{4}-\d{2}-\d{2})\.csv$")


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    if path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def _nonblank(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().ne("") & series.astype(str).str.lower().ne("nan")


def _summarize(path: Path, kind: str, asof: str = "") -> dict:
    frame = _read(path)
    symbols = frame.get("TckrSymb", pd.Series(dtype=str)).astype(str).str.strip().str.upper()
    valid_symbols = symbols[symbols.ne("") & symbols.ne("NAN") & symbols.ne("NONE")]
    row = {
        "CacheType": kind, "SnapshotDate": asof, "File": str(path),
        "FileBytes": path.stat().st_size if path.exists() else 0,
        "Rows": int(len(frame)), "UniqueSymbols": int(valid_symbols.nunique()),
        "DuplicateSymbolRows": int(valid_symbols.duplicated(keep=False).sum()),
        "InvalidSymbolRows": int((symbols.eq("") | symbols.eq("NAN") | symbols.eq("NONE")).sum()),
    }
    for metric in METRICS:
        row[f"Available_{metric}"] = int(_nonblank(frame[metric]).sum()) if metric in frame else 0
    for field in STATUS_FIELDS:
        if field in frame:
            counts = frame[field].replace("", "BLANK").value_counts(dropna=False).to_dict()
            row[f"{field}_CountsJSON"] = json.dumps({str(k): int(v) for k, v in counts.items()}, sort_keys=True)
        else:
            row[f"{field}_CountsJSON"] = "{}"
    for field in ("Source", "FinancialPeriodEnd", "PublicationDate", "OfficialFilingURL",
                  "DataRetrievedAtUTC", "AsOfDate"):
        row[f"{field}_Nonblank"] = int(_nonblank(frame[field]).sum()) if field in frame else 0
    return row


def build_audit(root: Path = ROOT) -> tuple[pd.DataFrame, dict]:
    current_path = root / CURRENT
    history_dir = root / HISTORY
    rows = [_summarize(current_path, "CURRENT")]
    snapshots = []
    if history_dir.exists():
        for path in sorted(history_dir.glob("fundamental_metrics_*.csv")):
            match = SNAPSHOT_RE.fullmatch(path.name)
            if match:
                snapshots.append((match.group(1), path))
    for asof, path in snapshots:
        rows.append(_summarize(path, "HISTORICAL_SNAPSHOT", asof))
    table = pd.DataFrame(rows)
    nonempty = table[table["Rows"] > 0]
    latest = max((d for d, _ in snapshots), default="")
    summary = {
        "GeneratedAtUTC": datetime.now(timezone.utc).isoformat(),
        "CurrentCacheExists": current_path.exists(),
        "CurrentCacheBytes": current_path.stat().st_size if current_path.exists() else 0,
        "HistorySnapshotCount": len(snapshots),
        "LatestSnapshotDate": latest,
        "LatestSnapshotRows": int(nonempty.loc[nonempty["SnapshotDate"].eq(latest), "Rows"].iloc[0])
            if latest and nonempty["SnapshotDate"].eq(latest).any() else 0,
        "NonemptySnapshotCount": int((table["Rows"] > 0).sum()),
        "SnapshotDateRange": [snapshots[0][0], snapshots[-1][0]] if snapshots else [],
        "DuplicateSymbolRowsAcrossFilesAreNotSummed": True,
        "UniverseCoverageLimitation": (
            "This inventory measures symbols present in cache files only. "
            "It does not claim full NSE Mainboard coverage without a dated, "
            "independently validated Mainboard universe manifest."
        ),
        "NoNetworkRequestsMade": True,
        "CacheFilesModified": False,
    }
    return table, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    table, summary = build_audit(args.root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.output_dir / "fundamental_cache_inventory.csv", index=False)
    (args.output_dir / "fundamental_cache_inventory_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print(table[["CacheType", "SnapshotDate", "Rows", "UniqueSymbols",
                 "DuplicateSymbolRows", "FileBytes"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
