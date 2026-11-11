import pandas as pd

import hybrid_watchlists
from volume_gainer import calculate_accumulation_score, calculate_consolidation_score


def test_experimental_accumulation_alias_preserves_legacy_numeric_score():
    source = pd.DataFrame([{
        "TckrSymb": "ABC", "CLV": 1.0, "LowVolumeDays5D": 5,
        "PriceChangePct": 0.0, "RVOL": 1.2,
    }])
    result = calculate_accumulation_score(source)
    assert result.loc[0, "AccumulationScore"] == 100.0
    assert result.loc[0, "ExperimentalAccumulationScore"] == 100.0
    assert result.loc[0, "AccumulationStatus"] == "HIGH_ACCUMULATION"
    assert result.loc[0, "ExperimentalAccumulationStatus"].startswith(
        "EXPERIMENTAL_NOT_APPROVED_NOT_BACKTESTED_"
    )


def test_experimental_consolidation_alias_preserves_legacy_numeric_score():
    dates = pd.date_range("2026-10-01", periods=10, freq="B")
    history = pd.DataFrame([{
        "TckrSymb": "ABC", "Date": day, "ClsPric": 101.0,
        "TtlTradgVol": 1000, "OpnPric": 100.0, "HghPric": 102.0,
        "LwPric": 100.0,
    } for day in dates])
    result = calculate_consolidation_score(pd.DataFrame([{"TckrSymb": "ABC"}]), [history])
    assert result.loc[0, "ConsolidationScore"] == 90.0
    assert result.loc[0, "ExperimentalConsolidationScore"] == 90.0
    assert result.loc[0, "ExperimentalConsolidationStatus"].startswith(
        "EXPERIMENTAL_NOT_APPROVED_NOT_BACKTESTED_"
    )


def test_observation_watchlist_wording_is_not_a_trade_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(hybrid_watchlists, "BREAKOUT_PATH", tmp_path / "breakout.csv")
    source = pd.DataFrame([{
        "TckrSymb": "ABC", "ChaseStatus": "CLEAR",
        "BreakoutStatus": "Near Breakout", "PullbackStatus": "WAIT_FOR_DATA",
    }])
    result = hybrid_watchlists.write_breakout_ready_watchlist(source)
    assert result.loc[0, "WatchlistStatus"] == "BREAKOUT_PULLBACK_OBSERVATION"
    assert "NOT_A_TRADE_ENTRY" in result.loc[0, "WatchlistReason"]


def test_accumulation_watchlist_is_explicitly_unmeasured(monkeypatch, tmp_path):
    monkeypatch.setattr(hybrid_watchlists, "ACCUMULATION_PATH", tmp_path / "accumulation.csv")
    monkeypatch.setattr(hybrid_watchlists, "BASE_VCP_PATH", tmp_path / "base.csv")
    accumulation = pd.DataFrame([{
        "TckrSymb": "ABC", "AsOfDate": "2026-11-11",
        "DeliveryEvidenceStatus": "OBSERVATIONS_AVAILABLE",
    }])
    accumulation_out, _ = hybrid_watchlists.write_early_hybrid_watchlists(accumulation, pd.DataFrame())
    assert accumulation_out.loc[0, "WatchlistStatus"] == "ACCUMULATION_WATCH"
    assert "OBSERVATION_ONLY_NOT_MEASURED" in accumulation_out.loc[0, "WatchlistReason"]
