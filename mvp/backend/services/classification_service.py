"""Classifies note text into a small category set."""

import numpy as np

from services import model_service
from services.service_logger import log_service_call, log_service_step

CATEGORY_LABELS = ["reminder", "task", "idea"]

_category_embeddings = None


def _get_category_embeddings():
    global _category_embeddings
    if _category_embeddings is None:
        log_service_step("building category embeddings", labels=CATEGORY_LABELS)
        _category_embeddings = model_service.get_sentence_model().encode(CATEGORY_LABELS)
    return _category_embeddings


@log_service_call
def classify_text(text: str) -> str:
    from sklearn.metrics.pairwise import cosine_similarity

    model = model_service.get_sentence_model()
    category_embeddings = _get_category_embeddings()
    text_embedding = model.encode(text)
    log_service_step("using embeddings", labels=CATEGORY_LABELS)
    similarities = cosine_similarity([text_embedding], category_embeddings)
    category = CATEGORY_LABELS[int(np.argmax(similarities))].capitalize()
    log_service_step("embedding category selected", category=category, scores=similarities.tolist())
    return category
