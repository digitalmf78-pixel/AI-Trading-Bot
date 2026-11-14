from pathlib import Path

import pandas as pd

from scripts.research_fundamental_cache_audit import build_audit


def test_inventory_counts_symbols_metrics_and_duplicate_rows(tmp_path):
    inputs = tmp_path / "data/inputs"
    history = tmp_path / "data/cache/fundamental_history"
    inputs.mkdir(parents=True)
    history.mkdir(parents=True)
    pd.DataFrame([
        {"TckrSymb": "AAA", "RevenueGrowthPct": "12.5", "PublicationDateStatus": "VERIFIED"},
        {"TckrSymb": "BBB", "RevenueGrowthPct": "", "PublicationDateStatus": "UNVERIFIED"},
        {"TckrSymb": "BBB", "RevenueGrowthPct": "4", "PublicationDateStatus": "UNVERIFIED"},
    ]).to_csv(inputs / "fundamental_metrics.csv", index=False)
    pd.DataFrame([
        {"TckrSymb": "AAA", "ROEPercent": "10", "MetricCalculationBasis": "TTM"},
    ]).to_csv(history / "fundamental_metrics_2026-11-13.csv", index=False)

    table, summary = build_audit(tmp_path)
    current = table[table.CacheType == "CURRENT"].iloc[0]
    snapshot = table[table.CacheType == "HISTORICAL_SNAPSHOT"].iloc[0]
    assert current.Rows == 3
    assert current.UniqueSymbols == 2
    assert current.DuplicateSymbolRows == 2
    assert current.Available_RevenueGrowthPct == 2
    assert snapshot.UniqueSymbols == 1
    assert summary["LatestSnapshotDate"] == "2026-11-13"
    assert summary["NoNetworkRequestsMade"] is True


def test_missing_cache_is_reported_without_creating_or_mutating_files(tmp_path):
    table, summary = build_audit(tmp_path)
    assert len(table) == 1
    assert table.iloc[0].Rows == 0
    assert summary["CurrentCacheExists"] is False
    assert summary["CacheFilesModified"] is False
