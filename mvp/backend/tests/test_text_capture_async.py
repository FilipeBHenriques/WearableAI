"""POST /api/text saves immediately and enriches in the background.

Patches database.DB_PATH to a temp file *before* importing server (server.py calls
init_db() at import time) so this test never touches the real data.db.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database

_temp_dir = tempfile.TemporaryDirectory()
database.DB_PATH = Path(_temp_dir.name) / "import_time.db"

import server  # noqa: E402  (must come after the DB_PATH patch above)
from schemas import TextInput  # noqa: E402
from services import command_service  # noqa: E402

_TAKE_NOTE = command_service.Command(type=command_service.CommandType.TAKE_NOTE)


class TextCaptureAsyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_saves_immediately_and_enriches_in_background(self):
        enrich_calls = []

        def fake_enrich(note_id):
            enrich_calls.append(note_id)

        with (
            patch.object(command_service, "detect_command", return_value=_TAKE_NOTE),
            patch.object(server.note_pipeline, "run_enrich", side_effect=fake_enrich) as run_enrich,
            patch.object(server.threading, "Thread") as thread_cls,
        ):
            result = server.api_text(TextInput(text="buy milk tomorrow"))

            # The route must not block on enrichment: run_enrich is only wired up
            # as the background thread's target, never called inline.
            run_enrich.assert_not_called()
            thread_cls.assert_called_once()
            _, kwargs = thread_cls.call_args
            self.assertEqual(kwargs["target"], server.note_pipeline.run_enrich)
            self.assertEqual(kwargs["args"], (result.id,))
            self.assertTrue(kwargs["daemon"])
            thread_cls.return_value.start.assert_called_once()

            # Simulate the background thread actually running, using the same
            # (mocked) target/args the route handed to threading.Thread.
            kwargs["target"](*kwargs["args"])

        self.assertIsNotNone(result.id)
        self.assertTrue(result.saved)
        # Enrichment fields are not populated yet in the immediate response.
        self.assertEqual(result.category, server.note_service.PENDING_CATEGORY)
        self.assertEqual(enrich_calls, [result.id])

    def test_saved_raw_event_is_published_before_enrichment_starts(self):
        published = []

        with (
            patch.object(command_service, "detect_command", return_value=_TAKE_NOTE),
            patch.object(server.event_bus, "publish", side_effect=lambda *a: published.append(a)),
            patch.object(server.threading, "Thread"),
        ):
            result = server.api_text(TextInput(text="buy milk tomorrow"))

        self.assertIn(("notes_changed", {"note_id": result.id, "stage": "saved_raw"}), published)


if __name__ == "__main__":
    unittest.main()
