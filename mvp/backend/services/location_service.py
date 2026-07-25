"""Stores named places and links notes to relevant places.

Candidate ranking here is embedding-only. Picking a candidate (when the LLM
tie-break is needed) is folded into services.memory_extraction_service's single
consolidated per-note LLM call.
"""

import numpy as np

from database import delete_location, get_all_locations, update_note_location, upsert_location
from models import Location, Note
from services import event_bus, model_service
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

# Per-location cache of that location's phrase embeddings (e.g. "at gym", "near
# gym", ...). Keyed by location id; invalidated whenever that location's name
# changes or it is deleted, since the phrases are derived from the name.
_location_phrase_embeddings: dict[int, np.ndarray] = {}


def _invalidate_location_cache(location_id: int) -> None:
    _location_phrase_embeddings.pop(location_id, None)


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
    location = upsert_location(location_name, latitude, longitude)
    _invalidate_location_cache(location.id)
    event_bus.publish("locations_changed", {"location_id": location.id})
    return location


@log_service_call
def get_locations() -> list[Location]:
    locations = get_all_locations()
    log_service_step("loaded locations", count=len(locations))
    return locations


@log_service_call
def delete_saved_location(location_id: int) -> bool:
    deleted = delete_location(location_id)
    log_service_step("deleted location", location_id=location_id, deleted=deleted)
    if deleted:
        _invalidate_location_cache(location_id)
        event_bus.publish("locations_changed", {"location_id": location_id})
        event_bus.publish("notes_changed", {"reason": "location_deleted"})
    return deleted


def attach_location(note: Note, location: Location | None) -> Location | None:
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
def location_candidates(text: str) -> list[tuple[Location, float]]:
    """Embedding-ranked candidate locations (top matches by phrase similarity),
    or [] when there are no saved locations. Picking among them (when the LLM
    tie-break is needed) is done by memory_extraction_service."""
    locations = get_all_locations()
    log_service_step("loaded saved locations for matching", count=len(locations))
    if not locations:
        return []
    return _rank_location_candidates(text, locations)


def resolve_location(candidates: list[tuple[Location, float]], parsed_location_id) -> Location | None:
    """Turns a parsed `location_id` value from the consolidated LLM response
    into the matching candidate Location, or None."""
    if parsed_location_id is None:
        return None
    try:
        selected_id = int(parsed_location_id)
    except (TypeError, ValueError):
        return None
    for location, _score in candidates:
        if location.id == selected_id:
            return location
    return None


@log_service_call
def warm_up() -> None:
    log_service_step(
        "warming location context embeddings",
        phrases=len(_LOCATION_CONTEXT_PHRASES),
    )
    _get_context_embeddings()


def _phrase_embeddings_for(location: Location, model) -> np.ndarray:
    cached = _location_phrase_embeddings.get(location.id)
    if cached is not None:
        return cached
    embeddings = np.asarray(model.encode(_phrases_for_location(location.name)))
    _location_phrase_embeddings[location.id] = embeddings
    return embeddings


def _rank_location_candidates(text: str, locations: list[Location]) -> list[tuple[Location, float]]:
    if not locations:
        return []

    model = model_service.get_sentence_model()
    text_embedding = model.encode(text)

    best_by_location: dict[int, float] = {}
    for location in locations:
        phrase_embeddings = _phrase_embeddings_for(location, model)
        best_by_location[location.id] = max(
            (_cosine_similarity(text_embedding, embedding) for embedding in phrase_embeddings),
            default=0.0,
        )

    location_by_id = {location.id: location for location in locations}
    ranked = sorted(
        (
            (location_by_id[location_id], score)
            for location_id, score in best_by_location.items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:_MAX_LLM_CANDIDATES]
    log_service_step(
        "embedding ranked location candidates",
        candidates=[{"id": location.id, "name": location.name, "score": score} for location, score in ranked],
    )
    return ranked


def _phrases_for_location(location_name: str) -> list[str]:
    return [f"{phrase} {location_name}" for phrase in _LOCATION_CONTEXT_PHRASES]


def _get_context_embeddings():
    global _context_embeddings
    if _context_embeddings is None:
        _context_embeddings = model_service.get_sentence_model().encode(
            _LOCATION_CONTEXT_PHRASES
        )
    return _context_embeddings
