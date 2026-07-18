"""Shared service-call logging helpers."""

import inspect
import os
from dataclasses import is_dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_DIM = "\033[2m"
_SERVICE_COLORS = [
    "\033[36m",
    "\033[35m",
    "\033[34m",
    "\033[32m",
    "\033[33m",
]
_LOG_ENABLED = os.getenv("SERVICE_LOG_ENABLED", "1").lower() not in {"0", "false", "no"}


class ServiceName(str, Enum):
    CAPTURE = "capture_service"
    CAPTURE_QUEUE = "capture_queue_service"
    NOTE = "note_service"
    RECORDING = "recording_service"
    COMMAND = "command_service"
    CLASSIFICATION = "classification_service"
    RELATIONSHIP = "relationship_service"
    URGENCY = "urgency_service"
    RECURRENCE = "recurrence_service"
    LOCATION = "location_service"
    GPS = "gps_service"
    MODEL = "model_service"
    ESTIMATE_DURATION = "estimate_duration_service"
    FIXUP = "fixup_service"
    EVENT_BUS = "event_bus"
    NOTE_PIPELINE = "note_pipeline"


# None = all services when master is on.
# Example: {ServiceName.CAPTURE, ServiceName.URGENCY}
SERVICE_LOG_ALLOWLIST: set[ServiceName] | None = None

_SERVICE_BY_VALUE = {member.value: member for member in ServiceName}


def _short_repr(value: Any, max_length: int = 500) -> str:
    rendered = _safe_repr(value)
    if len(rendered) <= max_length:
        return rendered
    return f"{rendered[: max_length - 3]}..."


def _safe_repr(value: Any) -> str:
    if value is None or isinstance(value, (bool, int, float, str)):
        return repr(value)
    if is_dataclass(value):
        return repr(value)
    if hasattr(value, "model_dump"):
        return repr(value)
    if isinstance(value, dict):
        items = list(value.items())[:8]
        body = ", ".join(f"{key!r}: {_short_repr(item, 120)}" for key, item in items)
        suffix = ", ..." if len(value) > len(items) else ""
        return f"{{{body}{suffix}}}"
    if isinstance(value, (list, tuple, set, frozenset)):
        values = list(value)
        body = ", ".join(_short_repr(item, 120) for item in values[:8])
        suffix = ", ..." if len(values) > 8 else ""
        opener, closer = ("[", "]") if isinstance(value, list) else ("(", ")")
        return f"{opener}{body}{suffix}{closer}"
    if hasattr(value, "shape") and hasattr(value, "dtype"):
        return f"<{type(value).__name__} shape={value.shape} dtype={value.dtype}>"
    return f"<{type(value).__module__}.{type(value).__name__}>"


def _service_label(service_name: str) -> str:
    color = _SERVICE_COLORS[sum(ord(char) for char in service_name) % len(_SERVICE_COLORS)]
    return f"{color}{_BOLD}[ {service_name} ]{_RESET}"


def _resolve_service(module_stem: str) -> ServiceName | None:
    return _SERVICE_BY_VALUE.get(module_stem)


def _should_log(service: ServiceName | None) -> bool:
    if not _LOG_ENABLED:
        return False
    if SERVICE_LOG_ALLOWLIST is None:
        return True
    if service is None:
        return False
    return service in SERVICE_LOG_ALLOWLIST


def _caller_module_stem() -> str:
    frame = inspect.currentframe()
    if frame is None or frame.f_back is None or frame.f_back.f_back is None:
        return "service"
    module_name = frame.f_back.f_back.f_globals.get("__name__", "service")
    return str(module_name).split(".")[-1]


def log_service_step(message: str, **fields: Any) -> None:
    module_stem = _caller_module_stem()
    service = _resolve_service(module_stem)
    if not _should_log(service):
        return

    field_text = " ".join(
        f"{key}={_short_repr(value, 160)}" for key, value in fields.items()
    )
    suffix = f" {field_text}" if field_text else ""
    print(f"{_service_label(module_stem)} {_DIM}step{_RESET} {message}{suffix}", flush=True)


def log_service_call(func: F) -> F:
    """Log service name, function name, and return value."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        module_stem = func.__module__.split(".")[-1]
        service = _resolve_service(module_stem)
        if not _should_log(service):
            return func(*args, **kwargs)

        label = _service_label(module_stem)
        print(f"{label} {_DIM}start{_RESET} {func.__name__}", flush=True)
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            print(
                f"{label} {func.__name__} {_RED}raised={exc!r}{_RESET}",
                flush=True,
            )
            raise

        print(
            f"{label} {func.__name__} returned={_short_repr(result)}",
            flush=True,
        )
        return result

    return wrapper  # type: ignore[return-value]
