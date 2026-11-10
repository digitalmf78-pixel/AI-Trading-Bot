import pandas as pd
import pytest

from signal_cohort_assembly import CohortAssemblyError, assemble_mainboard_cohort


def test_preserves_entire_mainboard_cohort_when_downstream_reports_omit_rows():
    main = pd.DataFrame({"TckrSymb": ["AAA", "BBB", "CCC"], "SctySrs": ["EQ"] * 3, "ClsPric": [10, 20, 30]})
    delivery = pd.DataFrame({"TckrSymb": ["AAA", "CCC"], "DeliveryFilterStatus": ["PASS", "WAIT_FOR_DATA"]})
    result = assemble_mainboard_cohort(main, reports={"Delivery": delivery})
    assert result.cohort["TckrSymb"].tolist() == ["AAA", "BBB", "CCC"]
    assert result.cohort["Delivery__DeliveryFilterStatus"].tolist()[:1] == ["PASS"]
    missing = result.cohort.loc[result.cohort["TckrSymb"] == "BBB"].iloc[0]
    assert missing["Delivery__CoverageStatus"] == "NOT_EVALUATED"
    assert missing["Delivery__CoverageReason"] == "MISSING_SOURCE_ROW"
    assert pd.isna(missing["Delivery__DeliveryFilterStatus"])


def test_missing_and_empty_reports_are_not_evaluated():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    result = assemble_mainboard_cohort(main, reports={"Absent": None, "Empty": pd.DataFrame(columns=["TckrSymb"])})
    row = result.cohort.iloc[0]
    assert row["Absent__CoverageStatus"] == "NOT_EVALUATED"
    assert row["Absent__CoverageReason"] == "SOURCE_REPORT_NOT_SUPPLIED"
    assert row["Empty__CoverageStatus"] == "NOT_EVALUATED"
    assert row["Empty__CoverageReason"] == "SOURCE_REPORT_EMPTY"


def test_duplicate_mainboard_symbols_fail_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA", "aaa"]})
    with pytest.raises(CohortAssemblyError, match="duplicate symbol"):
        assemble_mainboard_cohort(main)


def test_duplicate_report_symbols_fail_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    report = pd.DataFrame({"TckrSymb": ["AAA", "aaa"], "Status": ["PASS", "FAIL"]})
    with pytest.raises(CohortAssemblyError, match="duplicate symbol"):
        assemble_mainboard_cohort(main, reports={"Delivery": report})


def test_symbol_normalization_and_native_status_preservation():
    main = pd.DataFrame({"TckrSymb": [" aaa "]})
    report = pd.DataFrame({"TckrSymb": ["AAA"], "WatchlistStatus": ["ACCUMULATION_WATCH"], "WatchlistReason": ["RAW_REASON"]})
    result = assemble_mainboard_cohort(main, reports={"Accumulation": report})
    row = result.cohort.iloc[0]
    assert row["Accumulation__WatchlistStatus"] == "ACCUMULATION_WATCH"
    assert row["Accumulation__WatchlistReason"] == "RAW_REASON"
    assert row["Accumulation__CoverageStatus"] == "SOURCE_ROW_PRESENT"


def test_news_one_to_many_rows_do_not_duplicate_cohort_rows():
    main = pd.DataFrame({"TckrSymb": ["AAA", "BBB"]})
    news = pd.DataFrame({"TckrSymb": ["AAA", "AAA", "ZZZ"], "Headline": ["h1", "h2", "h3"], "EventID": ["1", "2", "3"]})
    result = assemble_mainboard_cohort(main, news_report=news)
    assert len(result.cohort) == 2
    assert len(result.news_evidence) == 3
    assert result.news_evidence["NewsEvidenceCoverageStatus"].tolist() == ["SOURCE_ROW_PRESENT", "SOURCE_ROW_PRESENT", "OUT_OF_COHORT"]


def test_out_of_cohort_stage_rows_are_diagnostic_not_added_to_universe():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    report = pd.DataFrame({"TckrSymb": ["AAA", "ZZZ"], "Status": ["PASS", "PASS"]})
    result = assemble_mainboard_cohort(main, reports={"Stage": report})
    assert result.cohort["TckrSymb"].tolist() == ["AAA"]
    diagnostic = result.diagnostics[result.diagnostics["Stage"] == "Stage"].iloc[0]
    assert diagnostic["OutOfCohortRows"] == 1


def test_non_symbol_report_rejected():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    with pytest.raises(CohortAssemblyError, match="TckrSymb"):
        assemble_mainboard_cohort(main, reports={"Stage": pd.DataFrame({"Symbol": ["AAA"]})})



def test_corporate_events_one_to_many_rows_are_preserved_separately():
    main = pd.DataFrame({"TckrSymb": ["AAA", "BBB"]})
    events = pd.DataFrame({
        "TckrSymb": ["AAA", "AAA", "ZZZ"],
        "EventType": ["Board Meeting", "Results", "AGM"],
        "EventDate": ["2026-11-12", "2026-11-15", "2026-11-20"],
    })
    result = assemble_mainboard_cohort(main, corporate_events_report=events)
    assert len(result.cohort) == 2
    assert len(result.corporate_event_evidence) == 3
    assert result.corporate_event_evidence["CorporateEventEvidenceCoverageStatus"].tolist() == [
        "SOURCE_ROW_PRESENT", "SOURCE_ROW_PRESENT", "OUT_OF_COHORT"
    ]


def test_news_and_event_evidence_can_both_be_empty_or_missing():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    result = assemble_mainboard_cohort(main, news_report=None, corporate_events_report=pd.DataFrame())
    assert list(result.news_evidence.columns) == ["TckrSymb", "NewsEvidenceCoverageStatus"]
    assert "CorporateEventEvidenceCoverageStatus" in result.corporate_event_evidence.columns


def test_series_mismatch_for_same_symbol_fails_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["EQ"]})
    report = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["BE"], "Status": ["PASS"]})
    with pytest.raises(CohortAssemblyError, match="SctySrs mismatch"):
        assemble_mainboard_cohort(main, reports={"Stage": report})


def test_internal_join_keys_are_not_exposed_in_output():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["EQ"]})
    report = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["EQ"], "Status": ["PASS"]})
    result = assemble_mainboard_cohort(main, reports={"Stage": report})
    assert "_cohort_symbol_key" not in result.cohort.columns
    assert "_cohort_series_key" not in result.cohort.columns
    assert "Stage___cohort_series_key" not in result.cohort.columns
    assert result.cohort.loc[0, "Stage__SctySrs"] == "EQ"
