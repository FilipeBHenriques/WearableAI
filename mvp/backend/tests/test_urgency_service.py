"""Urgency scoring and deadline parsing tests."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import database
from services import note_service, urgency_service
from services.urgency_service import _calculate_urgency, _parse_deadline, _score_from_slack_hours


class UrgencyServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_date_only_uses_end_of_day(self):
        deadline = _parse_deadline("2026-07-20")
        self.assertEqual(deadline, datetime(2026, 7, 20, 23, 59))

    def test_parse_iso_datetime(self):
        deadline = _parse_deadline("2026-07-20T17:30")
        self.assertEqual(deadline, datetime(2026, 7, 20, 17, 30))

    def test_no_deadline_scores_zero(self):
        now = datetime(2026, 7, 19, 12, 0)
        self.assertEqual(_calculate_urgency(None, now), 0)

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
        without = _calculate_urgency(deadline, now, None)
        with_duration = _calculate_urgency(deadline, now, 300)  # 5h of work, 6h until due
        self.assertGreaterEqual(with_duration, without)

    def test_next_friday_deadline_is_exact(self):
        note_id, _ = note_service.save("deliver homework by next Friday")
        note = note_service.get_by_id(note_id)
        with patch(
            "services.model_service.generate_llm",
            return_value='{"has_deadline":true,"deadline_at":"2026-07-20T23:59","reason":"Friday"}',
        ):
            result = urgency_service.analyze_note(
                note,
                datetime.fromisoformat("2026-07-18T15:00:00+01:00"),
            )
        # 2026-07-18 is Saturday → next Friday is 2026-07-24
        self.assertEqual(result.deadline_at, "2026-07-24T23:59")
        self.assertEqual(result.rank_score, result.urgency_score)


if __name__ == "__main__":
    unittest.main()
