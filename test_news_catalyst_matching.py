import news_catalyst as news


def test_akash_personal_name_does_not_match_issuer():
    assert news._issuer_match_reason(
        "AKASH",
        "After return to BSP, Akash Anand set to resume electoral campaign in UP",
        "AKASH INFRA-PROJECTS LIMITED",
    ) == ""


def test_akash_infra_projects_company_name_matches():
    assert news._issuer_match_reason(
        "AKASH",
        "Akash Infra-Projects Ltd announces quarterly results",
        "AKASH INFRA-PROJECTS LIMITED",
    ) == "COMPANY_NAME_MATCH"


def test_efc_issuer_name_matches_with_legal_suffix_variation():
    assert news._issuer_match_reason(
        "EFCIL",
        "EFC (I) Ltd. (EFCIL) Reg 74(5) Certificate Q2 FY27",
        "EFC (I) LIMITED",
    ) in {"COMPANY_NAME_MATCH", "EXPLICIT_TICKER_MATCH"}


def test_explicit_nse_ticker_is_accepted():
    assert news._issuer_match_reason(
        "AKASH", "AKASH (NSE: AKASH) share price update", ""
    ) == "EXPLICIT_TICKER_MATCH"


def test_unrelated_akash_mentions_are_rejected():
    headlines = [
        "Tonbo Imaging IPO: Akash Bhansali among investors buying shares",
        "Bharat Dynamics: Akash missile ramp and board update",
        "Jio strategy: Akash Ambani discusses new technology",
    ]
    for headline in headlines:
        assert news._issuer_match_reason(
            "AKASH", headline, "AKASH INFRA-PROJECTS LIMITED"
        ) == "", headline


def test_secondary_searches_do_not_require_name_and_ticker_together():
    queries = news._secondary_search_queries(
        "SINGERIND", "Singer India Limited"
    )
    assert queries == [
        '"Singer India Limited" when:10d',
        '"SINGERIND" NSE stock when:10d',
    ]


def test_secondary_description_can_confirm_registered_issuer_name():
    # The query is discovery only; the company name still has to match explicitly.
    assert news._issuer_match_reason(
        "SINGERIND",
        "Business update | Singer India Limited announced a board meeting",
        "Singer India Limited",
    ) == "COMPANY_NAME_MATCH"


def test_secondary_search_query_for_unmapped_etf_does_not_invent_company_name():
    assert news._secondary_search_queries("TECH", "") == [
        '"TECH" NSE stock when:10d'
    ]



def test_news_delivery_gate_keeps_category_a_only_and_a_and_b_union():
    import pandas as pd

    candidates = pd.DataFrame([
        {
            "TckrSymb": "A_ONLY",
            "DeliveryCategoryAStatus": "PASS_AVG_GE_60_PERCENT",
            "DeliveryCategoryBStatus": "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT",
        },
        {
            "TckrSymb": "A_AND_B",
            "DeliveryCategoryAStatus": "PASS_AVG_GE_60_PERCENT",
            "DeliveryCategoryBStatus": "PASS_EACH_DAY_GE_60_PERCENT",
        },
        {
            "TckrSymb": "REJECT",
            "DeliveryCategoryAStatus": "FILTERED_OUT_AVG_LT_60_PERCENT",
            "DeliveryCategoryBStatus": "FILTERED_OUT_AT_LEAST_ONE_DAY_LT_60_PERCENT",
        },
    ])

    selected = news._filter_catalyst_candidates(candidates)
    assert selected["TckrSymb"].tolist() == ["A_ONLY", "A_AND_B"]


def test_news_delivery_gate_uses_union_delivery_status_when_category_columns_absent():
    import pandas as pd

    candidates = pd.DataFrame({
        "TckrSymb": ["A_OR_B", "REJECT"],
        "DeliveryFilterStatus": ["PASS_GE_60_PERCENT", "FILTERED_OUT_BELOW_60_PERCENT"],
    })
    selected = news._filter_catalyst_candidates(candidates)
    assert selected["TckrSymb"].tolist() == ["A_OR_B"]


def test_telegram_liquidity_digest_groups_strong_medium_then_weak():
    import pandas as pd

    report = pd.DataFrame([
        {"TckrSymb": "WEAK_STOCK", "LiquidityFilterStatus": "PASS", "LiquidityTier": "LOW",
         "AvgDailyTradedValue20D": 17_000_000},
        {"TckrSymb": "MEDIUM_STOCK", "LiquidityFilterStatus": "PASS", "LiquidityTier": "MEDIUM",
         "AvgDailyTradedValue20D": 30_000_000},
        {"TckrSymb": "STRONG_STOCK", "LiquidityFilterStatus": "PASS", "LiquidityTier": "STRONG",
         "AvgDailyTradedValue20D": 80_000_000},
    ])

    lines = news._observation_digest_lines(report, result=None, news_data=None)
    message = "\\n".join(lines)
    assert message.index("STRONG LIQUIDITY") < message.index("MEDIUM LIQUIDITY") < message.index("WEAK LIQUIDITY")
    assert message.index("STRONG_STOCK") < message.index("MEDIUM_STOCK") < message.index("WEAK_STOCK")
    assert "WEAK: 1" in message
