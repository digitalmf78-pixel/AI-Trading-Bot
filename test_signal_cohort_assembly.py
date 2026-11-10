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


def test_missing_report_series_is_explicitly_diagnosed_without_rejecting_symbol_join():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["EQ"]})
    report = pd.DataFrame({"TckrSymb": ["AAA"], "Status": ["PASS"]})
    result = assemble_mainboard_cohort(main, reports={"Stage": report})
    diagnostic = result.diagnostics[result.diagnostics["Stage"] == "Stage"].iloc[0]
    assert diagnostic["SeriesAlignmentStatus"] == "NOT_CHECKED_SERIES_MISSING_IN_REPORT"
    assert result.cohort.loc[0, "Stage__CoverageStatus"] == "SOURCE_ROW_PRESENT"


def test_duplicate_column_names_fail_closed():
    main = pd.DataFrame([["AAA", "EQ"]], columns=["TckrSymb", "TckrSymb"])
    with pytest.raises(CohortAssemblyError, match="duplicate column names"):
        assemble_mainboard_cohort(main)


def test_stage_names_are_validated_and_normalized_collisions_rejected():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    with pytest.raises(CohortAssemblyError, match="Invalid stage name"):
        assemble_mainboard_cohort(main, reports={"Bad Stage": pd.DataFrame({"TckrSymb": ["AAA"]})})
    with pytest.raises(CohortAssemblyError, match="Duplicate stage name"):
        assemble_mainboard_cohort(main, reports={"Delivery": None, " Delivery ": None})


def test_one_to_many_evidence_series_mismatch_fails_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["EQ"]})
    news = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["BE"], "Headline": ["h"]})
    with pytest.raises(CohortAssemblyError, match="SctySrs mismatch for evidence rows"):
        assemble_mainboard_cohort(main, news_report=news)


def test_one_to_many_evidence_missing_series_is_diagnosed_not_rejected():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["EQ"]})
    events = pd.DataFrame({"TckrSymb": ["AAA"], "EventType": ["Results"]})
    result = assemble_mainboard_cohort(main, corporate_events_report=events)
    diagnostic = result.diagnostics[
        result.diagnostics["Diagnostic"] == "SERIES_ALIGNMENT_NOT_CHECKED_SERIES_MISSING_IN_REPORT"
    ]
    assert len(diagnostic) == 1
    assert result.corporate_event_evidence.loc[0, "CorporateEventEvidenceCoverageStatus"] == "SOURCE_ROW_PRESENT"


def test_one_to_many_evidence_duplicate_columns_fail_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    news = pd.DataFrame([["AAA", "x", "y"]], columns=["TckrSymb", "Headline", "Headline"])
    with pytest.raises(CohortAssemblyError, match="duplicate column names"):
        assemble_mainboard_cohort(main, news_report=news)


def test_reserved_internal_source_columns_fail_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "_cohort_symbol_key": ["spoofed"]})
    with pytest.raises(CohortAssemblyError, match="reserved internal columns"):
        assemble_mainboard_cohort(main)


def test_generated_base_field_collision_fails_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "CohortIdentityKey": ["source-value"]})
    with pytest.raises(CohortAssemblyError, match="collide with generated fields"):
        assemble_mainboard_cohort(main)


def test_generated_stage_field_collision_fails_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "Delivery__Status": ["source-value"]})
    report = pd.DataFrame({"TckrSymb": ["AAA"], "Status": ["PASS"]})
    with pytest.raises(CohortAssemblyError, match="generated output columns collide"):
        assemble_mainboard_cohort(main, reports={"Delivery": report})


def test_evidence_coverage_column_collision_fails_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    news = pd.DataFrame({
        "TckrSymb": ["AAA"],
        "NewsEvidenceCoverageStatus": ["spoofed"],
    })
    with pytest.raises(CohortAssemblyError, match="reserved coverage column"):
        assemble_mainboard_cohort(main, news_report=news)


def test_generated_stage_coverage_columns_cannot_overwrite_base_data():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "Delivery__CoverageStatus": ["source-value"]})
    report = pd.DataFrame({"TckrSymb": ["AAA"], "Status": ["PASS"]})
    with pytest.raises(CohortAssemblyError, match="generated output columns collide"):
        assemble_mainboard_cohort(main, reports={"Delivery": report})


@pytest.mark.parametrize("reserved_field", ["CoverageStatus", "CoverageReason"])
def test_stage_payload_cannot_shadow_generated_coverage_fields(reserved_field):
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    report = pd.DataFrame({"TckrSymb": ["AAA"], reserved_field: ["spoofed"]})
    with pytest.raises(CohortAssemblyError, match="reserved coverage field names"):
        assemble_mainboard_cohort(main, reports={"Stage": report})


def test_missing_stage_report_cannot_overwrite_existing_coverage_columns():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "Stage__CoverageStatus": ["source-value"]})
    with pytest.raises(CohortAssemblyError, match="generated output columns collide"):
        assemble_mainboard_cohort(main, reports={"Stage": None})


def test_empty_stage_report_cannot_overwrite_existing_coverage_columns():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "Stage__CoverageStatus": ["source-value"]})
    empty = pd.DataFrame(columns=["TckrSymb"])
    with pytest.raises(CohortAssemblyError, match="generated output columns collide"):
        assemble_mainboard_cohort(main, reports={"Stage": empty})


def test_empty_evidence_report_duplicate_columns_fail_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    news = pd.DataFrame(columns=["TckrSymb", "Headline", "Headline"])
    with pytest.raises(CohortAssemblyError, match="duplicate column names"):
        assemble_mainboard_cohort(main, news_report=news)


def test_empty_evidence_report_reserved_coverage_column_fails_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    news = pd.DataFrame(columns=["TckrSymb", "NewsEvidenceCoverageStatus"])
    with pytest.raises(CohortAssemblyError, match="reserved coverage column"):
        assemble_mainboard_cohort(main, news_report=news)


def test_empty_evidence_report_reserved_internal_keys_fail_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    news = pd.DataFrame(columns=["TckrSymb", "_cohort_symbol_key"])
    with pytest.raises(CohortAssemblyError, match="reserved internal cohort columns"):
        assemble_mainboard_cohort(main, news_report=news)


def test_empty_stage_report_duplicate_columns_fail_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    empty = pd.DataFrame(columns=["TckrSymb", "Status", "Status"])
    with pytest.raises(CohortAssemblyError, match="duplicate column names"):
        assemble_mainboard_cohort(main, reports={"Stage": empty})


def test_empty_stage_report_reserved_internal_columns_fail_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"]})
    empty = pd.DataFrame(columns=["TckrSymb", "_cohort_series_key"])
    with pytest.raises(CohortAssemblyError, match="reserved internal columns"):
        assemble_mainboard_cohort(main, reports={"Stage": empty})



def test_empty_mainboard_cohort_returns_empty_schema_without_losing_columns():
    main = pd.DataFrame({"TckrSymb": pd.Series(dtype="object"), "SctySrs": pd.Series(dtype="object")})
    result = assemble_mainboard_cohort(main, reports={"Delivery": None})
    assert result.cohort.empty
    assert "CohortIdentityKey" in result.cohort.columns
    assert result.cohort["Delivery__CoverageStatus"].empty
    assert result.cohort["DownstreamReportsExpected"].iloc[0:0].empty


@pytest.mark.parametrize("bad_symbol", [[ "AAA", "BBB" ], {"symbol": "AAA"}])
def test_non_scalar_symbol_identity_fails_closed(bad_symbol):
    main = pd.DataFrame({"TckrSymb": [bad_symbol]})
    with pytest.raises(CohortAssemblyError, match="scalar"):
        assemble_mainboard_cohort(main)


def test_non_scalar_series_identity_fails_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": [["EQ", "BE"]]})
    with pytest.raises(CohortAssemblyError, match="SctySrs key must be a scalar"):
        assemble_mainboard_cohort(main)


def test_non_scalar_news_series_identity_fails_closed():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["EQ"]})
    news = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": [["EQ", "BE"]]})
    with pytest.raises(CohortAssemblyError, match="SctySrs key must be a scalar"):
        assemble_mainboard_cohort(main, news_report=news)

def test_out_of_cohort_news_with_series_is_preserved_as_out_of_cohort():
    main = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["EQ"]})
    news = pd.DataFrame({
        "TckrSymb": ["OUTSIDE"],
        "SctySrs": ["EQ"],
        "Headline": ["Unmatched evidence row"],
    })
    result = assemble_mainboard_cohort(main, news_report=news)
    assert len(result.news_evidence) == 1
    assert result.news_evidence.loc[0, "NewsEvidenceCoverageStatus"] == "OUT_OF_COHORT"


def test_full_2588_symbol_mainboard_cohort_is_not_reduced_to_delivery_union():
    symbols = [f"STK{i:04d}" for i in range(2588)]
    main = pd.DataFrame({
        "TckrSymb": symbols,
        "SctySrs": ["EQ"] * 2385 + ["BE"] * 203,
        "MainBoardStatus": ["PASS_MAIN_BOARD"] * 2588,
    })
    # The 758-row delivery union is a downstream report, not the base cohort.
    delivery_symbols = symbols[:758]
    delivery = pd.DataFrame({
        "TckrSymb": delivery_symbols,
        "DeliveryFilterStatus": ["PASS_A_OR_B"] * 758,
        "DeliveryCategoryAStatus": ["PASS"] * 758,
        "DeliveryCategoryBStatus": ["PASS"] * 102 + ["NOT_PASS"] * 656,
    })
    result = assemble_mainboard_cohort(main, reports={"Delivery": delivery})
    assert len(result.cohort) == 2588
    assert result.cohort["TckrSymb"].tolist() == symbols
    assert result.cohort["CohortEligibilityStatus"].eq("PASS_MAIN_BOARD_INPUT").all()
    assert result.cohort["Delivery__CoverageStatus"].eq("SOURCE_ROW_PRESENT").sum() == 758
    assert result.cohort["Delivery__CoverageStatus"].eq("NOT_EVALUATED").sum() == 1830
    assert result.cohort["Delivery__DeliveryFilterStatus"].notna().sum() == 758


def test_native_wait_and_reject_statuses_are_preserved_without_gate_interpretation():
    main = pd.DataFrame({"TckrSymb": ["AAA", "BBB", "CCC"]})
    report = pd.DataFrame({
        "TckrSymb": ["AAA", "BBB"],
        "Status": ["WAIT_FOR_DATA", "FILTERED_OUT_AVG_LT_60_PERCENT"],
    })
    result = assemble_mainboard_cohort(main, reports={"Delivery": report})
    assert result.cohort["TckrSymb"].tolist() == ["AAA", "BBB", "CCC"]
    assert result.cohort["Delivery__Status"].tolist()[:2] == [
        "WAIT_FOR_DATA", "FILTERED_OUT_AVG_LT_60_PERCENT"
    ]
    assert result.cohort.loc[2, "Delivery__CoverageStatus"] == "NOT_EVALUATED"


def test_one_to_many_news_and_event_rows_do_not_inflate_stage_coverage_counts():
    main = pd.DataFrame({"TckrSymb": ["AAA", "BBB"]})
    stage = pd.DataFrame({"TckrSymb": ["AAA"], "Status": ["PASS"]})
    news = pd.DataFrame({"TckrSymb": ["AAA", "AAA", "BBB"], "Headline": ["n1", "n2", "n3"]})
    events = pd.DataFrame({"TckrSymb": ["AAA", "AAA"], "EventType": ["AGM", "Results"]})
    result = assemble_mainboard_cohort(
        main, reports={"StageA": stage}, news_report=news, corporate_events_report=events
    )
    assert result.cohort["DownstreamReportsExpected"].tolist() == [1, 1]
    assert result.cohort["DownstreamReportsPresent"].tolist() == [1, 0]
    assert len(result.news_evidence) == 3
    assert len(result.corporate_event_evidence) == 2


def test_assembly_does_not_mutate_any_input_frame():
    main = pd.DataFrame({"TckrSymb": ["AAA", "BBB"], "SctySrs": ["EQ", "BE"]})
    stage = pd.DataFrame({"TckrSymb": ["AAA"], "SctySrs": ["EQ"], "Status": ["PASS"]})
    news = pd.DataFrame({"TckrSymb": ["AAA", "AAA"], "Headline": ["h1", "h2"]})
    before = [frame.copy(deep=True) for frame in (main, stage, news)]
    assemble_mainboard_cohort(main, reports={"Stage": stage}, news_report=news)
    pd.testing.assert_frame_equal(main, before[0])
    pd.testing.assert_frame_equal(stage, before[1])
    pd.testing.assert_frame_equal(news, before[2])
