"""Coordinates the full capture workflow."""

from schemas import CaptureResult
from services import (
    classification_service,
    note_service,
    recording_service,
    relationship_service,
)


def process_note_text(text: str) -> CaptureResult:
    text = text.strip()
    if not text:
        return CaptureResult(text="", category=None, saved=False)

    note_id, created_at = note_service.save(text)
    note = note_service.get_by_id(note_id)
    if note is None:
        return CaptureResult(text=text, category=None, saved=False)

    note = relationship_service.apply_relationship(note)
    category = classification_service.classify_text(note.text)
    note_service.update_category(note_id, category)

    return CaptureResult(
        id=note_id,
        text=text,
        category=category,
        created_at=created_at,
        saved=True,
    )


def stop_and_save() -> CaptureResult:
    """Stop the active recording, transcribe, process, and save."""
    text = recording_service.stop_and_transcribe().strip()
    if not text:
        return CaptureResult(text="", category=None, saved=False)
    return process_note_text(text)


def process_text(raw: str) -> CaptureResult:
    """Process plain-text input through the full note pipeline."""
    return process_note_text(raw)
