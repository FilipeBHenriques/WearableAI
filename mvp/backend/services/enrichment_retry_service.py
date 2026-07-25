"""Periodically retries enrichment for notes that never finished — e.g. Ollama was
down when the note was first processed, or the process restarted mid-enrichment.

Mirrors gps_service's background-ticker pattern.
"""

from __future__ import annotations

import threading
import time

from services import note_pipeline, note_service
from services.service_logger import log_service_call, log_service_step

RETRY_INTERVAL_SECONDS = 300.0

_lock = threading.Lock()
_ticker_started = False


@log_service_call
def retry_pending_enrichment() -> list[int]:
    note_ids = note_service.get_ids_needing_enrichment()
    for note_id in note_ids:
        log_service_step("retrying enrichment", note_id=note_id)
        note_pipeline.run_enrich(note_id)
    return note_ids


def _ticker_loop() -> None:
    while True:
        try:
            retry_pending_enrichment()
        except Exception as exc:
            log_service_step("enrichment retry ticker failed", error=repr(exc))
        time.sleep(RETRY_INTERVAL_SECONDS)


@log_service_call
def start_background_ticker() -> None:
    global _ticker_started
    with _lock:
        if _ticker_started:
            return
        _ticker_started = True
    thread = threading.Thread(target=_ticker_loop, daemon=True, name="enrichment-retry-ticker")
    thread.start()
    log_service_step("enrichment retry ticker started", interval_seconds=RETRY_INTERVAL_SECONDS)
