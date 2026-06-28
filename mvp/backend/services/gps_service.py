"""Provides the current GPS coordinates.

For the MVP this is mocked by environment variables. The wearable GPS can
replace this module later without changing the capture pipeline.
"""

import os
from dataclasses import dataclass

from services.service_logger import log_service_call


DEFAULT_LATITUDE = 38.7223
DEFAULT_LONGITUDE = -9.1393


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float


def _read_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        print(f"[gps] invalid {name}={raw_value!r}; using default", flush=True)
        return default


@log_service_call
def get_current_coordinates() -> Coordinates:
    return Coordinates(
        latitude=_read_float_env("MOCK_GPS_LAT", DEFAULT_LATITUDE),
        longitude=_read_float_env("MOCK_GPS_LON", DEFAULT_LONGITUDE),
    )
