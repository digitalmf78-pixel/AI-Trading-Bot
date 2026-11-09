import pandas as pd

from breakout_retest_observation import build_breakout_retest_observation


def _history(with_event=True, exact_touch=True):
    dates = pd.bdate_range(end="2026-10-23", periods=53)
    frame = pd.DataFrame({
        "TckrSymb": ["AAA"] * len(dates),
        "Date": dates,
        "OpnPric": [99.0] * len(dates),
        "HghPric": [105.0] * len(dates),
        "LwPric": [95.0] * len(dates),
        "ClsPric": [100.0] * len(dates),
        "TtlTradgVol": [1000.0] * len(dates),
    })
    if with_event:
        frame.loc[50, ["OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"]] = [
            108, 112, 107, 111, 2500
        ]
        if exact_touch:
            frame.loc[51, ["OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"]] = [
                106, 110, 104, 107, 800
            ]
        else:
            frame.loc[51, ["OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"]] = [
                107, 111, 106, 109, 800
            ]
        frame.loc[52, ["OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"]] = [
            107, 111, 106, 109, 700
        ]
    return frame


def _candidate():
    return pd.DataFrame([{"TckrSymb": "AAA"}])


def test_retest_observation_uses_existing_breakout_and_records_exact_level_touch():
    history = _history()
    row = build_breakout_retest_observation(_candidate(), [history]).iloc[0]
    assert row["RetestObservationStatus"] == "POST_BREAKOUT_PRICE_OBSERVATIONS_AVAILABLE"
    assert row["LastBreakoutDate"] == history.loc[50, "Date"].date().isoformat()
    assert row["BreakoutReferenceLevel"] == 105
    assert row["SessionsSinceBreakout"] == 2
    assert row["ExactLevelTouchObserved"] == True
    assert row["FirstExactLevelTouchDate"] == history.loc[51, "Date"].date().isoformat()


def test_retest_observation_does_not_claim_exact_touch_when_price_never_crosses_level():
    row = build_breakout_retest_observation(
        _candidate(), [_history(exact_touch=False)]
    ).iloc[0]
    assert row["ExactLevelTouchObserved"] is False
    assert row["RetestObservationStatus"] == "POST_BREAKOUT_PRICE_OBSERVATIONS_AVAILABLE"


def test_no_historical_breakout_is_descriptive_not_a_failure_or_gate():
    row = build_breakout_retest_observation(
        _candidate(), [_history(with_event=False)]
    ).iloc[0]
    assert row["RetestObservationStatus"] == "NO_PRIOR_BREAKOUT_EVENT_OBSERVED_IN_AVAILABLE_CACHE"
    assert row["ExactLevelTouchObserved"] == "NOT_OBSERVED"


def test_missing_symbol_market_session_waits_without_backfilling():
    history = _history()
    missing = history.iloc[[30]].copy()
    missing["TckrSymb"] = "OTHER"
    symbol_history = history[history["Date"] != missing.iloc[0]["Date"]]
    row = build_breakout_retest_observation(
        _candidate(), [pd.concat([symbol_history, missing], ignore_index=True)]
    ).iloc[0]
    assert row["RetestObservationStatus"] == "WAIT_FOR_DATA"


def test_duplicate_candidate_symbol_returns_one_wait_row_per_input_row():
    candidates = pd.concat([_candidate(), _candidate()], ignore_index=True)
    report = build_breakout_retest_observation(candidates, [_history()])
    assert len(report) == 2
    assert report["RetestObservationStatus"].eq("WAIT_FOR_DATA").all()


def test_retest_module_is_integrated_after_existing_breakout_detection():
    from pathlib import Path
    source = Path("volume_gainer.py").read_text(encoding="utf-8")
    assert "from breakout_retest_observation import build_breakout_retest_observation" in source
    assert source.index("result = (\n        calculate_breakout_pullback(") < source.index(
        "retest_observation = build_breakout_retest_observation("
    )
    assert "never changes selection or entry gates" in source
