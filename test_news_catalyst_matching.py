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
            "DeliveryCategoryAStatus": "PASS_ROLLING_5D_AVG_GE_60_AT_LEAST_5",
            "DeliveryCategoryBStatus": "FILTERED_OUT_DAILY_DELIVERY_LT_5",
        },
        {
            "TckrSymb": "A_AND_B",
            "DeliveryCategoryAStatus": "PASS_ROLLING_5D_AVG_GE_60_AT_LEAST_5",
            "DeliveryCategoryBStatus": "PASS_DAILY_DELIVERY_GE_60_AT_LEAST_5",
        },
        {
            "TckrSymb": "REJECT",
            "DeliveryCategoryAStatus": "FILTERED_OUT_ROLLING_5D_AVG_LT_5",
            "DeliveryCategoryBStatus": "FILTERED_OUT_DAILY_DELIVERY_LT_5",
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


def test_telegram_liquidity_digest_counts_all_tiers_without_forced_fill():
    import pandas as pd

    report = pd.DataFrame([
        {"TckrSymb": "WEAK_STOCK", "LiquidityFilterStatus": "PASS", "LiquidityTier": "LOW",
         "AvgDailyTradedValue20D": 17_000_000},
        {"TckrSymb": "MEDIUM_STOCK", "LiquidityFilterStatus": "PASS", "LiquidityTier": "MEDIUM",
         "AvgDailyTradedValue20D": 30_000_000},
        {"TckrSymb": "STRONG_STOCK", "LiquidityFilterStatus": "PASS", "LiquidityTier": "STRONG",
         "AvgDailyTradedValue20D": 80_000_000},
    ])

    message = "\\n".join(news._observation_digest_lines(report, result=None, news_data=None))
    assert "STRONG: 1" in message
    assert "MEDIUM: 1" in message
    assert "WEAK: 1" in message
    assert "ranked stock उपलब्ध नाही" in message
    assert "STRONG_STOCK" in message

def test_telegram_top4_is_ranked_independently_for_each_liquidity_tier():
    import pandas as pd

    rows = []
    for tier in ("STRONG", "MEDIUM", "LOW"):
        for rank in range(1, 7):
            rows.append({
                "TckrSymb": f"{tier}_{rank}",
                "LiquidityTier": tier,
                "FundamentalScore": 100 - rank,
                "RelativeStrengthNifty": 10 - rank,
                "SectorStrengthNifty": 8 - rank,
                "RVOL": 3.0 - (rank / 10),
                "RiskReward": 3.0 - (rank / 10),
                "EMA44": 100.0,
                "TrendClassification": "Bullish (Close > EMA44)",
                "CoreTechnicalScreenStatus": "PASS",
                "RiskRewardStatus": "PASS",
                "NewsEvidenceStatus": "PRIMARY_CONFIRMED",
                "NewsPrimarySourceVerified": True,
                "SetupType": "Breakout",
            })
    selected = news._top_ranked_observations_by_tier(pd.DataFrame(rows), limit_per_tier=4)
    assert len(selected) == 12
    counts = selected["LiquidityTier"].value_counts().to_dict()
    assert counts == {"STRONG": 4, "MEDIUM": 4, "LOW": 4}
    for tier in ("STRONG", "MEDIUM", "LOW"):
        group = selected[selected["LiquidityTier"] == tier]
        assert group["TckrSymb"].tolist() == [f"{tier}_{i}" for i in range(1, 5)]
        assert group["_TierRank"].tolist() == [1, 2, 3, 4]


def test_telegram_top4_does_not_force_fill_or_rank_wait_for_data():
    import pandas as pd

    rows = []
    for tier in ("STRONG", "MEDIUM", "LOW"):
        rows.append({
            "TckrSymb": tier + "_PASS", "LiquidityTier": tier,
            "FundamentalScore": 80, "RelativeStrengthNifty": 5,
            "SectorStrengthNifty": 3, "RVOL": 2, "RiskReward": 2.5,
            "EMA44": 100, "TrendClassification": "Bullish (Close > EMA44)",
            "CoreTechnicalScreenStatus": "PASS", "RiskRewardStatus": "PASS",
            "NewsEvidenceStatus": "PRIMARY_CONFIRMED", "NewsPrimarySourceVerified": True,
            "SetupType": "Pullback",
        })
        rows.append({
            "TckrSymb": tier + "_WAIT", "LiquidityTier": tier,
            "FundamentalScore": 99, "RelativeStrengthNifty": 9,
            "SectorStrengthNifty": 9, "RVOL": 9, "RiskReward": 4,
            "EMA44": 100, "TrendClassification": "WAIT_FOR_DATA",
            "CoreTechnicalScreenStatus": "WAIT_FOR_DATA", "RiskRewardStatus": "WAIT_FOR_DATA",
            "NewsEvidenceStatus": "NO_DATA", "NewsPrimarySourceVerified": False,
            "SetupType": "Breakout",
        })
    selected = news._top_ranked_observations_by_tier(pd.DataFrame(rows), limit_per_tier=4)
    assert selected["TckrSymb"].tolist() == ["STRONG_PASS", "MEDIUM_PASS", "LOW_PASS"]
    assert len(selected) == 3

