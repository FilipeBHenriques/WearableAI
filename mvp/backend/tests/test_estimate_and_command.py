"""Command service corner cases.

Duration-estimate LLM behavior now lives in memory_extraction_service
(see test_memory_extraction_service.py); estimate_duration_service only holds the
pure clamp_minutes helper now.
"""

from unittest.mock import patch
import unittest

from services import command_service


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
