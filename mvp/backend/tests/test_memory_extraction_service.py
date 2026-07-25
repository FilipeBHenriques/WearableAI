"""Consolidated memory extraction tests."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np

import database
from services import location_service, memory_extraction_service, note_service, relationship_service

CAPTURED_AT = datetime.fromisoformat("2026-07-18T15:00:00")


class _FakeModel:
    """Deterministic stand-in for SentenceTransformer: encodes text to a vector
    whose angle is controlled by whether "space" appears, landing cosine
    similarity in the ambiguous relationship band (0.65-0.93) for the mixed case."""

    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
            single = True
        else:
            single = False
        vectors = [np.array([1.0, 0.0]) if "space" in text else np.array([0.8, 0.6]) for text in texts]
        return vectors[0] if single else np.array(vectors)


class MemoryExtractionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_clear_note_never_calls_llm(self):
        note_id, _ = note_service.save("buy milk tomorrow, 10 min")
        note = note_service.get_by_id(note_id)

        with patch("services.model_service.generate_llm") as mock_generate:
            memory_extraction_service.apply(note, CAPTURED_AT)

        mock_generate.assert_not_called()
        refreshed = note_service.get_by_id(note_id)
        self.assertEqual(refreshed.deadline_at, "2026-07-19T23:59")
        self.assertEqual(refreshed.estimated_duration_minutes, 10)

    def test_ambiguous_note_asks_only_for_unresolved_fields(self):
        note_id, _ = note_service.save("finish this before end of week")
        note = note_service.get_by_id(note_id)

        with patch(
            "services.model_service.generate_llm",
            return_value='{"deadline_at":"2026-07-24T23:59","reason":"end of week"}',
        ) as mock_generate:
            memory_extraction_service.apply(note, CAPTURED_AT)

        mock_generate.assert_called_once()
        prompt = mock_generate.call_args[0][0]
        self.assertIn('"deadline_at"', prompt)
        self.assertNotIn('"repeat_cycle"', prompt)
        self.assertNotIn('"estimated_duration_minutes"', prompt)

        refreshed = note_service.get_by_id(note_id)
        self.assertEqual(refreshed.deadline_at, "2026-07-24T23:59")

    def test_llm_failure_leaves_fields_unset(self):
        note_id, _ = note_service.save("finish this before end of week")
        note = note_service.get_by_id(note_id)

        with patch("services.model_service.generate_llm", side_effect=RuntimeError("down")):
            memory_extraction_service.apply(note, CAPTURED_AT)

        refreshed = note_service.get_by_id(note_id)
        self.assertIsNone(refreshed.deadline_at)

    def test_deterministic_recurrence_wins_over_llm(self):
        note_id, _ = note_service.save("take out the trash every Monday")
        note = note_service.get_by_id(note_id)

        with patch("services.model_service.generate_llm") as mock_generate:
            memory_extraction_service.apply(note, CAPTURED_AT)

        mock_generate.assert_not_called()
        refreshed = note_service.get_by_id(note_id)
        self.assertEqual(refreshed.repeat_cycle, "weekly")
        self.assertEqual(refreshed.category, "Goal")

    def test_repeat_signal_without_pattern_asks_llm_for_repeat_only(self):
        note_id, _ = note_service.save("this is a recurring thing I need to handle")
        note = note_service.get_by_id(note_id)

        with patch(
            "services.model_service.generate_llm",
            return_value='{"is_repeating":true,"repeat_cycle":"weekly","repeat_days":[1],"repeat_months":null,"repeat_time":null}',
        ) as mock_generate:
            memory_extraction_service.apply(note, CAPTURED_AT)

        mock_generate.assert_called_once()
        prompt = mock_generate.call_args[0][0]
        self.assertIn('"repeat_cycle"', prompt)
        self.assertNotIn('"deadline_at"', prompt)

        refreshed = note_service.get_by_id(note_id)
        self.assertEqual(refreshed.repeat_cycle, "weekly")


class ConsolidatedRelationshipAndLocationTests(unittest.TestCase):
    """Relationship tie-break and location matching are folded into the same
    consolidated call as memory fields — these confirm at most one generate_llm
    call handles whichever of the three a given note actually needs."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()
        self.model = _FakeModel()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ambiguous_relationship_resolved_via_consolidated_call(self):
        with patch.object(relationship_service.model_service, "get_sentence_model", return_value=self.model):
            parent_id, _ = note_service.save("idea about space travel")
            note_id, _ = note_service.save("some plan to discuss")
            note = note_service.get_by_id(note_id)

            with patch(
                "services.model_service.generate_llm",
                return_value='{"parent_decision":"SUB_IDEA"}',
            ) as mock_generate:
                memory_extraction_service.apply(note, CAPTURED_AT)

        mock_generate.assert_called_once()
        prompt = mock_generate.call_args[0][0]
        self.assertIn('"parent_decision"', prompt)
        self.assertNotIn('"location_id"', prompt)

        refreshed = note_service.get_by_id(note_id)
        self.assertEqual(refreshed.parent_note_id, parent_id)

    def test_location_candidate_resolved_via_consolidated_call(self):
        gym = location_service.save_current_location("gym", 40.1, -8.2)
        note_id, _ = note_service.save("stretch once I get to the gym")
        note = note_service.get_by_id(note_id)

        with (
            patch("services.location_service._rank_location_candidates", return_value=[(gym, 0.42)]),
            patch(
                "services.model_service.generate_llm",
                return_value='{"location_id":1,"reason":"gym is mentioned"}',
            ) as mock_generate,
        ):
            memory_extraction_service.apply(note, CAPTURED_AT)

        mock_generate.assert_called_once()
        prompt = mock_generate.call_args[0][0]
        self.assertIn('"location_id"', prompt)
        self.assertNotIn('"parent_decision"', prompt)

        refreshed = note_service.get_by_id(note_id)
        self.assertEqual(refreshed.location_id, gym.id)

    def test_deadline_relationship_and_location_all_resolved_in_one_call(self):
        gym = location_service.save_current_location("gym", 40.1, -8.2)

        with patch.object(relationship_service.model_service, "get_sentence_model", return_value=self.model):
            parent_id, _ = note_service.save("idea about space travel")
            note_id, _ = note_service.save("finish this before end of week at the gym")
            note = note_service.get_by_id(note_id)

            with (
                patch("services.location_service._rank_location_candidates", return_value=[(gym, 0.42)]),
                patch(
                    "services.model_service.generate_llm",
                    return_value=(
                        '{"deadline_at":"2026-07-24T23:59","reason":"end of week",'
                        '"parent_decision":"NEW_IDEA","location_id":1}'
                    ),
                ) as mock_generate,
            ):
                memory_extraction_service.apply(note, CAPTURED_AT)

        mock_generate.assert_called_once()

        refreshed = note_service.get_by_id(note_id)
        self.assertEqual(refreshed.deadline_at, "2026-07-24T23:59")
        self.assertIsNone(refreshed.parent_note_id)
        self.assertEqual(refreshed.location_id, gym.id)

    def test_llm_unavailable_leaves_relationship_and_location_unresolved(self):
        gym = location_service.save_current_location("gym", 40.1, -8.2)

        with patch.object(relationship_service.model_service, "get_sentence_model", return_value=self.model):
            note_service.save("idea about space travel")
            note_id, _ = note_service.save("some plan to discuss at the gym")
            note = note_service.get_by_id(note_id)

            with (
                patch("services.location_service._rank_location_candidates", return_value=[(gym, 0.42)]),
                patch("services.model_service.generate_llm", side_effect=RuntimeError("down")),
            ):
                memory_extraction_service.apply(note, CAPTURED_AT)

        refreshed = note_service.get_by_id(note_id)
        self.assertIsNone(refreshed.parent_note_id)
        self.assertIsNone(refreshed.location_id)


if __name__ == "__main__":
    unittest.main()
