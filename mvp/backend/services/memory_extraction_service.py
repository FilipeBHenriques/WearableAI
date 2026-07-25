"""Consolidated per-note enrichment: deterministic/embedding passes first, then at
most one LLM call for whatever this note still needs resolved — memory fields
(deadline/duration/recurrence), a relationship tie-break, and/or a location match.

This is the single place that calls the LLM during note enrichment. Each concern
contributes an optional section to one prompt, only when its own cheap pre-pass
(regex/embeddings) couldn't resolve it on its own:
- memory fields: deterministic_extraction_service leaves them unresolved
- relationship: relationship_service.embedding_decision returns ASK_LLM
  (similarity fell in the ambiguous band)
- location: location_service.location_candidates found saved locations to
  choose among
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from models import Location, Note, RepeatCycle
from services import (
    deterministic_extraction_service,
    estimate_duration_service,
    location_service,
    model_service,
    note_service,
    recurrence_service,
    relationship_service,
    urgency_service,
)
from services.llm_utils import extract_json_object
from services.relationship_service import RelationshipDecision, RelationshipResult
from services.service_logger import log_service_call, log_service_step

_FIELD_TOKENS = {
    "deadline_at": 64,
    "estimated_duration_minutes": 32,
    "repeat_cycle": 96,
}
_BASE_TOKENS = 32
_RELATIONSHIP_TOKENS = 64
_LOCATION_TOKENS = 64


@dataclass
class ExtractionFields:
    deadline_at: str | None = None
    urgency_reason: str | None = None
    estimated_duration_minutes: int | None = None
    repeat_cycle: RepeatCycle | None = None
    repeat_days: list[int] | None = None
    repeat_months: list[int] | None = None
    repeat_time: str | None = None
    parent_note_id: int | None = None
    location: Location | None = None


# Filled-in example values per possible key, keyed the same as _ask_shape's output.
# Some models (e.g. minicpm5) follow a worked example far more reliably than an
# abstract "these are the keys" description with null placeholders — a schema
# alone isn't enough to keep them from renaming/abbreviating keys.
_EXAMPLE_VALUES = {
    "deadline_at": "2026-07-24T23:59",
    "reason": "end of week",
    "estimated_duration_minutes": 30,
    "is_repeating": True,
    "repeat_cycle": "weekly",
    "repeat_days": [1, 3],
    "repeat_months": None,
    "repeat_time": "18:00",
    "parent_decision": "SUB_IDEA",
    "location_id": 1,
}


def _ask_shape(unresolved: set[str], relationship_pre: RelationshipResult | None, location_candidates: list[tuple[Location, float]]) -> dict:
    shape: dict = {}
    if "deadline_at" in unresolved:
        shape["deadline_at"] = None
        shape["reason"] = None
    if "estimated_duration_minutes" in unresolved:
        shape["estimated_duration_minutes"] = None
    if "repeat_cycle" in unresolved:
        shape["is_repeating"] = False
        shape["repeat_cycle"] = None
        shape["repeat_days"] = None
        shape["repeat_months"] = None
        shape["repeat_time"] = None
    if relationship_pre is not None:
        shape["parent_decision"] = None
    if location_candidates:
        shape["location_id"] = None
    return shape


def _build_prompt(
    note: Note,
    unresolved: set[str],
    captured_at: datetime,
    relationship_pre: RelationshipResult | None,
    location_candidates: list[tuple[Location, float]],
) -> str:
    shape = _ask_shape(unresolved, relationship_pre, location_candidates)
    example = {key: _EXAMPLE_VALUES.get(key) for key in shape}
    sections = [f"""Return one JSON object only. No explanation, no markdown.

Fill only these keys, using exactly these key names — do not rename, translate,
abbreviate, or add extra keys:
{json.dumps(shape)}

Example of a correctly formatted response (key names must match exactly, values are illustrative only):
{json.dumps(example)}

Current local date: {captured_at.date().isoformat()}
Note: {note.text}"""]

    if unresolved:
        sections.append("Fill the keys above from the note above, keeping the same key names.")

    if relationship_pre is not None:
        sections.append(f"""Relationship: decide whether the note belongs under this existing parent note.
- SUB_IDEA: the note is a specific item, action, detail, follow-up, continuation, or narrower version of the parent.
- NEW_IDEA: the note is about a different topic, goal, place, person, or context.
Bias toward SUB_IDEA when it could reasonably fit. parent_decision must be exactly "SUB_IDEA" or "NEW_IDEA".
Similarity score: {relationship_pre.similarity:.3f}
Parent note: {relationship_pre.candidate.text}""")

    if location_candidates:
        candidate_lines = "\n".join(
            f"- id: {location.id}, name: {location.name}, embedding_score: {score:.3f}"
            for location, score in location_candidates
        )
        sections.append(f"""Location: choose whether the note should be attached to one saved location.
Choose a location only if the note clearly refers to that place by name, context, or natural wording.
location_id must be one of the candidate ids or null.
Saved location candidates:
{candidate_lines}""")

    sections.append("JSON:")
    return "\n\n".join(sections)


@log_service_call
def extract(
    note: Note,
    unresolved: set[str],
    captured_at: datetime,
    relationship_pre: RelationshipResult | None = None,
    location_candidates: list[tuple[Location, float]] | None = None,
) -> ExtractionFields:
    location_candidates = location_candidates or []
    needs_relationship = relationship_pre is not None and relationship_pre.decision == RelationshipDecision.ASK_LLM

    if not unresolved and not needs_relationship and not location_candidates:
        return ExtractionFields()

    max_tokens = _BASE_TOKENS + sum(_FIELD_TOKENS.get(name, 48) for name in unresolved)
    if needs_relationship:
        max_tokens += _RELATIONSHIP_TOKENS
    if location_candidates:
        max_tokens += _LOCATION_TOKENS

    try:
        log_service_step(
            "using consolidated enrichment llm",
            note_id=note.id,
            fields=sorted(unresolved),
            relationship=needs_relationship,
            location_candidates=len(location_candidates),
        )
        raw_text = model_service.generate_llm(
            _build_prompt(note, unresolved, captured_at, relationship_pre if needs_relationship else None, location_candidates),
            max_tokens=max_tokens,
            json_mode=True,
        )
        parsed = extract_json_object(raw_text)
    except Exception as exc:
        log_service_step("consolidated enrichment llm failed", note_id=note.id, error=repr(exc))
        return ExtractionFields()

    fields = ExtractionFields()

    if "deadline_at" in unresolved:
        raw_deadline = str(parsed.get("deadline_at") or "").strip() or None
        parsed_deadline = urgency_service.parse_deadline(raw_deadline)
        if parsed_deadline is not None:
            fields.deadline_at = parsed_deadline.isoformat(timespec="minutes")
            fields.urgency_reason = str(parsed.get("reason") or "").strip() or None

    if "estimated_duration_minutes" in unresolved:
        raw_minutes = parsed.get("estimated_duration_minutes")
        if isinstance(raw_minutes, (int, float)):
            fields.estimated_duration_minutes = estimate_duration_service.clamp_minutes(int(raw_minutes))

    if "repeat_cycle" in unresolved:
        recurrence = recurrence_service.from_parsed(parsed)
        fields.repeat_cycle = recurrence.repeat_cycle
        fields.repeat_days = recurrence.repeat_days
        fields.repeat_months = recurrence.repeat_months
        fields.repeat_time = recurrence.repeat_time

    if needs_relationship:
        decision = relationship_service.resolve_decision(parsed.get("parent_decision"))
        if decision == RelationshipDecision.SUB_IDEA:
            fields.parent_note_id = relationship_pre.candidate.id

    if location_candidates:
        fields.location = location_service.resolve_location(location_candidates, parsed.get("location_id"))

    log_service_step(
        "consolidated enrichment llm response",
        note_id=note.id,
        deadline_at=fields.deadline_at,
        estimated_duration_minutes=fields.estimated_duration_minutes,
        repeat_cycle=fields.repeat_cycle,
        parent_note_id=fields.parent_note_id,
        location_id=fields.location.id if fields.location else None,
    )
    return fields


@log_service_call
def apply(note: Note, captured_at: datetime | None = None) -> None:
    captured_at = captured_at or datetime.now().astimezone()

    deterministic = deterministic_extraction_service.extract(note.text, captured_at)

    relationship_pre = relationship_service.embedding_decision(note) if note.parent_note_id is None else None
    candidates = location_service.location_candidates(note.text)

    llm_fields = extract(note, deterministic.unresolved, captured_at, relationship_pre, candidates)

    deadline_at = deterministic.deadline_at or llm_fields.deadline_at
    urgency_reason = deterministic.urgency_reason if deterministic.deadline_at else llm_fields.urgency_reason
    duration = (
        deterministic.estimated_duration_minutes
        if deterministic.estimated_duration_minutes is not None
        else llm_fields.estimated_duration_minutes
    )

    urgency_score = urgency_service.calculate_urgency(deadline_at, captured_at, duration)
    rank_score = urgency_score
    note_service.update_urgency(note.id, deadline_at, urgency_score, rank_score, urgency_reason)
    note.deadline_at = deadline_at
    note.urgency_score = urgency_score
    note.rank_score = rank_score
    note.urgency_reason = urgency_reason

    if duration is not None:
        note_service.update_estimated_duration(note.id, duration)
        note.estimated_duration_minutes = duration

    repeat_source = deterministic if deterministic.repeat_cycle is not None else llm_fields
    if repeat_source.repeat_cycle is not None:
        note_service.update_recurrence(
            note.id,
            repeat_source.repeat_cycle,
            repeat_source.repeat_days,
            repeat_source.repeat_months,
            repeat_source.repeat_time,
        )
        note_service.update_category(note.id, "Goal")
        note.repeat_cycle = repeat_source.repeat_cycle
        note.repeat_days = repeat_source.repeat_days
        note.repeat_months = repeat_source.repeat_months
        note.repeat_time = repeat_source.repeat_time

    if relationship_pre is not None:
        parent_note_id = llm_fields.parent_note_id if relationship_pre.decision == RelationshipDecision.ASK_LLM else relationship_pre.parent_note_id
        relationship_service.attach_parent(note, parent_note_id)

    if candidates:
        location_service.attach_location(note, llm_fields.location)

    log_service_step(
        "consolidated enrichment applied",
        note_id=note.id,
        deadline_at=deadline_at,
        estimated_duration_minutes=duration,
        repeat_cycle=repeat_source.repeat_cycle,
        parent_note_id=note.parent_note_id,
        location_id=note.location_id,
    )
