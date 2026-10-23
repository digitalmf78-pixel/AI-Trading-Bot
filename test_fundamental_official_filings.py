import tempfile
import unittest
from pathlib import Path
import pandas as pd

from fundamental_official_filings import apply_official_publication_dates, _period_end_from_description


class TestOfficialFilingPublicationDates(unittest.TestCase):
    def test_extracts_period_end(self):
        self.assertEqual(str(_period_end_from_description('Unaudited Financial Results for quarter ended June 30, 2026')), '2026-06-30')
        self.assertEqual(str(_period_end_from_description('Financial Results for the period ended 30-Jun-2026')), '2026-06-30')

    def test_exact_symbol_and_period_verified(self):
        records = pd.DataFrame([{'TckrSymb':'ABC','FinancialPeriodEnd':'2026-06-30','PublicationDate':pd.NA,'PublicationDateStatus':'UNVERIFIED'}])
        filings = pd.DataFrame([{'TckrSymb':'ABC','FinancialPeriodEnd':'2026-06-30','PublicationDate':'2026-07-25','PublicationDateStatus':'VERIFIED','OfficialFilingURL':'https://www.nseindia.com/companies-listing/corporate-filings-announcements','OfficialSource':'NSE corporate announcements'}])
        with tempfile.TemporaryDirectory() as tmp:
            out = apply_official_publication_dates(records, '2026-10-22', filings=filings, cache_path=Path(tmp)/'cache.csv', diagnostics_path=Path(tmp)/'diag.csv')
        self.assertEqual(out.loc[0,'PublicationDateStatus'], 'VERIFIED')
        self.assertEqual(str(out.loc[0,'PublicationDate'])[:10], '2026-07-25')

    def test_future_publication_not_verified(self):
        records = pd.DataFrame([{'TckrSymb':'ABC','FinancialPeriodEnd':'2026-06-30','PublicationDate':pd.NA,'PublicationDateStatus':'UNVERIFIED'}])
        filings = pd.DataFrame([{'TckrSymb':'ABC','FinancialPeriodEnd':'2026-06-30','PublicationDate':'2026-10-23','PublicationDateStatus':'VERIFIED','OfficialFilingURL':'https://www.nseindia.com/companies-listing/corporate-filings-announcements','OfficialSource':'NSE corporate announcements'}])
        with tempfile.TemporaryDirectory() as tmp:
            out = apply_official_publication_dates(records, '2026-10-22', filings=filings, cache_path=Path(tmp)/'cache.csv', diagnostics_path=Path(tmp)/'diag.csv')
        self.assertNotEqual(out.loc[0,'PublicationDateStatus'], 'VERIFIED')

    def test_symbol_mismatch_stays_unverified(self):
        records = pd.DataFrame([{'TckrSymb':'ABC','FinancialPeriodEnd':'2026-06-30','PublicationDate':pd.NA,'PublicationDateStatus':'UNVERIFIED'}])
        filings = pd.DataFrame([{'TckrSymb':'XYZ','FinancialPeriodEnd':'2026-06-30','PublicationDate':'2026-07-25','PublicationDateStatus':'VERIFIED'}])
        with tempfile.TemporaryDirectory() as tmp:
            out = apply_official_publication_dates(records, '2026-10-22', filings=filings, cache_path=Path(tmp)/'cache.csv', diagnostics_path=Path(tmp)/'diag.csv')
        self.assertEqual(out.loc[0,'PublicationDateStatus'], 'UNVERIFIED')

    def test_collection_rows_are_never_dropped(self):
        records = pd.DataFrame([{'TckrSymb':'ABC','FinancialPeriodEnd':'2026-06-30'}, {'TckrSymb':'XYZ','FinancialPeriodEnd':'2026-06-30'}])
        with tempfile.TemporaryDirectory() as tmp:
            out = apply_official_publication_dates(records, '2026-10-22', filings=pd.DataFrame(), cache_path=Path(tmp)/'cache.csv', diagnostics_path=Path(tmp)/'diag.csv')
        self.assertEqual(len(out), 2)


if __name__ == '__main__':
    unittest.main()
