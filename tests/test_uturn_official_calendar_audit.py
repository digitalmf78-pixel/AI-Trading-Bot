import unittest
from datetime import date

from research.ecms_uturn.official_calendar_audit import (
    expected_nse_sessions,
    next_nse_session,
)


class OfficialNSECalendarAuditTests(unittest.TestCase):
    def setUp(self):
        self.holidays = {
            date(2026, 3, 26),
            date(2026, 3, 31),
            date(2026, 4, 3),
            date(2026, 4, 14),
            date(2026, 5, 1),
        }

    def test_infy_20_session_window_matches_nse_holidays(self):
        sessions = expected_nse_sessions(date(2026, 3, 20), date(2026, 4, 22), self.holidays)
        self.assertEqual(len(sessions), 20)
        self.assertEqual(sessions[0], "2026-03-20")
        self.assertEqual(sessions[-1], "2026-04-22")

    def test_aartiind_20_session_window_matches_nse_holidays(self):
        sessions = expected_nse_sessions(date(2026, 4, 1), date(2026, 4, 30), self.holidays)
        self.assertEqual(len(sessions), 20)
        self.assertEqual(sessions[0], "2026-04-01")
        self.assertEqual(sessions[-1], "2026-04-30")

    def test_aci_20_session_window_matches_nse_holidays(self):
        sessions = expected_nse_sessions(date(2026, 4, 9), date(2026, 5, 8), self.holidays)
        self.assertEqual(len(sessions), 20)
        self.assertNotIn("2026-05-01", sessions)

    def test_next_post_result_session(self):
        self.assertEqual(
            next_nse_session(date(2026, 4, 23), self.holidays),
            date(2026, 4, 24),
        )
        self.assertEqual(
            next_nse_session(date(2026, 5, 1), self.holidays),
            date(2026, 5, 4),
        )


if __name__ == "__main__":
    unittest.main()
