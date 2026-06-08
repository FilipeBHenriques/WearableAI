"""Coordinates the full capture workflow.

This is the only place that knows the sequence:
  record → transcribe → categorize → save → return result

Routes call this service and return whatever it gives back.
They do not know about Whisper, SQLite, or categorization rules.
"""

from schemas import CaptureResult
from services import note_service, organizer_service, recording_service


def stop_and_save() -> CaptureResult:
    """Stop the active recording, transcribe, categorize, and save."""
    text = recording_service.stop_and_transcribe().strip()
    if not text:
        return CaptureResult(text="", category=None, saved=False)

    category = organizer_service.categorize(text)
    note_service.save(text, category)
    return CaptureResult(text=text, category=category, saved=True)


def process_text(raw: str) -> CaptureResult:
    """Categorize and save a plain-text input (no recording needed)."""
    text = raw.strip()
    if not text:
        return CaptureResult(text="", category=None, saved=False)

    category = organizer_service.categorize(text)
    note_service.save(text, category)
    return CaptureResult(text=text, category=category, saved=True)
