"""In-process pub/sub for SSE UI updates (single-user, local)."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from services.service_logger import log_service_step

_subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
_lock = threading.Lock()


def subscribe() -> asyncio.Queue:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    with _lock:
        _subscribers.append((loop, queue))
    log_service_step("subscriber connected", count=len(_subscribers))
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    with _lock:
        _subscribers[:] = [(loop, q) for loop, q in _subscribers if q is not queue]
    log_service_step("subscriber disconnected", count=len(_subscribers))


def _safe_put(queue: asyncio.Queue, message: dict[str, Any]) -> None:
    try:
        queue.put_nowait(message)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass


def publish(event_type: str, payload: Any = None) -> None:
    message = {"type": event_type, "payload": payload if payload is not None else {}}
    with _lock:
        subscribers = list(_subscribers)
    if not subscribers:
        return
    for loop, queue in subscribers:
        try:
            loop.call_soon_threadsafe(_safe_put, queue, message)
        except RuntimeError:
            # Loop closed (server shutting down / subscriber gone).
            continue
