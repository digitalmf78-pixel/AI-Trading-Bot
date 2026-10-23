import tempfile
from pathlib import Path
import pandas as pd

from fundamental_official_filings import apply_official_publication_dates, _period_end_from_description


def test_period_end_parser_requires_period_context():
    assert str(_period_end_from_description("Financial Results for quarter ended June 30, 2026")) == "2026-06-30"
    assert str(_period_end_from_description("Results discussed at board meeting on 30-Jun-2026")) == "None"


def test_exact_symbol_and_period_verified_only_before_cutoff(tmp_path):
    records = pd.DataFrame([{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30"}])
    filings = pd.DataFrame([{
        "TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30", "PublicationDate": "2026-07-25",
        "PublicationDateStatus": "VERIFIED", "OfficialFilingURL": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        "OfficialSource": "NSE corporate announcements",
    }])
    out = apply_official_publication_dates(records, "2026-10-22", filings=filings,
        cache_path=tmp_path/"cache.csv", diagnostics_path=tmp_path/"diag.csv")
    assert out.loc[0, "PublicationDateStatus"] == "VERIFIED"
    assert str(out.loc[0, "PublicationDate"])[:10] == "2026-07-25"


def test_future_publication_and_future_period_are_unverified(tmp_path):
    records = pd.DataFrame([
        {"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30"},
        {"TckrSymb": "XYZ", "FinancialPeriodEnd": "2026-12-31"},
    ])
    filings = pd.DataFrame([
        {"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30", "PublicationDate": "2026-10-23", "PublicationDateStatus": "VERIFIED"},
        {"TckrSymb": "XYZ", "FinancialPeriodEnd": "2026-12-31", "PublicationDate": "2026-10-20", "PublicationDateStatus": "VERIFIED"},
    ])
    out = apply_official_publication_dates(records, "2026-10-22", filings=filings,
        cache_path=tmp_path/"cache.csv", diagnostics_path=tmp_path/"diag.csv")
    assert set(out["PublicationDateStatus"].astype(str)) == {"UNVERIFIED"}
    assert len(out) == 2


def test_symbol_mismatch_does_not_verify_and_rows_are_retained(tmp_path):
    records = pd.DataFrame([{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30"}, {"TckrSymb": "XYZ", "FinancialPeriodEnd": "2026-06-30"}])
    filings = pd.DataFrame([{"TckrSymb": "ABCX", "FinancialPeriodEnd": "2026-06-30", "PublicationDate": "2026-07-25", "PublicationDateStatus": "VERIFIED"}])
    out = apply_official_publication_dates(records, "2026-10-22", filings=filings,
        cache_path=tmp_path/"cache.csv", diagnostics_path=tmp_path/"diag.csv")
    assert len(out) == 2
    assert all(out["PublicationDateStatus"].astype(str) == "UNVERIFIED")


def test_missing_period_does_not_use_asof_date_as_period(tmp_path):
    records = pd.DataFrame([{"TckrSymb": "ABC", "AsOfDate": "2026-10-22"}])
    filings = pd.DataFrame([{"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-10-22", "PublicationDate": "2026-10-20", "PublicationDateStatus": "VERIFIED"}])
    out = apply_official_publication_dates(records, "2026-10-22", filings=filings,
        cache_path=tmp_path/"cache.csv", diagnostics_path=tmp_path/"diag.csv")
    assert out.loc[0, "PublicationDateStatus"] == "UNVERIFIED"
