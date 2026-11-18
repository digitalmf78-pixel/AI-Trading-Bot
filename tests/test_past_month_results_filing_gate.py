import pandas as pd

import fundamental_official_filings
from nse_results_verification import apply_past_month_results_filing_gate


def _audit(symbol, event_date, details):
    return pd.DataFrame([{
        "TckrSymb": symbol,
        "ResultsUniverseStatus": "PASS_ANNOUNCED_WITHIN_3M_REQUIRES_PAST_MONTH_FILING_CHECK",
        "OfficialResultsDate": event_date,
        "ResultsPurpose": "Financial Results",
        "ResultsDetails": details,
    }])


def test_previous_month_candidate_requires_exact_verified_period(tmp_path, monkeypatch):
    candidates = pd.DataFrame({"TckrSymb": ["AAA"]})
    audit = _audit("AAA", "2026-10-20", "Quarter ended 30-Sep-2026")
    monkeypatch.setattr(
        fundamental_official_filings,
        "fetch_nse_financial_results",
        lambda asof_date, lookback_days: pd.DataFrame([{
            "TckrSymb": "AAA",
            "FinancialPeriodEnd": "2026-09-30",
            "PublicationDate": "2026-10-20",
            "PublicationDateStatus": "VERIFIED",
            "OfficialFilingURL": "https://www.nseindia.com/example",
        }]),
    )
    gated, result_audit = apply_past_month_results_filing_gate(
        candidates, audit, pd.Timestamp("2026-11-17").date(),
        filings_path=tmp_path / "filings.csv",
    )
    assert gated["TckrSymb"].tolist() == ["AAA"]
    assert result_audit.iloc[0]["ResultsFilingGateStatus"] == "PASS_EXACT_PERIOD_NSE_FILING_VERIFIED"


def test_previous_month_candidate_without_exact_period_is_wait_for_data(tmp_path, monkeypatch):
    candidates = pd.DataFrame({"TckrSymb": ["AAA"]})
    audit = _audit("AAA", "2026-10-20", "Financial Results")
    monkeypatch.setattr(
        fundamental_official_filings,
        "fetch_nse_financial_results",
        lambda asof_date, lookback_days: pd.DataFrame([{
            "TckrSymb": "AAA",
            "FinancialPeriodEnd": "2026-09-30",
            "PublicationDate": "2026-10-20",
            "PublicationDateStatus": "VERIFIED",
        }]),
    )
    gated, result_audit = apply_past_month_results_filing_gate(
        candidates, audit, pd.Timestamp("2026-11-17").date(),
        filings_path=tmp_path / "filings.csv",
    )
    assert gated.empty
    assert result_audit.iloc[0]["ResultsFilingGateStatus"] == "WAIT_FOR_DATA_EVENT_PERIOD_NOT_EXPLICIT"


def test_filing_refresh_failure_does_not_use_stale_snapshot(tmp_path, monkeypatch):
    candidates = pd.DataFrame({"TckrSymb": ["AAA"]})
    audit = _audit("AAA", "2026-10-20", "Quarter ended 30-Sep-2026")
    stale = pd.DataFrame([{
        "TckrSymb": "AAA", "FinancialPeriodEnd": "2026-09-30",
        "PublicationDate": "2026-10-20", "PublicationDateStatus": "VERIFIED",
    }])
    stale.to_csv(tmp_path / "filings.csv", index=False)
    monkeypatch.setattr(
        fundamental_official_filings,
        "fetch_nse_financial_results",
        lambda asof_date, lookback_days: (_ for _ in ()).throw(RuntimeError("NSE unavailable")),
    )
    gated, result_audit = apply_past_month_results_filing_gate(
        candidates, audit, pd.Timestamp("2026-11-17").date(),
        filings_path=tmp_path / "filings.csv",
    )
    assert gated.empty
    assert result_audit.iloc[0]["ResultsFilingGateStatus"] == "WAIT_FOR_DATA_FILING_REFRESH_FAILED"


def test_upcoming_results_candidate_does_not_require_prior_filing(tmp_path, monkeypatch):
    candidates = pd.DataFrame({"TckrSymb": ["AAA"]})
    audit = _audit("AAA", "2026-11-25", "Financial Results")
    monkeypatch.setattr(
        fundamental_official_filings,
        "fetch_nse_financial_results",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("refresh should not run")),
    )
    gated, result_audit = apply_past_month_results_filing_gate(
        candidates, audit, pd.Timestamp("2026-11-17").date(),
        filings_path=tmp_path / "filings.csv",
    )
    assert gated["TckrSymb"].tolist() == ["AAA"]
    assert result_audit.iloc[0]["ResultsFilingGateStatus"] == "NOT_REQUIRED_UPCOMING_EVENT"
