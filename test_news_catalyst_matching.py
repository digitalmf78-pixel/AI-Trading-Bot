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
