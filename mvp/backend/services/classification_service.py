"""Classifies note text into a small category set."""

import numpy as np

from services import model_service

CATEGORY_LABELS = ["reminder", "task", "idea"]

_category_embeddings = None


def _get_category_embeddings():
    global _category_embeddings
    if _category_embeddings is None:
        _category_embeddings = model_service.get_sentence_model().encode(CATEGORY_LABELS)
    return _category_embeddings


def classify_text(text: str) -> str:
    from sklearn.metrics.pairwise import cosine_similarity

    model = model_service.get_sentence_model()
    category_embeddings = _get_category_embeddings()
    text_embedding = model.encode(text)
    similarities = cosine_similarity([text_embedding], category_embeddings)
    return CATEGORY_LABELS[int(np.argmax(similarities))].capitalize()
