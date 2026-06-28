"""Stores named places and links notes to relevant places."""

import numpy as np

from database import delete_location, get_all_locations, update_note_location, upsert_location
from models import Location, Note
from services import model_service
from services.llm_utils import extract_json_object
from services.service_logger import log_service_call, log_service_step

_LOCATION_CONTEXT_PHRASES = [
    "when i get to",
    "when i am at",
    "once i get to",
    "once i am at",
    "at",
    "near",
    "in",
]

_MAX_LLM_CANDIDATES = 5
_context_embeddings = None


def _cosine_similarity(a, b) -> float:
    a = np.asarray(a)
    b = np.asarray(b)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        return 0.0
    return float(np.dot(a, b) / denominator)


@log_service_call
def save_current_location(name: str, latitude: float, longitude: float) -> Location:
    location_name = name.strip()
    log_service_step(
        "saving current location",
        name=location_name,
        latitude=latitude,
        longitude=longitude,
    )
    return upsert_location(location_name, latitude, longitude)


@log_service_call
def get_locations() -> list[Location]:
    locations = get_all_locations()
    log_service_step("loaded locations", count=len(locations))
    return locations


@log_service_call
def delete_saved_location(location_id: int) -> bool:
    deleted = delete_location(location_id)
    log_service_step("deleted location", location_id=location_id, deleted=deleted)
    return deleted


@log_service_call
def apply_location(note: Note) -> Location | None:
    location = find_relevant_location(note.text)
    if location is None:
        log_service_step("no location matched", note_id=note.id)
        return None

    log_service_step(
        "attaching location to note",
        note_id=note.id,
        location_id=location.id,
        location_name=location.name,
    )
    update_note_location(note.id, location.id)
    note.location_id = location.id
    note.location_name = location.name
    note.location_latitude = location.latitude
    note.location_longitude = location.longitude
    return location


@log_service_call
def find_relevant_location(text: str) -> Location | None:
    locations = get_all_locations()
    log_service_step("loaded saved locations for matching", count=len(locations))
    if not locations:
        return None

    candidates = _rank_location_candidates(text, locations)
    if not candidates:
        return None

    llm_status = model_service.get_llm_config_status()
    if not llm_status["configured"]:
        log_service_step("llm unavailable; skipping location link", error=llm_status.get("error"))
        return None

    try:
        return _ask_llm_to_choose_location(text, candidates)
    except Exception as exc:
        log_service_step("llm location match failed", error=repr(exc))
        return None


@log_service_call
def warm_up() -> None:
    log_service_step(
        "warming location context embeddings",
        phrases=len(_LOCATION_CONTEXT_PHRASES),
    )
    _get_context_embeddings()


def _rank_location_candidates(text: str, locations: list[Location]) -> list[tuple[Location, float]]:
    model = model_service.get_sentence_model()
    text_embedding = model.encode(text)
    location_phrases = [
        phrase
        for location in locations
        for phrase in _phrases_for_location(location.name)
    ]
    if not location_phrases:
        return []

    phrase_embeddings = model.encode(location_phrases)
    scored = [
        (index, _cosine_similarity(text_embedding, embedding))
        for index, embedding in enumerate(phrase_embeddings)
    ]
    phrases_per_location = len(_LOCATION_CONTEXT_PHRASES)
    best_by_location: dict[int, float] = {}
    for phrase_index, score in scored:
        location_index = phrase_index // phrases_per_location
        best_by_location[location_index] = max(
            best_by_location.get(location_index, 0.0),
            score,
        )

    ranked = sorted(
        (
            (locations[location_index], score)
            for location_index, score in best_by_location.items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:_MAX_LLM_CANDIDATES]
    log_service_step(
        "embedding ranked location candidates",
        candidates=[{"id": location.id, "name": location.name, "score": score} for location, score in ranked],
    )
    return ranked


def _ask_llm_to_choose_location(
    text: str,
    candidates: list[tuple[Location, float]],
) -> Location | None:
    candidate_lines = "\n".join(
        f"- id: {location.id}, name: {location.name}, embedding_score: {score:.3f}"
        for location, score in candidates
    )
    log_service_step("using llm location selection", candidates=len(candidates))
    prompt = f"""Return one JSON object only. Do not explain, do not use markdown.

Choose whether this note should be attached to one saved location.

JSON shape:
{{"location_id":null,"reason":"short reason"}}

Rules:
- Choose a location only if the note clearly refers to that place by name, context, or natural wording.
- If no saved location is relevant, return location_id as null.
- location_id must be one of the candidate ids or null.

Note: {text}
Saved location candidates:
{candidate_lines}
JSON:"""
    raw_text = model_service.generate_llm(prompt, max_tokens=160, json_mode=True)
    parsed = extract_json_object(raw_text)
    selected_id = parsed.get("location_id")
    reason = str(parsed.get("reason") or "").strip() or None
    log_service_step("llm selected location", location_id=selected_id, reason=reason)
    if selected_id is None:
        return None

    try:
        selected_id = int(selected_id)
    except (TypeError, ValueError):
        return None

    for location, _score in candidates:
        if location.id == selected_id:
            return location
    return None


def _phrases_for_location(location_name: str) -> list[str]:
    return [f"{phrase} {location_name}" for phrase in _LOCATION_CONTEXT_PHRASES]


def _get_context_embeddings():
    global _context_embeddings
    if _context_embeddings is None:
        _context_embeddings = model_service.get_sentence_model().encode(
            _LOCATION_CONTEXT_PHRASES
        )
    return _context_embeddings
