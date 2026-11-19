"""ECMS-only selection of provider-aligned consolidated audited NSE filings."""
from __future__ import annotations
import pandas as pd

STATUS_COLUMN = "ECMSOfficialFilingBasisStatus"

def apply_consolidated_audited_filing_selection(metrics: pd.DataFrame, filings: pd.DataFrame):
    """Set each candidate's current filing metadata to its latest consolidated audited filing.

    Yahoo Finance metrics are generally consolidated. The legacy official-filing
    selector may choose one filing per issuer/period without retaining reporting
    basis, so ECMS must independently select basis-matched XBRL URLs. No
    standalone fallback is permitted: unresolved rows remain unverified.
    """
    output = metrics.copy()
    diagnostics = []
    for column in ("OfficialFilingURL", "PublicationDate", "PublicationDateStatus", "OfficialFilingSource"):
        if column not in output.columns:
            output[column] = ""
    output[STATUS_COLUMN] = "WAIT_CONSOLIDATED_AUDITED_FILING"
    required = {"TckrSymb", "FinancialPeriodEnd", "PublicationDate", "PublicationDateStatus", "FilingDescription", "OfficialFilingURL"}
    if filings is None or filings.empty or not required.issubset(filings.columns):
        output["OfficialFilingURL"] = ""
        output["PublicationDate"] = ""
        output["PublicationDateStatus"] = "UNVERIFIED"
        diagnostics.append({"Status": "FILING_REGISTER_SCHEMA_OR_DATA_UNAVAILABLE", "Rows": len(output)})
        return output, pd.DataFrame(diagnostics)
    register = filings.copy()
    register["TckrSymb"] = register["TckrSymb"].astype(str).str.strip().str.upper()
    register["FinancialPeriodEnd"] = register["FinancialPeriodEnd"].astype(str).str[:10]
    register["PublicationDate"] = pd.to_datetime(register["PublicationDate"], errors="coerce")
    descriptions = register["FilingDescription"].astype(str).str.upper()
    eligible = (register["PublicationDateStatus"].astype(str).str.upper().eq("VERIFIED")
                & descriptions.str.contains("CONSOLIDATED", regex=False)
                & descriptions.str.contains("AUDITED", regex=False)
                & ~descriptions.str.contains("STANDALONE|UNAUDITED", regex=True))
    register = register[eligible].copy()
    for idx, metric in output.iterrows():
        symbol = str(metric.get("TckrSymb", "") or "").strip().upper()
        period = str(metric.get("FinancialPeriodEnd", "") or "")[:10]
        subset = register[register["TckrSymb"].eq(symbol) & register["FinancialPeriodEnd"].eq(period)].copy()
        if subset.empty:
            output.at[idx, "OfficialFilingURL"] = ""
            output.at[idx, "PublicationDate"] = ""
            output.at[idx, "PublicationDateStatus"] = "UNVERIFIED"
            diagnostics.append({"TckrSymb": symbol, "FinancialPeriodEnd": period, "Status": "CONSOLIDATED_AUDITED_FILING_NOT_FOUND"})
            continue
        latest_date = subset["PublicationDate"].max()
        latest = subset[subset["PublicationDate"].eq(latest_date)].copy()
        # Prefer a revision if the latest publication date contains original and revision labels.
        desc = latest["FilingDescription"].astype(str).str.upper()
        revised = latest[desc.str.contains("REVISION", regex=False)]
        if not revised.empty:
            latest = revised
        urls = sorted(latest["OfficialFilingURL"].dropna().astype(str).str.strip().unique())
        if len(urls) != 1 or not urls[0].startswith("https://nsearchives.nseindia."):
            output.at[idx, "OfficialFilingURL"] = ""
            output.at[idx, "PublicationDate"] = ""
            output.at[idx, "PublicationDateStatus"] = "UNVERIFIED"
            diagnostics.append({"TckrSymb": symbol, "FinancialPeriodEnd": period, "Status": "CONSOLIDATED_FILING_AMBIGUOUS_OR_URL_INVALID", "CandidateURLs": ";".join(urls)})
            continue
        selected = latest.iloc[0]
        output.at[idx, "OfficialFilingURL"] = urls[0]
        output.at[idx, "PublicationDate"] = latest_date.date().isoformat()
        output.at[idx, "PublicationDateStatus"] = "VERIFIED"
        output.at[idx, "OfficialFilingSource"] = "NSE Integrated Filing - Consolidated Audited (ECMS selection)"
        output.at[idx, STATUS_COLUMN] = "CONSOLIDATED_AUDITED_SELECTED"
        diagnostics.append({"TckrSymb": symbol, "FinancialPeriodEnd": period, "Status": "CONSOLIDATED_AUDITED_SELECTED", "SelectedURL": urls[0], "PublicationDate": latest_date.date().isoformat()})
    return output, pd.DataFrame(diagnostics)
