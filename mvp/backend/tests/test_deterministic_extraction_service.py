"""Deterministic (non-LLM) field extraction tests."""

import unittest
from datetime import datetime
from unittest.mock import patch

from services import deterministic_extraction_service, model_service

# Saturday, chosen to make "next Friday"/weekday math unambiguous.
CAPTURED_AT = datetime.fromisoformat("2026-07-18T15:00:00")


class RelativeDateTests(unittest.TestCase):
    def test_tomorrow(self):
        result = deterministic_extraction_service.extract("pick up dry cleaning tomorrow", CAPTURED_AT)
        self.assertEqual(result.deadline_at, "2026-07-19T23:59")

    def test_today_with_time(self):
        result = deterministic_extraction_service.extract("call mom today at 5pm", CAPTURED_AT)
        self.assertEqual(result.deadline_at, "2026-07-18T17:00")

    def test_next_week(self):
        result = deterministic_extraction_service.extract("finish the report next week", CAPTURED_AT)
        self.assertEqual(result.deadline_at, "2026-07-25T23:59")

    def test_in_n_days(self):
        result = deterministic_extraction_service.extract("renew passport in 3 days", CAPTURED_AT)
        self.assertEqual(result.deadline_at, "2026-07-21T23:59")

    def test_explicit_iso_date(self):
        result = deterministic_extraction_service.extract("submit taxes 2026-08-01", CAPTURED_AT)
        self.assertEqual(result.deadline_at, "2026-08-01T23:59")

    def test_month_day(self):
        result = deterministic_extraction_service.extract("book flight by August 3", CAPTURED_AT)
        self.assertEqual(result.deadline_at, "2026-08-03T23:59")

    def test_next_friday_weekday_delegation(self):
        result = deterministic_extraction_service.extract("deliver homework by next Friday", CAPTURED_AT)
        # 2026-07-18 is Saturday -> next Friday is 2026-07-24
        self.assertEqual(result.deadline_at, "2026-07-24T23:59")

    def test_no_date_language_leaves_deadline_unresolved_field_absent(self):
        result = deterministic_extraction_service.extract("thinking about a new hobby", CAPTURED_AT)
        self.assertIsNone(result.deadline_at)
        self.assertNotIn("deadline_at", result.unresolved)

    def test_soft_deadline_language_is_unresolved(self):
        result = deterministic_extraction_service.extract("finish this before end of week", CAPTURED_AT)
        self.assertIsNone(result.deadline_at)
        self.assertIn("deadline_at", result.unresolved)

    def test_recurring_weekday_phrase_is_not_treated_as_deadline(self):
        result = deterministic_extraction_service.extract("take out the trash every Monday", CAPTURED_AT)
        self.assertIsNone(result.deadline_at)
        self.assertNotIn("deadline_at", result.unresolved)
        self.assertEqual(result.repeat_cycle, "weekly")

    def test_negated_need_suppresses_deadline(self):
        result = deterministic_extraction_service.extract(
            "I don't need to finish this by tomorrow, there's no rush at all", CAPTURED_AT
        )
        self.assertIsNone(result.deadline_at)
        self.assertNotIn("deadline_at", result.unresolved)

    def test_negated_rush_suppresses_deadline(self):
        result = deterministic_extraction_service.extract(
            "there's no rush but let's grab coffee sometime", CAPTURED_AT
        )
        self.assertIsNone(result.deadline_at)
        self.assertNotIn("deadline_at", result.unresolved)


class DurationHintTests(unittest.TestCase):
    def test_explicit_hours(self):
        result = deterministic_extraction_service.extract("call the plumber tomorrow, 2 hours", CAPTURED_AT)
        self.assertEqual(result.estimated_duration_minutes, 120)

    def test_explicit_minutes(self):
        result = deterministic_extraction_service.extract("email reply tomorrow, 30 min", CAPTURED_AT)
        self.assertEqual(result.estimated_duration_minutes, 30)

    def test_half_an_hour(self):
        result = deterministic_extraction_service.extract("gym session tomorrow, half an hour", CAPTURED_AT)
        self.assertEqual(result.estimated_duration_minutes, 30)

    def test_vague_duration_with_deadline_is_unresolved(self):
        result = deterministic_extraction_service.extract("finish the project tomorrow", CAPTURED_AT)
        self.assertIsNone(result.estimated_duration_minutes)
        self.assertIn("estimated_duration_minutes", result.unresolved)

    def test_no_deadline_never_asks_for_duration(self):
        result = deterministic_extraction_service.extract("finish the project eventually", CAPTURED_AT)
        self.assertNotIn("estimated_duration_minutes", result.unresolved)

    def test_explicit_duration_is_captured_even_without_a_deadline(self):
        # Recurring tasks state durations too ("every Tuesday ... for 45 minutes")
        # — duration extraction must not be gated behind having a one-time deadline.
        result = deterministic_extraction_service.extract(
            "meet the trainer every Tuesday and Thursday at 7am for 45 minutes", CAPTURED_AT
        )
        self.assertIsNone(result.deadline_at)
        self.assertEqual(result.estimated_duration_minutes, 45)
        self.assertNotIn("estimated_duration_minutes", result.unresolved)


class RecurrenceDelegationTests(unittest.TestCase):
    def test_every_monday(self):
        result = deterministic_extraction_service.extract("take out the trash every Monday", CAPTURED_AT)
        self.assertEqual(result.repeat_cycle, "weekly")
        self.assertEqual(result.repeat_days, [1])

    def test_daily(self):
        result = deterministic_extraction_service.extract("stretch daily", CAPTURED_AT)
        self.assertEqual(result.repeat_cycle, "daily")

    def test_repeat_signal_without_clean_pattern_is_unresolved(self):
        result = deterministic_extraction_service.extract("I always forget to water the plants", CAPTURED_AT)
        self.assertIsNone(result.repeat_cycle)
        self.assertNotIn("repeat_cycle", result.unresolved)

    def test_recurring_word_without_pattern_is_unresolved(self):
        result = deterministic_extraction_service.extract("this is a recurring thing I need to handle", CAPTURED_AT)
        self.assertIsNone(result.repeat_cycle)
        self.assertIn("repeat_cycle", result.unresolved)

    def test_no_repeat_language_is_not_unresolved(self):
        result = deterministic_extraction_service.extract("buy milk", CAPTURED_AT)
        self.assertNotIn("repeat_cycle", result.unresolved)


class NoLlmCallTests(unittest.TestCase):
    def test_clear_cases_never_call_llm(self):
        with patch.object(model_service, "generate_llm") as mock_generate:
            deterministic_extraction_service.extract(
                "take out the trash every Monday, buy milk tomorrow, 2 hours", CAPTURED_AT
            )
            mock_generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
