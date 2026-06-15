"""Classifies a transcript into a note category.

Model loads on first use so the API server starts immediately.
"""

import numpy as np

from schemas import CategorizeResult
from services import note_service

categories = ["reminder", "task", "idea"]

_model = None
_category_embeddings = None


def _ensure_model():
    global _model, _category_embeddings
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
        _category_embeddings = _model.encode(categories)
    return _model, _category_embeddings


def _classify(text: str) -> str:
    from sklearn.metrics.pairwise import cosine_similarity

    _, category_embeddings = _ensure_model()
    text_embedding = _model.encode(text)
    similarities = cosine_similarity([text_embedding], category_embeddings)
    return categories[int(np.argmax(similarities))]


def categorize(note_id: int) -> CategorizeResult | None:
    """Classify a saved note and persist its category."""
    note = note_service.get_by_id(note_id)
    if note is None:
        return None

    category = _classify(note.text).capitalize()
    note_service.update_category(note_id, category)
    return CategorizeResult(id=note_id, category=category)
