"""Per-location context-phrase embedding cache + invalidation tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import database
from services import location_service


class _FakeModel:
    def __init__(self):
        self.encode_calls: list[str] = []

    def encode(self, texts):
        if isinstance(texts, str):
            self.encode_calls.append(texts)
            return np.array([1.0, 0.0])
        self.encode_calls.extend(texts)
        return np.array([[1.0, 0.0] for _ in texts])


class LocationServiceCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()
        self.model = _FakeModel()
        location_service._location_phrase_embeddings.clear()

    def tearDown(self):
        self.temp_dir.cleanup()
        location_service._location_phrase_embeddings.clear()

    def test_second_call_does_not_reencode_cached_location_phrases(self):
        gym = location_service.save_current_location("gym", 40.1, -8.2)

        with patch.object(location_service.model_service, "get_sentence_model", return_value=self.model):
            location_service._rank_location_candidates("stretch at the gym", [gym])
            first_call_count = len(self.model.encode_calls)
            self.assertGreater(first_call_count, 0)

            location_service._rank_location_candidates("back at the gym again", [gym])

            # Only the note text should be encoded on the second call; the
            # location's phrase embeddings came from cache.
            self.assertEqual(len(self.model.encode_calls), first_call_count + 1)

    def test_deleting_location_invalidates_its_cache(self):
        gym = location_service.save_current_location("gym", 40.1, -8.2)

        with patch.object(location_service.model_service, "get_sentence_model", return_value=self.model):
            location_service._rank_location_candidates("stretch at the gym", [gym])

        self.assertIn(gym.id, location_service._location_phrase_embeddings)
        location_service.delete_saved_location(gym.id)
        self.assertNotIn(gym.id, location_service._location_phrase_embeddings)

    def test_resaving_location_invalidates_its_cache(self):
        gym = location_service.save_current_location("gym", 40.1, -8.2)

        with patch.object(location_service.model_service, "get_sentence_model", return_value=self.model):
            location_service._rank_location_candidates("stretch at the gym", [gym])

        self.assertIn(gym.id, location_service._location_phrase_embeddings)
        location_service.save_current_location("gym", 41.0, -9.0)
        self.assertNotIn(gym.id, location_service._location_phrase_embeddings)


if __name__ == "__main__":
    unittest.main()
