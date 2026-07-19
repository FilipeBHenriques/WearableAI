"""Mock GPS that wanders near saved locations and surfaces location reminders."""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import asdict, dataclass

from models import Location, Note
from services import event_bus, location_service, note_service, recurrence_service
from services.service_logger import log_service_call, log_service_step

DEFAULT_LATITUDE = 38.7223
DEFAULT_LONGITUDE = -9.1393
TICK_INTERVAL_SECONDS = 30.0
# ~50–150 meters of jitter at mid-latitudes.
_JITTER_METERS_MIN = 50.0
_JITTER_METERS_MAX = 150.0
_METERS_PER_DEG_LAT = 111_320.0

_lock = threading.Lock()
_rng = random.Random()
_active_location: Location | None = None
_last_tick_monotonic = 0.0
_ticker_started = False


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float


_current = Coordinates(latitude=DEFAULT_LATITUDE, longitude=DEFAULT_LONGITUDE)


def _meters_to_deg(lat: float, east_m: float, north_m: float) -> tuple[float, float]:
    lat_offset = north_m / _METERS_PER_DEG_LAT
    lon_scale = _METERS_PER_DEG_LAT * max(0.2, math.cos(math.radians(lat)))
    lon_offset = east_m / lon_scale
    return lat_offset, lon_offset


def _jitter_around(location: Location) -> Coordinates:
    distance = _rng.uniform(_JITTER_METERS_MIN, _JITTER_METERS_MAX)
    bearing = _rng.uniform(0, 2 * math.pi)
    east = distance * math.sin(bearing)
    north = distance * math.cos(bearing)
    d_lat, d_lon = _meters_to_deg(location.latitude, east, north)
    return Coordinates(
        latitude=location.latitude + d_lat,
        longitude=location.longitude + d_lon,
    )


def _note_is_suggestable(note: Note) -> bool:
    if recurrence_service.is_repeating(note):
        return recurrence_service.is_available_today(note)
    return note.status == note_service.ACTIVE_STATUS


def _serialize_suggestion_note(note: Note) -> dict:
    return {
        "id": note.id,
        "text": note.text,
        "category": note.category,
        "location_id": note.location_id,
        "location_name": note.location_name,
        "urgency_score": note.urgency_score,
        "rank_score": note.rank_score,
        "deadline_at": note.deadline_at,
        "status": note.status,
    }


def get_location_suggestions(location_id: int | None = None) -> list[Note]:
    target_id = location_id
    with _lock:
        if target_id is None and _active_location is not None:
            target_id = _active_location.id
    if target_id is None:
        return []

    return [
        note
        for note in note_service.get_all_flat()
        if note.location_id == target_id and _note_is_suggestable(note)
    ]


def _publish_suggestions() -> None:
    with _lock:
        location = _active_location
        coords = _current
    if location is None:
        event_bus.publish(
            "gps_suggestions",
            {
                "location": None,
                "coordinates": asdict(coords),
                "notes": [],
            },
        )
        return

    notes = get_location_suggestions(location.id)
    event_bus.publish(
        "gps_suggestions",
        {
            "location": {
                "id": location.id,
                "name": location.name,
                "latitude": location.latitude,
                "longitude": location.longitude,
            },
            "coordinates": asdict(coords),
            "notes": [_serialize_suggestion_note(note) for note in notes],
        },
    )


@log_service_call
def tick(force: bool = False) -> Coordinates:
    """Move mock GPS near a random saved location (or keep defaults)."""
    global _current, _active_location, _last_tick_monotonic

    now = time.monotonic()
    with _lock:
        if not force and (now - _last_tick_monotonic) < TICK_INTERVAL_SECONDS:
            return _current

    locations = location_service.get_locations()
    if locations:
        chosen = _rng.choice(locations)
        coords = _jitter_around(chosen)
        with _lock:
            _active_location = chosen
            _current = coords
            _last_tick_monotonic = now
        log_service_step(
            "gps tick near location",
            location_id=chosen.id,
            location_name=chosen.name,
            latitude=coords.latitude,
            longitude=coords.longitude,
        )
    else:
        with _lock:
            _active_location = None
            _current = Coordinates(latitude=DEFAULT_LATITUDE, longitude=DEFAULT_LONGITUDE)
            _last_tick_monotonic = now
        log_service_step("gps tick default", latitude=DEFAULT_LATITUDE, longitude=DEFAULT_LONGITUDE)

    _publish_suggestions()
    with _lock:
        return _current


@log_service_call
def get_current_coordinates() -> Coordinates:
    return tick(force=False)


def get_active_location() -> Location | None:
    with _lock:
        return _active_location


def set_rng_seed(seed: int) -> None:
    """Test helper for deterministic jitter / location picks."""
    global _rng
    _rng = random.Random(seed)


def reset_state() -> None:
    """Test helper."""
    global _current, _active_location, _last_tick_monotonic
    with _lock:
        _current = Coordinates(latitude=DEFAULT_LATITUDE, longitude=DEFAULT_LONGITUDE)
        _active_location = None
        _last_tick_monotonic = 0.0


def _ticker_loop() -> None:
    while True:
        try:
            tick(force=True)
        except Exception as exc:
            log_service_step("gps ticker failed", error=repr(exc))
        time.sleep(TICK_INTERVAL_SECONDS)


@log_service_call
def start_background_ticker() -> None:
    global _ticker_started
    with _lock:
        if _ticker_started:
            return
        _ticker_started = True
    thread = threading.Thread(target=_ticker_loop, daemon=True, name="gps-ticker")
    thread.start()
    log_service_step("gps ticker started", interval_seconds=TICK_INTERVAL_SECONDS)
    tick(force=True)
