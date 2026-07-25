"""Enrichment retry sweep tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from services import enrichment_retry_service, note_pipeline, note_service


class EnrichmentRetryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_retries_pending_and_failed_notes_only(self):
        pending_id, _ = note_service.save("still pending")
        failed_id, _ = note_service.save("failed once")
        note_service.update_enrichment_status(failed_id, "failed")
        done_id, _ = note_service.save("already done")
        note_service.update_enrichment_status(done_id, "done")

        with patch.object(note_pipeline, "run_enrich") as run_enrich:
            retried = enrichment_retry_service.retry_pending_enrichment()

        self.assertEqual(sorted(retried), sorted([pending_id, failed_id]))
        self.assertEqual(
            sorted(call.args[0] for call in run_enrich.call_args_list),
            sorted([pending_id, failed_id]),
        )

    def test_nothing_to_retry_calls_run_enrich_zero_times(self):
        note_id, _ = note_service.save("already done")
        note_service.update_enrichment_status(note_id, "done")

        with patch.object(note_pipeline, "run_enrich") as run_enrich:
            retried = enrichment_retry_service.retry_pending_enrichment()

        self.assertEqual(retried, [])
        run_enrich.assert_not_called()


if __name__ == "__main__":
    unittest.main()
