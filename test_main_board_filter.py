"""Tests for the official NSE Main Board-only eligibility gate."""
import pandas as pd
import pytest

from main_board_filter import apply_main_board_filter, _symbols_from_csv


def test_only_official_main_board_symbols_pass_and_sme_is_always_excluded():
    frame = pd.DataFrame({"TckrSymb": ["RELIANCE", "ABCOTS", "AGUL", "UNKNOWN", " agul "]})
    filtered, audit = apply_main_board_filter(
        frame,
        main_board_symbols={"RELIANCE", "ABCOTS", "AGUL"},
        sme_symbols={"ABCOTS", "AGUL"},
    )
    assert filtered["TckrSymb"].tolist() == ["RELIANCE"]
    status = dict(zip(audit["TckrSymb"], audit["MainBoardStatus"]))
    assert status["RELIANCE"] == "PASS_MAIN_BOARD"
    assert status["ABCOTS"] == "EXCLUDED_SME"
    assert status["AGUL"] == "EXCLUDED_SME"
    assert status["UNKNOWN"] == "EXCLUDED_UNVERIFIED_CLASSIFICATION"


def test_official_csv_symbol_column_detection():
    payload = b"SYMBOL,NAME OF COMPANY,SERIES\nABC,ABC Limited,EQ\nXYZ,XYZ Limited,BE\n"
    assert _symbols_from_csv(payload) == {"ABC", "XYZ"}


def test_invalid_official_csv_is_rejected():
    with pytest.raises(ValueError):
        _symbols_from_csv(b"NAME,DESCRIPTION\nABC,Something\n")
