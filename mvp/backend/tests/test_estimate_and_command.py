"""Estimate duration and command service corner cases."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from services import command_service, estimate_duration_service, note_service


class EstimateDurationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_stores_llm_estimate(self):
        note_id, _ = note_service.save("write a short email")
        note = note_service.get_by_id(note_id)
        with patch(
            "services.model_service.generate_llm",
            return_value='{"estimated_duration_minutes":12,"reason":"quick email"}',
        ):
            result = estimate_duration_service.apply_estimate(note)

        self.assertEqual(result.estimated_duration_minutes, 12)
        refreshed = note_service.get_by_id(note_id)
        self.assertEqual(refreshed.estimated_duration_minutes, 12)

    def test_failure_leaves_duration_unset(self):
        note_id, _ = note_service.save("ambiguous task")
        note = note_service.get_by_id(note_id)
        with patch("services.model_service.generate_llm", side_effect=RuntimeError("down")):
            result = estimate_duration_service.apply_estimate(note)

        self.assertIsNone(result.estimated_duration_minutes)
        refreshed = note_service.get_by_id(note_id)
        self.assertIsNone(refreshed.estimated_duration_minutes)


class CommandServiceTests(unittest.TestCase):
    def test_empty_defaults_to_take_note(self):
        result = command_service.detect_command("   ")
        self.assertEqual(result.type, command_service.CommandType.TAKE_NOTE)

    def test_llm_save_location(self):
        with (
            patch("services.model_service.get_llm_config_status", return_value={"configured": True}),
            patch.object(
                command_service,
                "_ask_llm",
                return_value=command_service.Command(
                    type=command_service.CommandType.SAVE_LOCATION,
                    location_name="office",
                ),
            ),
        ):
            result = command_service.detect_command("save this place as office")

        self.assertEqual(result.type, command_service.CommandType.SAVE_LOCATION)
        self.assertEqual(result.location_name, "office")

    def test_llm_down_defaults_to_take_note(self):
        with patch(
            "services.model_service.get_llm_config_status",
            return_value={"configured": False, "error": "offline"},
        ):
            result = command_service.detect_command("this is my house")

        self.assertEqual(result.type, command_service.CommandType.TAKE_NOTE)


if __name__ == "__main__":
    unittest.main()
