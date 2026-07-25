"""Decides note-to-note relationships.

The embedding-only decision (this module) resolves clear cases without an LLM.
Ambiguous cases are resolved by services.memory_extraction_service, which folds
the tie-break into its single consolidated per-note LLM call.
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np

from database import get_embeddings_for_notes, update_note_embedding
from models import Note
from services import model_service, note_service
from services.service_logger import log_service_call, log_service_step

# Tuned for bge-small-en-v1.5, which packs similarities into a higher, narrower
# band than all-MiniLM-L6-v2 (benchmarked true-pair avg ~0.80, false-pair avg
# ~0.51 vs MiniLM's ~0.65/~0.24) — thresholds are shifted up to match.
SUB_IDEA_THRESHOLD = 0.93
NEW_IDEA_THRESHOLD = 0.65


class RelationshipDecision(str, Enum):
    SUB_IDEA = "SUB_IDEA"
    NEW_IDEA = "NEW_IDEA"
    ASK_LLM = "ASK_LLM"


@dataclass
class RelationshipResult:
    decision: RelationshipDecision
    parent_note_id: int | None
    similarity: float | None = None
    candidate: Note | None = None


def _candidate_notes(note_id: int) -> list[Note]:
    notes = note_service.get_all_flat("active")
    children_by_parent: dict[int, list[int]] = {}
    for note in notes:
        if note.parent_note_id is None:
            continue
        children_by_parent.setdefault(note.parent_note_id, []).append(note.id)

    excluded_ids = {note_id}
    pending = [note_id]
    while pending:
        current = pending.pop()
        for child_id in children_by_parent.get(current, []):
            if child_id in excluded_ids:
                continue
            excluded_ids.add(child_id)
            pending.append(child_id)

    return [note for note in notes if note.id not in excluded_ids]


def _cosine_similarity(a, b) -> float:
    a = np.asarray(a)
    b = np.asarray(b)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        return 0.0
    return float(np.dot(a, b) / denominator)


def _embedding_for(note: Note, model, model_name: str, cache: dict[int, np.ndarray]) -> np.ndarray:
    cached = cache.get(note.id)
    if cached is not None:
        return cached
    embedding = np.asarray(model.encode(note.text), dtype=np.float32)
    update_note_embedding(note.id, embedding, model_name)
    return embedding


def _nearest_note(note: Note, candidates: list[Note]) -> tuple[Note | None, float | None]:
    if not candidates:
        return None, None

    model = model_service.get_sentence_model()
    model_name = model_service.SENTENCE_MODEL_NAME
    log_service_step("using embeddings for nearest note", note_id=note.id, candidates=len(candidates))

    all_ids = [note.id, *(candidate.id for candidate in candidates)]
    cache = get_embeddings_for_notes(all_ids, model_name)

    note_embedding = _embedding_for(note, model, model_name, cache)

    missing = [candidate for candidate in candidates if candidate.id not in cache]
    if missing:
        log_service_step("embedding cache miss", note_id=note.id, missing=len(missing))
        missing_embeddings = model.encode([candidate.text for candidate in missing])
        for candidate, embedding in zip(missing, missing_embeddings):
            embedding = np.asarray(embedding, dtype=np.float32)
            update_note_embedding(candidate.id, embedding, model_name)
            cache[candidate.id] = embedding

    scored = [
        (candidate, _cosine_similarity(note_embedding, cache[candidate.id]))
        for candidate in candidates
    ]
    return max(scored, key=lambda item: item[1])


def resolve_decision(parsed_decision) -> RelationshipDecision:
    """Turns a parsed `parent_decision` value from the consolidated LLM response
    into a RelationshipDecision. Anything other than an exact "SUB_IDEA" match
    defaults to NEW_IDEA."""
    decision = str(parsed_decision or "").strip().upper()
    if decision == RelationshipDecision.SUB_IDEA.value:
        return RelationshipDecision.SUB_IDEA
    return RelationshipDecision.NEW_IDEA


@log_service_call
def embedding_decision(note: Note) -> RelationshipResult:
    """Embedding-only decision. Clear cases (very similar or very dissimilar)
    resolve here with no LLM involved. Ambiguous cases return ASK_LLM with the
    candidate note attached, for memory_extraction_service to fold into its
    single consolidated per-note LLM call."""
    candidate, similarity = _nearest_note(note, _candidate_notes(note.id))
    if candidate is None or similarity is None:
        log_service_step("relationship new idea", note_id=note.id, reason="no_candidates")
        return RelationshipResult(RelationshipDecision.NEW_IDEA, None, similarity)

    if similarity > SUB_IDEA_THRESHOLD:
        log_service_step("embedding threshold matched sub idea", note_id=note.id, candidate_id=candidate.id, similarity=similarity)
        return RelationshipResult(RelationshipDecision.SUB_IDEA, candidate.id, similarity)

    if similarity < NEW_IDEA_THRESHOLD:
        log_service_step("embedding threshold matched new idea", note_id=note.id, candidate_id=candidate.id, similarity=similarity)
        return RelationshipResult(RelationshipDecision.NEW_IDEA, None, similarity)

    log_service_step("relationship ambiguous; needs llm tie-break", note_id=note.id, candidate_id=candidate.id, similarity=similarity)
    return RelationshipResult(RelationshipDecision.ASK_LLM, None, similarity, candidate=candidate)


def attach_parent(note: Note, parent_note_id: int | None) -> Note:
    if parent_note_id is None:
        return note
    note_service.update_parent(note.id, parent_note_id)
    note.parent_note_id = parent_note_id
    return note


@log_service_call
def apply_relationship(note: Note) -> Note:
    """Embedding-only convenience wrapper: resolves clear cases, leaves
    ambiguous cases unlinked. Not used by the note pipeline (which resolves
    ambiguous cases via the consolidated LLM call) — kept for direct/standalone
    use and tests that don't need the LLM tie-break."""
    if note.parent_note_id is not None:
        return note

    result = embedding_decision(note)
    return attach_parent(note, result.parent_note_id)
