"""Coordinates the full capture workflow."""

from schemas import CaptureResult
from services import (
    classification_service,
    command_service,
    gps_service,
    location_service,
    note_service,
    recording_service,
    relationship_service,
    urgency_service,
)
from services.service_logger import log_service_call, log_service_step


@log_service_call
def process_note_text(text: str) -> CaptureResult:
    text = text.strip()
    if not text:
        log_service_step("empty text ignored")
        return CaptureResult(text="", category=None, saved=False)

    command = command_service.detect_command(text)
    log_service_step("command detected", command=command.type.value, location_name=command.location_name)
    if command.type == command_service.CommandType.SAVE_LOCATION:
        if command.location_name is None:
            return CaptureResult(
                text=text,
                category=None,
                saved=False,
                command_processed=True,
                command_type=command.type.value,
                message="Could not identify the location name.",
            )

        coordinates = gps_service.get_current_coordinates()
        location = location_service.save_current_location(
            command.location_name,
            coordinates.latitude,
            coordinates.longitude,
        )
        return CaptureResult(
            text=text,
            category=None,
            saved=False,
            command_processed=True,
            command_type=command.type.value,
            location_id=location.id,
            location_name=location.name,
            location_latitude=location.latitude,
            location_longitude=location.longitude,
            message=f"Saved location '{location.name}'.",
        )

    note_id, created_at = note_service.save(text)
    log_service_step("note saved", note_id=note_id)
    note = note_service.get_by_id(note_id)
    if note is None:
        return CaptureResult(text=text, category=None, saved=False)

    try:
        note = relationship_service.apply_relationship(note)
    except Exception as exc:
        log_service_step("relationship failed", note_id=note_id, error=repr(exc))

    category = note.category
    try:
        category = classification_service.classify_text(note.text)
        note_service.update_category(note_id, category)
        note.category = category
    except Exception as exc:
        log_service_step("classification failed", note_id=note_id, error=repr(exc))

    urgency = urgency_service.UrgencyResult(
        deadline_at=note.deadline_at,
        importance_score=note.importance_score,
        urgency_score=note.urgency_score,
        rank_score=note.rank_score,
        urgency_reason=note.urgency_reason,
    )
    try:
        urgency = urgency_service.apply_urgency(note)
    except Exception as exc:
        log_service_step("urgency failed", note_id=note_id, error=repr(exc))

    try:
        location_service.apply_location(note)
    except Exception as exc:
        log_service_step("location failed", note_id=note_id, error=repr(exc))

    return CaptureResult(
        id=note_id,
        text=text,
        category=category,
        created_at=created_at,
        status=note.status,
        deadline_at=urgency.deadline_at,
        importance_score=urgency.importance_score,
        urgency_score=urgency.urgency_score,
        rank_score=urgency.rank_score,
        urgency_reason=urgency.urgency_reason,
        location_id=note.location_id,
        location_name=note.location_name,
        location_latitude=note.location_latitude,
        location_longitude=note.location_longitude,
        saved=True,
        command_processed=True,
        command_type=command.type.value,
    )


@log_service_call
def stop_and_save() -> CaptureResult:
    """Stop the active recording, transcribe, process, and save."""
    text = recording_service.stop_and_transcribe().strip()
    if not text:
        return CaptureResult(text="", category=None, saved=False)
    return process_note_text(text)


@log_service_call
def process_text(raw: str) -> CaptureResult:
    """Process plain-text input through the full note pipeline."""
    return process_note_text(raw)
