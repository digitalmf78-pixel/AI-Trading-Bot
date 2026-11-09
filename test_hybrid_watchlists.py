import pandas as pd

from hybrid_watchlists import (
    write_early_hybrid_watchlists,
    write_breakout_ready_watchlist,
    write_confirmed_entry_watchlist,
)


def test_early_accumulation_watchlist_keeps_delivery_ab_names_without_vcp_or_breakout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    accumulation = pd.DataFrame([
        {"TckrSymb": "AAA", "AsOfDate": "2026-10-23", "DeliveryCategory": "A_ONLY",
         "DeliveryEvidenceStatus": "OBSERVATIONS_AVAILABLE", "BreakoutStatus": "No Breakout"},
        {"TckrSymb": "BBB", "AsOfDate": "2026-10-23", "DeliveryCategory": "B_ONLY",
         "DeliveryEvidenceStatus": "WAIT_FOR_DATA", "BreakoutStatus": "WAIT_FOR_DATA"},
    ])
    vcp = pd.DataFrame([
        {"TckrSymb": "AAA", "AsOfDate": "2026-10-23", "VCPObservationStatus": "WAIT_FOR_DATA"},
        {"TckrSymb": "BBB", "AsOfDate": "2026-10-23", "VCPObservationStatus": "WAIT_FOR_DATA"},
    ])
    accumulation_out, base_out = write_early_hybrid_watchlists(accumulation, vcp)
    assert set(accumulation_out["TckrSymb"]) == {"AAA", "BBB"}
    assert accumulation_out.set_index("TckrSymb").loc["AAA", "WatchlistStatus"] == "ACCUMULATION_WATCH"
    assert accumulation_out.set_index("TckrSymb").loc["BBB", "WatchlistStatus"] == "WAIT_FOR_DATA"
    assert len(base_out) == 2
    assert (tmp_path / "outputs/v8_hybrid_potential_accumulation_watchlist.csv").exists()


def test_base_forming_is_only_an_observational_two_step_tag_not_vcp_confirmed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    accumulation = pd.DataFrame([{
        "TckrSymb": "AAA", "AsOfDate": "2026-10-23",
        "DeliveryEvidenceStatus": "OBSERVATIONS_AVAILABLE",
    }])
    vcp = pd.DataFrame([{
        "TckrSymb": "AAA", "AsOfDate": "2026-10-23",
        "VCPObservationStatus": "COMPLETE", "VCPStatus": "NOT_CLASSIFIED",
        "ContractionTransitionsObserved": 2,
    }])
    _, base = write_early_hybrid_watchlists(accumulation, vcp)
    assert base.iloc[0]["WatchlistStatus"] == "BASE_FORMING"
    assert base.iloc[0]["VCPStatus"] == "NOT_CLASSIFIED"
    assert "NOT_VCP_CONFIRMED" in base.iloc[0]["WatchlistReason"]


def test_breakout_ready_watchlist_uses_existing_statuses_and_chase_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([
        {"TckrSymb": "AAA", "BreakoutStatus": "Strong Breakout", "PullbackStatus": "No Pullback"},
        {"TckrSymb": "BBB", "BreakoutStatus": "Near Breakout", "PullbackStatus": "No Pullback"},
        {"TckrSymb": "CCC", "BreakoutStatus": "Breakout", "PullbackStatus": "No Pullback", "ChaseStatus": "CHASE"},
        {"TckrSymb": "DDD", "BreakoutStatus": "WAIT_FOR_DATA", "PullbackStatus": "WAIT_FOR_DATA"},
    ])
    output = write_breakout_ready_watchlist(candidates).set_index("TckrSymb")
    assert output.loc["AAA", "WatchlistStatus"] == "BREAKOUT_CONFIRMED"
    assert output.loc["BBB", "WatchlistStatus"] == "ENTRY_CANDIDATE"
    assert output.loc["CCC", "WatchlistStatus"] == "CHASED"
    assert output.loc["DDD", "WatchlistStatus"] == "WAIT_FOR_DATA"


def test_confirmed_entry_requires_existing_final_eod_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = pd.DataFrame([
        {"TckrSymb": "AAA", "EODWatchlistStatus": "WATCH", "RiskControlStatus": "PASS",
         "MandatoryConfirmationStatus": "PASS", "RiskRewardStatus": "PASS", "ChaseStatus": "CLEAR"},
        {"TckrSymb": "BBB", "EODWatchlistStatus": "WATCH", "RiskControlStatus": "PASS",
         "MandatoryConfirmationStatus": "WAIT_FOR_DATA", "RiskRewardStatus": "PASS", "ChaseStatus": "CLEAR"},
        {"TckrSymb": "CCC", "EODWatchlistStatus": "WAIT_FOR_DATA"},
    ])
    output = write_confirmed_entry_watchlist(candidates).set_index("TckrSymb")
    assert output.loc["AAA", "WatchlistStatus"] == "ENTRY_CANDIDATE"
    assert output.loc["BBB", "WatchlistStatus"] == "WAIT_FOR_DATA"
    assert output.loc["CCC", "WatchlistStatus"] == "WAIT_FOR_DATA"



def test_empty_early_reports_still_write_all_watchlist_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    accumulation, base = write_early_hybrid_watchlists(pd.DataFrame(), pd.DataFrame())
    assert accumulation.empty
    assert base.empty
    assert (tmp_path / "outputs/v8_hybrid_potential_accumulation_watchlist.csv").exists()
    assert (tmp_path / "outputs/v8_hybrid_base_vcp_watchlist.csv").exists()
