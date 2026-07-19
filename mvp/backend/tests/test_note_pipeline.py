"""note_pipeline orchestration tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from services import command_service, note_pipeline, note_service, recurrence_service, urgency_service
from services.gps_service import Coordinates
from services.note_pipeline import ENRICH_STEPS, INTAKE_STEPS, PipelineStep
from services.recurrence_service import RecurrenceResult


class NotePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_step_order_is_declared(self):
        self.assertEqual(
            [step.id for step in INTAKE_STEPS],
            [PipelineStep.DETECT_COMMAND, PipelineStep.SAVE_NOTE],
        )
        self.assertEqual(
            [step.id for step in ENRICH_STEPS],
            [
                PipelineStep.RELATIONSHIP,
                PipelineStep.CLASSIFICATION,
                PipelineStep.URGENCY,
                PipelineStep.ESTIMATE_DURATION,
                PipelineStep.LOCATION,
                PipelineStep.RECURRENCE,
            ],
        )

    def test_intake_stops_on_save_location(self):
        command = command_service.Command(
            type=command_service.CommandType.SAVE_LOCATION,
            location_name="studio",
        )
        with (
            patch.object(command_service, "detect_command", return_value=command),
            patch(
                "services.gps_service.get_current_coordinates",
                return_value=Coordinates(40.0, -8.0),
            ),
        ):
            result = note_pipeline.run_intake("this is my studio")

        self.assertFalse(result.saved)
        self.assertEqual(result.command_type, "save_location")
        self.assertEqual(result.location_name, "studio")
        self.assertEqual(note_service.get_all_flat(), [])

    def test_duration_skipped_without_deadline(self):
        command = command_service.Command(type=command_service.CommandType.TAKE_NOTE)
        estimate_calls = []

        with (
            patch.object(command_service, "detect_command", return_value=command),
            patch("services.relationship_service.apply_relationship", side_effect=lambda note: note),
            patch("services.classification_service.classify_text", return_value="Task"),
            patch.object(
                urgency_service,
                "apply_urgency",
                return_value=urgency_service.UrgencyResult(deadline_at=None, urgency_score=0, rank_score=0),
            ),
            patch(
                "services.estimate_duration_service.apply_estimate",
                side_effect=lambda note: estimate_calls.append(note.id),
            ),
            patch("services.location_service.apply_location", return_value=None),
            patch("services.recurrence_service.analyze_text", return_value=RecurrenceResult()),
        ):
            result = note_pipeline.process_text("buy milk")

        self.assertTrue(result.saved)
        self.assertEqual(estimate_calls, [])

    def test_enrich_continues_after_step_failure(self):
        command = command_service.Command(type=command_service.CommandType.TAKE_NOTE)
        with (
            patch.object(command_service, "detect_command", return_value=command),
            patch("services.relationship_service.apply_relationship", side_effect=RuntimeError("boom")),
            patch("services.classification_service.classify_text", return_value="Idea"),
            patch.object(urgency_service, "apply_urgency", return_value=urgency_service.UrgencyResult()),
            patch("services.location_service.apply_location", return_value=None),
            patch("services.recurrence_service.analyze_text", return_value=RecurrenceResult()),
        ):
            result = note_pipeline.process_text("keep this note")

        self.assertTrue(result.saved)
        note = note_service.get_by_id(result.id)
        self.assertEqual(note.category, "Idea")


if __name__ == "__main__":
    unittest.main()
