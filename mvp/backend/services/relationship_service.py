"""Decides note-to-note relationships."""

from dataclasses import dataclass
from enum import Enum

import numpy as np

from models import Note
from services import model_service, note_service
from services.llm_utils import extract_json_object
from services.service_logger import log_service_call, log_service_step

SUB_IDEA_THRESHOLD = 0.85
NEW_IDEA_THRESHOLD = 0.45


class RelationshipDecision(str, Enum):
    SUB_IDEA = "SUB_IDEA"
    NEW_IDEA = "NEW_IDEA"
    ASK_LLM = "ASK_LLM"


@dataclass
class RelationshipResult:
    decision: RelationshipDecision
    parent_note_id: int | None
    similarity: float | None = None


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


def _nearest_note(note: Note, candidates: list[Note]) -> tuple[Note | None, float | None]:
    if not candidates:
        return None, None

    model = model_service.get_sentence_model()
    log_service_step("using embeddings for nearest note", note_id=note.id, candidates=len(candidates))
    note_embedding = model.encode(note.text)
    candidate_embeddings = model.encode([candidate.text for candidate in candidates])

    scored = [
        (candidate, _cosine_similarity(note_embedding, candidate_embedding))
        for candidate, candidate_embedding in zip(candidates, candidate_embeddings)
    ]
    return max(scored, key=lambda item: item[1])


def _ask_llm(note: Note, candidate: Note, similarity: float) -> RelationshipDecision:
    log_service_step("using llm relationship decision", note_id=note.id, candidate_id=candidate.id, similarity=similarity)
    prompt = f"""Decide whether the new note should be nested under the parent note.

Definitions:
- SUB_IDEA means the new note belongs under the parent because it is a specific item, action, detail, follow-up, continuation, or narrower version of the parent.
- NEW_IDEA means the new note should stand alone because it is about a different topic, goal, place, person, or context.

Bias:
- If the new note could reasonably be part of the parent, choose SUB_IDEA.
- Choose NEW_IDEA only when the notes are clearly separate.

Return only valid JSON with this exact shape:
{{"decision":"SUB_IDEA","confidence":0.0,"reason":"short reason"}}

Rules:
- decision must be exactly "SUB_IDEA" or "NEW_IDEA".
- confidence must be a number from 0 to 1.
- reason must be one short sentence.
- Do not include markdown or extra text.

Similarity score: {similarity:.3f}
Parent note: {candidate.text}
New note: {note.text}
JSON:"""
    raw_text = model_service.generate_llm(prompt, max_tokens=96).strip()

    try:
        parsed = extract_json_object(raw_text)
    except ValueError:
        log_service_step("llm invalid json", note_id=note.id, candidate_id=candidate.id, response=raw_text)
        return RelationshipDecision.NEW_IDEA

    decision = str(parsed.get("decision", "")).strip().upper()
    if decision == RelationshipDecision.SUB_IDEA.value:
        return RelationshipDecision.SUB_IDEA
    return RelationshipDecision.NEW_IDEA


@log_service_call
def decide_relationship(note: Note) -> RelationshipResult:
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

    llm_status = model_service.get_llm_config_status()
    if not llm_status["configured"]:
        log_service_step("llm unavailable", note_id=note.id, candidate_id=candidate.id, similarity=similarity, error=llm_status["error"])
        return RelationshipResult(RelationshipDecision.ASK_LLM, None, similarity)

    llm_decision = _ask_llm(note, candidate, similarity)
    parent_note_id = candidate.id if llm_decision == RelationshipDecision.SUB_IDEA else None
    log_service_step("llm relationship selected", note_id=note.id, candidate_id=candidate.id, similarity=similarity, decision=llm_decision.value, parent_note_id=parent_note_id)
    return RelationshipResult(RelationshipDecision.ASK_LLM, parent_note_id, similarity)


@log_service_call
def apply_relationship(note: Note) -> Note:
    if note.parent_note_id is not None:
        return note

    result = decide_relationship(note)
    if result.parent_note_id is not None:
        note_service.update_parent(note.id, result.parent_note_id)
        note.parent_note_id = result.parent_note_id
    return note
