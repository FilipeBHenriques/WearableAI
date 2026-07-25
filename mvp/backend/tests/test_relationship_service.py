"""Embedding-cache behavior for relationship linking."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import database
from services import note_service, relationship_service


class _FakeModel:
    """Deterministic stand-in for SentenceTransformer: same-topic text -> [1, 0],
    different-topic text -> [0, 1], so cosine similarity lands cleanly on either
    side of the SUB_IDEA/NEW_IDEA thresholds without needing an LLM tie-break."""

    def __init__(self):
        self.encode_calls: list[str] = []

    def _vector(self, text: str) -> np.ndarray:
        return np.array([1.0, 0.0]) if "space" in text else np.array([0.0, 1.0])

    def encode(self, texts):
        if isinstance(texts, str):
            self.encode_calls.append(texts)
            return self._vector(texts)
        self.encode_calls.extend(texts)
        return np.array([self._vector(text) for text in texts])


class RelationshipEmbeddingCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()
        self.model = _FakeModel()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_third_note_only_encodes_itself_once_earlier_notes_are_cached(self):
        with (
            patch.object(relationship_service.model_service, "get_sentence_model", return_value=self.model),
            patch.object(relationship_service.model_service, "SENTENCE_MODEL_NAME", "fake-model"),
        ):
            note_a_id, _ = note_service.save("idea about space travel")
            note_a = note_service.get_by_id(note_a_id)
            relationship_service.apply_relationship(note_a)
            # No other active notes exist yet, so there is nothing to compare
            # against and no embedding is computed for note_a itself here.
            self.assertEqual(self.model.encode_calls, [])

            note_b_id, _ = note_service.save("another space travel thought")
            note_b = note_service.get_by_id(note_b_id)
            relationship_service.apply_relationship(note_b)
            # note_b is embedded directly; note_a (the only candidate) is a cache
            # miss and gets embedded + persisted as a side effect.
            self.assertEqual(
                sorted(self.model.encode_calls),
                sorted(["another space travel thought", "idea about space travel"]),
            )
            self.model.encode_calls.clear()

            note_c_id, _ = note_service.save("a third space travel note")
            note_c = note_service.get_by_id(note_c_id)
            relationship_service.apply_relationship(note_c)
            # note_a and note_b are now both cached — only note_c should be encoded.
            self.assertEqual(self.model.encode_calls, ["a third space travel note"])

        linked = note_service.get_by_id(note_b_id)
        self.assertEqual(linked.parent_note_id, note_a_id)

    def test_unrelated_topic_is_not_linked(self):
        with (
            patch.object(relationship_service.model_service, "get_sentence_model", return_value=self.model),
            patch.object(relationship_service.model_service, "SENTENCE_MODEL_NAME", "fake-model"),
        ):
            note_a_id, _ = note_service.save("idea about space travel")
            note_a = note_service.get_by_id(note_a_id)
            relationship_service.apply_relationship(note_a)

            note_b_id, _ = note_service.save("buy groceries")
            note_b = note_service.get_by_id(note_b_id)
            relationship_service.apply_relationship(note_b)

        linked = note_service.get_by_id(note_b_id)
        self.assertIsNone(linked.parent_note_id)


if __name__ == "__main__":
    unittest.main()
