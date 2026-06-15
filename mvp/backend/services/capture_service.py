"""Coordinates the full capture workflow.

Save and categorize are separate steps so the client can show the note
immediately, then call categorize when ready.
"""

from schemas import CaptureResult
from services import note_service, recording_service


def save_text(text: str) -> CaptureResult:
    text = text.strip()
    if not text:
        return CaptureResult(text="", category=None, saved=False)

    note_id, created_at = note_service.save(text)
    return CaptureResult(
        id=note_id,
        text=text,
        category=note_service.PENDING_CATEGORY,
        created_at=created_at,
        saved=True,
    )


def stop_and_save() -> CaptureResult:
    """Stop the active recording, transcribe, and save."""
    text = recording_service.stop_and_transcribe().strip()
    if not text:
        return CaptureResult(text="", category=None, saved=False)
    return save_text(text)


def process_text(raw: str) -> CaptureResult:
    """Save plain-text input without categorizing."""
    return save_text(raw)
