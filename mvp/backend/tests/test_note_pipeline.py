"""note_pipeline orchestration tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from services import command_service, memory_extraction_service, note_pipeline, note_service
from services.gps_service import Coordinates
from services.note_pipeline import ENRICH_STEPS, INTAKE_STEPS, PipelineStep


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
            [PipelineStep.CLASSIFICATION, PipelineStep.ENRICH_LLM],
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

    def test_enrich_llm_skipped_when_no_note(self):
        # apply() should never be invoked with a None note; the step guards on it.
        with patch.object(memory_extraction_service, "apply") as apply_mock:
            note_pipeline._step_enrich_llm(note_pipeline.PipelineContext(text="x", note=None))

        apply_mock.assert_not_called()

    def test_enrich_continues_after_step_failure(self):
        command = command_service.Command(type=command_service.CommandType.TAKE_NOTE)
        with (
            patch.object(command_service, "detect_command", return_value=command),
            patch("services.classification_service.classify_text", return_value="Idea"),
            patch.object(memory_extraction_service, "apply", side_effect=RuntimeError("boom")),
        ):
            result = note_pipeline.process_text("keep this note")

        self.assertTrue(result.saved)
        note = note_service.get_by_id(result.id)
        self.assertEqual(note.category, "Idea")

    def test_new_note_starts_pending_enrichment(self):
        note_id, _ = note_service.save("a fresh note")
        self.assertIn(note_id, note_service.get_ids_needing_enrichment())

    def test_successful_enrich_marks_done(self):
        note_id, _ = note_service.save("a fresh note")
        with (
            patch("services.classification_service.classify_text", return_value="Idea"),
            patch.object(memory_extraction_service, "apply", return_value=None),
        ):
            note_pipeline.run_enrich(note_id)

        self.assertNotIn(note_id, note_service.get_ids_needing_enrichment())

    def test_step_failure_marks_failed_for_retry(self):
        note_id, _ = note_service.save("a fresh note")
        with (
            patch("services.classification_service.classify_text", return_value="Idea"),
            patch.object(memory_extraction_service, "apply", side_effect=RuntimeError("boom")),
        ):
            note_pipeline.run_enrich(note_id)

        self.assertIn(note_id, note_service.get_ids_needing_enrichment())


if __name__ == "__main__":
    unittest.main()
