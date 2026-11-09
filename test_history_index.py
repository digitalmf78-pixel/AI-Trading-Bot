import pandas as pd

from history_index import build_price_history_index, candidate_price_history


def test_history_index_matches_symbol_series_and_merges_current_candidate():
    historical = [
        pd.DataFrame([
            {"TckrSymb": "ABC", "SctySrs": "EQ", "Date": "2026-11-05", "ClsPric": 10, "HghPric": 11, "LwPric": 9, "TtlTradgVol": 100},
            {"TckrSymb": "ABC", "SctySrs": "BE", "Date": "2026-11-05", "ClsPric": 20, "HghPric": 21, "LwPric": 19, "TtlTradgVol": 200},
            {"TckrSymb": "XYZ", "SctySrs": "EQ", "Date": "2026-11-05", "ClsPric": 30, "HghPric": 31, "LwPric": 29, "TtlTradgVol": 300},
        ]),
        pd.DataFrame([
            {"TckrSymb": "ABC", "SctySrs": "EQ", "Date": "2026-11-06", "ClsPric": 12, "HghPric": 13, "LwPric": 11, "TtlTradgVol": 110},
            {"TckrSymb": "ABC", "SctySrs": "EQ", "Date": "2026-11-10", "ClsPric": 999, "HghPric": 999, "LwPric": 999, "TtlTradgVol": 999},
        ]),
    ]
    index, dates = build_price_history_index(historical, pd.Timestamp("2026-11-09").date())
    candidate = pd.Series({
        "TckrSymb": "ABC", "SctySrs": "EQ", "Date": "2026-11-09",
        "ClsPric": 14, "HghPric": 15, "LwPric": 13, "TtlTradgVol": 120,
        "PriceChangePct": 2.0,
    })

    result = candidate_price_history(index, candidate, "2026-11-09")

    assert dates == [pd.Timestamp("2026-11-05").date(), pd.Timestamp("2026-11-06").date(), pd.Timestamp("2026-11-09").date()]
    assert result["Date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-11-05", "2026-11-06", "2026-11-09"]
    assert result["ClsPric"].tolist() == [10, 12, 14]
    assert result.iloc[-1]["PriceChangePct"] == 2.0
    assert set(result["SctySrs"]) == {"EQ"}


def test_history_index_preserves_duplicate_session_rows_for_wait_for_data():
    duplicate_day = pd.DataFrame([
        {"TckrSymb": "ABC", "SctySrs": "EQ", "Date": "2026-11-06", "ClsPric": 10},
        {"TckrSymb": "ABC", "SctySrs": "EQ", "Date": "2026-11-06", "ClsPric": 11},
    ])
    index, _ = build_price_history_index([duplicate_day], "2026-11-09")
    candidate = pd.Series({"TckrSymb": "ABC", "SctySrs": "EQ", "ClsPric": 12})

    result = candidate_price_history(index, candidate, "2026-11-09")

    assert len(result[result["Date"].dt.date == pd.Timestamp("2026-11-06").date()]) == 2


def test_history_index_supports_sources_without_security_series_column():
    raw = pd.DataFrame([
        {"TckrSymb": "ABC", "Date": "2026-11-06", "ClsPric": 10},
    ])
    index, _ = build_price_history_index([raw], "2026-11-09")

    result = candidate_price_history(
        index, pd.Series({"TckrSymb": "ABC", "SctySrs": "EQ"}), "2026-11-09"
    )

    assert result["ClsPric"].iloc[0] == 10
