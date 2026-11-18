from datetime import date

import pandas as pd

from nse_results_verification import build_results_verification_report


def test_prior_filing_is_flagged_for_period_confirmation_not_auto_excluded():
    audit = pd.DataFrame([{
        "TckrSymb": "LATTEYS",
        "ResultsUniverseStatus": "PASS_ANNOUNCED_WITHIN_3M",
        "OfficialResultsDate": "2026-12-05",
        "ResultsPurpose": "Financial Results",
        "ResultsDetails": "Board meeting to consider quarterly results",
        "ResultsSourceURL": "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar",
    }])
    filings = pd.DataFrame([{
        "TckrSymb": "LATTEYS", "FinancialPeriodEnd": "2026-09-30",
        "PublicationDate": "2026-11-05", "PublicationDateStatus": "VERIFIED",
        "OfficialFilingURL": "https://nsearchives.nseindia.com/example.xml",
    }])
    out = build_results_verification_report(audit, filings, date(2026, 11, 17))
    assert out.loc[0, "FilingVerificationStatus"] == "PRIOR_FILING_REQUIRES_PERIOD_CONFIRMATION"
    assert out.loc[0, "LatestPriorFilingDate"] == "2026-11-05"
    assert out.loc[0, "MeetingStatus"] == "SCHEDULED_AS_PER_NSE_CALENDAR"


def test_explicit_period_match_is_marked_filed_for_that_period():
    audit = pd.DataFrame([{
        "TckrSymb": "ABC", "ResultsUniverseStatus": "PASS",
        "OfficialResultsDate": "2026-11-20",
        "ResultsPurpose": "Financial Results for quarter ended 30th September, 2026",
        "ResultsDetails": "",
    }])
    filings = pd.DataFrame([{
        "TckrSymb": "ABC", "FinancialPeriodEnd": "2026-09-30",
        "PublicationDate": "2026-11-10", "PublicationDateStatus": "VERIFIED",
    }])
    out = build_results_verification_report(audit, filings, date(2026, 11, 17))
    assert out.loc[0, "ExpectedFinancialPeriodEnd"] == "2026-09-30"
    assert out.loc[0, "FilingVerificationStatus"] == "RESULTS_FILED_FOR_EXPLICIT_EVENT_PERIOD"


def test_unverified_or_future_publication_is_not_used_as_prior_filing():
    audit = pd.DataFrame([{
        "TckrSymb": "ABC", "ResultsUniverseStatus": "PASS",
        "OfficialResultsDate": "2026-11-25", "ResultsPurpose": "Financial Results",
    }])
    filings = pd.DataFrame([
        {"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-09-30",
         "PublicationDate": "2026-11-18", "PublicationDateStatus": "VERIFIED"},
        {"TckrSymb": "ABC", "FinancialPeriodEnd": "2026-06-30",
         "PublicationDate": "2026-10-25", "PublicationDateStatus": "UNVERIFIED"},
    ])
    out = build_results_verification_report(audit, filings, date(2026, 11, 17))
    assert out.loc[0, "FilingVerificationStatus"] == "NO_PRIOR_FILING_FOUND_IN_AVAILABLE_SNAPSHOT"


def test_missing_filing_snapshot_fails_to_wait_for_data():
    audit = pd.DataFrame([{
        "TckrSymb": "ABC", "ResultsUniverseStatus": "PASS",
        "OfficialResultsDate": "2026-11-25", "ResultsPurpose": "Financial Results",
    }])
    out = build_results_verification_report(audit, pd.DataFrame(), date(2026, 11, 17))
    assert out.loc[0, "FilingVerificationStatus"] == "WAIT_FOR_DATA_NO_VALID_FILING_SNAPSHOT"


def test_cancelled_and_postponed_text_is_retained_as_status_evidence():
    audit = pd.DataFrame([
        {"TckrSymb": "A", "ResultsUniverseStatus": "PASS", "OfficialResultsDate": "2026-11-25",
         "ResultsPurpose": "Financial Results", "ResultsDetails": "Meeting postponed"},
        {"TckrSymb": "B", "ResultsUniverseStatus": "PASS", "OfficialResultsDate": "2026-11-26",
         "ResultsPurpose": "Financial Results", "ResultsDetails": "Meeting rescheduled"},
    ])
    filings = pd.DataFrame([{
        "TckrSymb": "A", "FinancialPeriodEnd": "2026-06-30",
        "PublicationDate": "2026-08-10", "PublicationDateStatus": "VERIFIED",
    }])
    out = build_results_verification_report(audit, filings, date(2026, 11, 17))
    assert out.loc[out.TckrSymb.eq("A"), "MeetingStatus"].iloc[0] == "POSTPONED_REVIEW"
    assert out.loc[out.TckrSymb.eq("B"), "MeetingStatus"].iloc[0] == "RESCHEDULED_REVIEW"
