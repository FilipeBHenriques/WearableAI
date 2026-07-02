import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from services.llm_utils import extract_json_object
from services import capture_service, command_service, location_service, note_service, recurrence_service, urgency_service


class LocationCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_location_command_saves_coordinates_without_note(self):
        command = command_service.Command(
            type=command_service.CommandType.SAVE_LOCATION,
            location_name="house",
        )
        with (
            patch.object(command_service, "detect_command", return_value=command),
            patch.dict("os.environ", {"MOCK_GPS_LAT": "40.1", "MOCK_GPS_LON": "-8.2"}),
        ):
            result = capture_service.process_note_text("this is my house")

        self.assertFalse(result.saved)
        self.assertTrue(result.command_processed)
        self.assertEqual(result.command_type, "save_location")
        self.assertEqual(result.location_name, "house")
        self.assertEqual(result.location_latitude, 40.1)
        self.assertEqual(result.location_longitude, -8.2)
        self.assertEqual(note_service.get_all_flat(), [])

    def test_note_referencing_gym_links_to_saved_location_by_llm_selection(self):
        location_service.save_current_location("gym", 40.1, -8.2)
        command = command_service.Command(type=command_service.CommandType.TAKE_NOTE)

        with (
            patch.object(command_service, "detect_command", return_value=command),
            patch("services.relationship_service.apply_relationship", side_effect=lambda note: note),
            patch("services.classification_service.classify_text", return_value="Task"),
            patch.object(urgency_service, "apply_urgency", return_value=urgency_service.UrgencyResult()),
            patch("services.location_service._rank_location_candidates", return_value=[(location_service.get_locations()[0], 0.42)]),
            patch("services.model_service.get_llm_config_status", return_value={"configured": True}),
            patch("services.model_service.generate_llm", return_value='{"location_id":1,"reason":"gym is mentioned"}'),
        ):
            result = capture_service.process_note_text(
                "I need to stretch once I get to the gym"
            )

        self.assertTrue(result.saved)
        self.assertEqual(result.command_type, "take_note")
        self.assertEqual(result.location_name, "gym")
        note = note_service.get_by_id(result.id)
        self.assertIsNotNone(note)
        self.assertEqual(note.location_name, "gym")

    def test_location_service_skips_link_when_llm_unavailable(self):
        location = location_service.save_current_location("gym", 40.1, -8.2)

        with (
            patch("services.location_service._rank_location_candidates", return_value=[(location, 0.95)]),
            patch("services.model_service.get_llm_config_status", return_value={"configured": False, "error": "no llm"}),
        ):
            result = location_service.find_relevant_location("stretch at the gym")

        self.assertIsNone(result)

    def test_empty_text_is_not_saved(self):
        result = capture_service.process_note_text("   ")

        self.assertFalse(result.saved)
        self.assertFalse(result.command_processed)
        self.assertIsNone(result.id)

    def test_enrichment_failures_still_leave_saved_note(self):
        command = command_service.Command(type=command_service.CommandType.TAKE_NOTE)
        with (
            patch.object(command_service, "detect_command", return_value=command),
            patch("services.relationship_service.apply_relationship", side_effect=RuntimeError("relationship failed")),
            patch("services.classification_service.classify_text", side_effect=RuntimeError("classification failed")),
            patch.object(urgency_service, "apply_urgency", side_effect=RuntimeError("urgency failed")),
            patch("services.location_service.apply_location", side_effect=RuntimeError("location failed")),
        ):
            result = capture_service.process_note_text("Save this thought even if enrichment fails")

        self.assertTrue(result.saved)
        self.assertIsNotNone(result.id)
        note = note_service.get_by_id(result.id)
        self.assertIsNotNone(note)
        self.assertEqual(note.text, "Save this thought even if enrichment fails")
        self.assertEqual(note.category, note_service.PENDING_CATEGORY)

    def test_command_service_uses_generic_save_location_intent(self):
        with (
            patch("services.model_service.get_llm_config_status", return_value={"configured": True}),
            patch.object(
                command_service,
                "_ask_llm",
                return_value=command_service.Command(
                    type=command_service.CommandType.SAVE_LOCATION,
                    location_name="studio",
                ),
            ),
        ):
            result = command_service.detect_command("save this as studio")

        self.assertEqual(result.type, command_service.CommandType.SAVE_LOCATION)
        self.assertEqual(result.location_name, "studio")

    def test_command_service_uses_llm_for_location_command(self):
        with (
            patch("services.model_service.get_llm_config_status", return_value={"configured": True}),
            patch.object(
                command_service,
                "_ask_llm",
                return_value=command_service.Command(
                    type=command_service.CommandType.SAVE_LOCATION,
                    location_name="gym",
                ),
            ) as ask_llm,
        ):
            result = command_service.detect_command("This is my gym")

        ask_llm.assert_called_once()
        self.assertEqual(result.type, command_service.CommandType.SAVE_LOCATION)
        self.assertEqual(result.location_name, "gym")

    def test_command_service_defaults_to_take_note_when_llm_unavailable(self):
        with (
            patch(
                "services.model_service.get_llm_config_status",
                return_value={"configured": False, "error": "no llm"},
            ),
        ):
            result = command_service.detect_command("This is the gym")

        self.assertEqual(result.type, command_service.CommandType.TAKE_NOTE)
        self.assertIsNone(result.location_name)

    def test_command_service_defaults_to_take_note(self):
        with (
            patch("services.model_service.get_llm_config_status", return_value={"configured": True}),
            patch.object(
                command_service,
                "_ask_llm",
                return_value=command_service.Command(type=command_service.CommandType.TAKE_NOTE),
            ) as ask_llm,
        ):
            result = command_service.detect_command("i need to go to the gym")

        ask_llm.assert_called_once()
        self.assertEqual(result.type, command_service.CommandType.TAKE_NOTE)
        self.assertIsNone(result.location_name)

    def test_location_service_does_not_rewrite_saved_location_names(self):
        location = location_service.save_current_location("my home", 40.1, -8.2)

        self.assertEqual(location.name, "my home")

    def test_deleting_location_clears_note_links(self):
        location = location_service.save_current_location("gym", 40.1, -8.2)
        note_id, _ = note_service.save("stretch at the gym")
        note = note_service.get_by_id(note_id)
        self.assertIsNotNone(note)

        with patch("services.location_service.find_relevant_location", return_value=location):
            location_service.apply_location(note)
        linked_note = note_service.get_by_id(note_id)
        self.assertEqual(linked_note.location_id, location.id)

        self.assertTrue(location_service.delete_saved_location(location.id))
        unlinked_note = note_service.get_by_id(note_id)
        self.assertIsNone(unlinked_note.location_id)
        self.assertEqual(location_service.get_locations(), [])

    def test_shared_json_extraction(self):
        self.assertEqual(extract_json_object('{"command":"take_note"}'), {"command": "take_note"})
        self.assertEqual(
            extract_json_object('prefix {"command":"save_location","location_name":"gym"} suffix'),
            {"command": "save_location", "location_name": "gym"},
        )

    def test_recurrence_fallback_detects_daily_repeat(self):
        with patch("services.model_service.generate_llm", side_effect=RuntimeError("no llm")):
            result = recurrence_service.analyze_text("drink water every day")

        self.assertEqual(result.repeat_cycle, "daily")
        self.assertIsNone(result.repeat_days)

    def test_recurrence_fallback_detects_weekly_repeat_with_time(self):
        with patch("services.model_service.generate_llm", side_effect=RuntimeError("no llm")):
            result = recurrence_service.analyze_text("go to the gym monday wednesday friday at 18")

        self.assertEqual(result.repeat_cycle, "weekly")
        self.assertEqual(result.repeat_days, [1, 3, 5])
        self.assertEqual(result.repeat_time, "18:00")

    def test_recurrence_fallback_detects_monthly_repeat(self):
        with patch("services.model_service.generate_llm", side_effect=RuntimeError("no llm")):
            result = recurrence_service.analyze_text("pay rent every month on the 1st")

        self.assertEqual(result.repeat_cycle, "monthly")
        self.assertEqual(result.repeat_days, [1])

    def test_recurrence_fallback_detects_yearly_repeat(self):
        with patch("services.model_service.generate_llm", side_effect=RuntimeError("no llm")):
            result = recurrence_service.analyze_text("renew passport every year on July 2")

        self.assertEqual(result.repeat_cycle, "yearly")
        self.assertEqual(result.repeat_days, [2])
        self.assertEqual(result.repeat_months, [7])

    def test_active_notes_include_due_repeats_and_exclude_not_due(self):
        due_id, _ = note_service.save("daily water")
        note_service.update_recurrence(due_id, "daily", None, None, None)

        not_due_id, _ = note_service.save("not today")
        tomorrow_weekday = (recurrence_service.date.today().isoweekday() % 7) + 1
        note_service.update_recurrence(not_due_id, "weekly", [tomorrow_weekday], None, None)

        active_ids = {note.id for note in note_service.get_all("active")}

        self.assertIn(due_id, active_ids)
        self.assertNotIn(not_due_id, active_ids)

    def test_completed_today_repeat_is_hidden_from_active(self):
        note_id, _ = note_service.save("daily water")
        note_service.update_recurrence(note_id, "daily", None, None, None)

        status = note_service.toggle_note_status(note_id)
        active_ids = {note.id for note in note_service.get_all("active")}

        self.assertEqual(status, recurrence_service.repeat_done_status())
        self.assertNotIn(note_id, active_ids)

    def test_repeat_toggle_clears_today_completion(self):
        note_id, _ = note_service.save("daily water")
        note_service.update_recurrence(note_id, "daily", None, None, None)

        note_service.toggle_note_status(note_id)
        status = note_service.toggle_note_status(note_id)

        self.assertEqual(status, "active")
        self.assertIn(note_id, {note.id for note in note_service.get_all("active")})

    def test_normal_note_toggle_still_marks_done(self):
        note_id, _ = note_service.save("normal task")

        status = note_service.toggle_note_status(note_id)

        self.assertEqual(status, "done")
        self.assertEqual(note_service.get_by_id(note_id).status, "done")


if __name__ == "__main__":
    unittest.main()
