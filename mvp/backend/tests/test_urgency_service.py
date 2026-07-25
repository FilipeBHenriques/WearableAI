"""Urgency scoring and deadline parsing tests."""

import unittest
from datetime import datetime

from services.urgency_service import calculate_urgency, parse_deadline, _score_from_slack_hours


class UrgencyServiceTests(unittest.TestCase):
    def test_parse_date_only_uses_end_of_day(self):
        deadline = parse_deadline("2026-07-20")
        self.assertEqual(deadline, datetime(2026, 7, 20, 23, 59))

    def test_parse_iso_datetime(self):
        deadline = parse_deadline("2026-07-20T17:30")
        self.assertEqual(deadline, datetime(2026, 7, 20, 17, 30))

    def test_no_deadline_scores_zero(self):
        now = datetime(2026, 7, 19, 12, 0)
        self.assertEqual(calculate_urgency(None, now), 0)

    def test_slack_curve_ranges(self):
        # Overdue
        self.assertGreaterEqual(_score_from_slack_hours(-1), 97)
        self.assertLessEqual(_score_from_slack_hours(-1), 100)
        # Near due
        self.assertGreaterEqual(_score_from_slack_hours(0), 90)
        # About one day of slack
        day = _score_from_slack_hours(24)
        self.assertGreaterEqual(day, 75)
        self.assertLessEqual(day, 95)
        # About one week
        week = _score_from_slack_hours(168)
        self.assertGreaterEqual(week, 45)
        self.assertLessEqual(week, 75)
        # About one month
        month = _score_from_slack_hours(720)
        self.assertGreaterEqual(month, 5)
        self.assertLessEqual(month, 40)
        # More slack → lower or equal score
        self.assertGreaterEqual(_score_from_slack_hours(0), _score_from_slack_hours(24))
        self.assertGreaterEqual(_score_from_slack_hours(24), _score_from_slack_hours(168))

    def test_duration_reduces_slack_and_raises_urgency(self):
        now = datetime(2026, 7, 19, 12, 0)
        deadline = "2026-07-19T18:00"
        without = calculate_urgency(deadline, now, None)
        with_duration = calculate_urgency(deadline, now, 300)  # 5h of work, 6h until due
        self.assertGreaterEqual(with_duration, without)


if __name__ == "__main__":
    unittest.main()
