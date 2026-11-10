import pandas as pd
import pytest

from delivery_60_each_of_5_sessions import (
    eligible_mainboard_eq_symbols,
    filter_five_session_delivery,
)


def _sessions(values_by_symbol):
    dates = pd.bdate_range("2026-11-02", periods=5)
    sessions = []
    for index, day in enumerate(dates):
        rows = []
        for symbol, values in values_by_symbol.items():
            rows.append({"SYMBOL": symbol, "SERIES": "EQ", "DELIV_PER": values[index]})
        sessions.append((day.date(), pd.DataFrame(rows)))
    return sessions


def test_exactly_sixty_percent_passes_on_all_five_sessions():
    sessions = _sessions({"AAA": [60, 60, 60, 60, 60], "BBB": [61, 62, 63, 64, 65]})
    qualifying, audit, summary = filter_five_session_delivery(sessions)
    assert qualifying == ["AAA", "BBB"]
    assert len(audit) == 2
    assert audit["PASS_ALL_5D_GE_60"].all()
    assert audit.loc[audit.SYMBOL.eq("AAA"), "MIN_DELIVERY_5D"].iloc[0] == 60.0
    assert summary["qualifying_symbols"] == 2


def test_one_session_below_sixty_rejects_symbol():
    sessions = _sessions({"AAA": [60, 60, 59.99, 60, 60]})
    qualifying, audit, _ = filter_five_session_delivery(sessions)
    assert qualifying == []
    assert audit.empty


def test_symbol_missing_any_one_of_five_sessions_is_excluded():
    sessions = _sessions({"AAA": [65, 65, 65, 65, 65], "BBB": [65, 65, 65, 65, 65]})
    day, frame = sessions[2]
    sessions[2] = (day, frame.loc[frame.SYMBOL.ne("BBB")].copy())
    qualifying, _, summary = filter_five_session_delivery(sessions)
    assert qualifying == ["AAA"]
    assert summary["symbols_missing_any_session"] == 1


def test_duplicate_symbol_rows_are_ambiguous_and_excluded_for_that_session():
    sessions = _sessions({"AAA": [65, 65, 65, 65, 65], "BBB": [65, 65, 65, 65, 65]})
    day, frame = sessions[1]
    sessions[1] = (day, pd.concat([frame, frame.loc[frame.SYMBOL.eq("BBB")]], ignore_index=True))
    qualifying, _, _ = filter_five_session_delivery(sessions)
    assert qualifying == ["AAA"]


def test_official_universe_excludes_etf_sme_and_unverified_symbols_without_other_filters():
    sessions = _sessions({"AAA": [65, 65, 65, 65, 65], "ETF1": [70, 70, 70, 70, 70], "SME1": [80, 80, 80, 80, 80]})
    dates = [day for day, _ in sessions]
    eligible = {day: {"AAA"} for day in dates}
    qualifying, _, _ = filter_five_session_delivery(sessions, eligible_symbols_by_date=eligible)
    assert qualifying == ["AAA"]


def test_exactly_five_distinct_sessions_are_required():
    sessions = _sessions({"AAA": [65, 65, 65, 65, 65]})
    with pytest.raises(ValueError, match="Exactly 5"):
        filter_five_session_delivery(sessions[:4])
    sessions[4] = sessions[3]
    with pytest.raises(ValueError, match="Five distinct"):
        filter_five_session_delivery(sessions)


def test_official_universe_helper_excludes_etf_mutual_fund_sme_and_unknown_rows():
    bhav = pd.DataFrame([
        {"TckrSymb": "AAA", "SctySrs": "EQ", "ClsPric": 10, "TtlTradgVol": 100, "ISIN": "INE000A01001", "FinInstrmNm": "AAA LIMITED"},
        {"TckrSymb": "BBB", "SctySrs": "EQ", "ClsPric": 20, "TtlTradgVol": 200, "ISIN": "INE000B01001", "FinInstrmNm": "BBB LIMITED"},
        {"TckrSymb": "ETF1", "SctySrs": "EQ", "ClsPric": 10, "TtlTradgVol": 100, "ISIN": "INE000E01001", "FinInstrmNm": "ETF1"},
        {"TckrSymb": "MF1", "SctySrs": "EQ", "ClsPric": 10, "TtlTradgVol": 100, "ISIN": "INF000M01001", "FinInstrmNm": "MF1"},
        {"TckrSymb": "AMC1", "SctySrs": "EQ", "ClsPric": 10, "TtlTradgVol": 100, "ISIN": "INE000C01001", "FinInstrmNm": "AMC - BANKPSU"},
        {"TckrSymb": "ETFNAME", "SctySrs": "EQ", "ClsPric": 10, "TtlTradgVol": 100, "ISIN": "INE000F01001", "FinInstrmNm": "ABC EXCHANGE TRADED FUND"},
        {"TckrSymb": "SME1", "SctySrs": "EQ", "ClsPric": 10, "TtlTradgVol": 100, "ISIN": "INE000S01001", "FinInstrmNm": "SME LIMITED"},
        {"TckrSymb": "UNKNOWN", "SctySrs": "EQ", "ClsPric": 10, "TtlTradgVol": 100, "ISIN": "INE000U01001", "FinInstrmNm": "UNKNOWN LIMITED"},
        {"TckrSymb": "BE1", "SctySrs": "BE", "ClsPric": 10, "TtlTradgVol": 100, "ISIN": "INE000B01002", "FinInstrmNm": "BE SERIES"},
    ])
    eligible, summary = eligible_mainboard_eq_symbols(
        bhav,
        main_board_symbols={"AAA", "BBB", "ETF1", "MF1", "AMC1", "ETFNAME", "SME1"},
        sme_symbols={"SME1"},
        official_etf_symbols={"ETF1"},
    )
    assert eligible == {"AAA", "BBB"}
    assert summary["excluded_etf_mf_symbols"] == 4
    assert summary["excluded_sme_symbols"] == 1
    assert summary["excluded_unverified_symbols"] == 1
    assert summary["main_board_eligible_symbols"] == 2
