"""Voice/text capture entrypoints — delegates processing to note_pipeline.

Recording I/O lives in recording_service. Job queue lives in capture_queue_service.
Command detection, save, and enrichment order live in note_pipeline.
"""

from schemas import CaptureResult
from services import note_pipeline, recording_service
from services.service_logger import log_service_call


@log_service_call
def save_raw_note_text(text: str) -> CaptureResult:
    return note_pipeline.run_intake(text)


@log_service_call
def enrich_note(note_id: int) -> CaptureResult:
    return note_pipeline.run_enrich(note_id)


@log_service_call
def process_note_text(text: str) -> CaptureResult:
    return note_pipeline.process_text(text)


@log_service_call
def stop_and_save() -> CaptureResult:
    """Stop the active recording, transcribe, and run the note pipeline."""
    text = recording_service.stop_and_transcribe().strip()
    if not text:
        return CaptureResult(text="", category=None, saved=False)
    return note_pipeline.process_text(text)


@log_service_call
def process_text(raw: str) -> CaptureResult:
    return note_pipeline.process_text(raw)
