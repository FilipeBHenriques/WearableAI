"""Owns note processing order: intake, then enrich.

Domain services do one job each. This module is the only place that decides order.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from models import Note
from schemas import CaptureResult
from services import (
    classification_service,
    command_service,
    estimate_duration_service,
    event_bus,
    gps_service,
    location_service,
    note_service,
    recurrence_service,
    relationship_service,
    urgency_service,
)
from services.command_service import CommandType
from services.service_logger import log_service_call, log_service_step


class PipelineStep(str, Enum):
    DETECT_COMMAND = "detect_command"
    SAVE_NOTE = "save_note"
    RELATIONSHIP = "relationship"
    CLASSIFICATION = "classification"
    URGENCY = "urgency"
    ESTIMATE_DURATION = "estimate_duration"
    LOCATION = "location"
    RECURRENCE = "recurrence"


class PipelineStage(str, Enum):
    ENRICHED = "enriched"


class ErrorPolicy(str, Enum):
    FAIL_FAST = "fail_fast"
    CONTINUE = "continue"


@dataclass
class PipelineContext:
    text: str
    note: Note | None = None
    command_type: CommandType | None = None
    stopped: bool = False
    saved: bool = False
    message: str | None = None
    location_id: int | None = None
    location_name: str | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None


StepFn = Callable[[PipelineContext], None]


@dataclass(frozen=True)
class Step:
    id: PipelineStep
    run: StepFn


def _audio_url(note: Note | None) -> str | None:
    if note is None or not note.audio_path:
        return None
    return f"/api/notes/{note.id}/audio"


def _reload_note(ctx: PipelineContext) -> None:
    if ctx.note is None:
        return
    refreshed = note_service.get_by_id(ctx.note.id)
    if refreshed is not None:
        ctx.note = refreshed


def _require_note(ctx: PipelineContext) -> Note | None:
    return ctx.note


def _empty_result(text: str = "") -> CaptureResult:
    return CaptureResult(text=text, category=None, saved=False)


def to_capture_result(ctx: PipelineContext) -> CaptureResult:
    command_value = ctx.command_type.value if ctx.command_type is not None else None

    if ctx.stopped and not ctx.saved:
        return CaptureResult(
            text=ctx.text,
            category=None,
            saved=False,
            command_processed=True,
            command_type=command_value,
            location_id=ctx.location_id,
            location_name=ctx.location_name,
            location_latitude=ctx.location_latitude,
            location_longitude=ctx.location_longitude,
            message=ctx.message,
        )

    note = ctx.note
    if note is None:
        return _empty_result(ctx.text)

    return CaptureResult(
        id=note.id,
        text=note.text,
        category=note.category,
        created_at=note.created_at,
        status=note.status,
        deadline_at=note.deadline_at,
        urgency_score=note.urgency_score,
        rank_score=note.rank_score,
        urgency_reason=note.urgency_reason,
        location_id=note.location_id,
        location_name=note.location_name,
        location_latitude=note.location_latitude,
        location_longitude=note.location_longitude,
        repeat_cycle=note.repeat_cycle,
        repeat_days=note.repeat_days,
        repeat_months=note.repeat_months,
        repeat_time=note.repeat_time,
        is_repeating=recurrence_service.is_repeating(note),
        is_due_today=recurrence_service.is_due_on(note),
        completed_today=recurrence_service.completed_on(note),
        repeat_display=recurrence_service.repeat_display(note),
        estimated_duration_minutes=note.estimated_duration_minutes,
        audio_path=note.audio_path,
        audio_url=_audio_url(note),
        saved=True,
        command_processed=True,
        command_type=command_value or CommandType.TAKE_NOTE.value,
        message=ctx.message,
    )


def _publish_enriched(note_id: int) -> None:
    event_bus.publish(
        "notes_changed",
        {"note_id": note_id, "stage": PipelineStage.ENRICHED.value},
    )


# --- Intake ---


def _step_detect_command(ctx: PipelineContext) -> None:
    command = command_service.detect_command(ctx.text)
    ctx.command_type = command.type
    log_service_step(
        "command detected",
        command=command.type.value,
        location_name=command.location_name,
    )

    if command.type is not CommandType.SAVE_LOCATION:
        return

    if command.location_name is None:
        ctx.stopped = True
        ctx.message = "Could not identify the location name."
        return

    coordinates = gps_service.get_current_coordinates()
    location = location_service.save_current_location(
        command.location_name,
        coordinates.latitude,
        coordinates.longitude,
    )
    ctx.stopped = True
    ctx.location_id = location.id
    ctx.location_name = location.name
    ctx.location_latitude = location.latitude
    ctx.location_longitude = location.longitude
    ctx.message = f"Saved location '{location.name}'."


def _step_save_note(ctx: PipelineContext) -> None:
    note_id, _created_at = note_service.save(ctx.text)
    note = note_service.get_by_id(note_id)
    if note is None:
        ctx.stopped = True
        return

    ctx.note = note
    ctx.saved = True
    ctx.command_type = ctx.command_type or CommandType.TAKE_NOTE
    log_service_step("note saved", note_id=note_id)


# --- Enrich ---


def _step_relationship(ctx: PipelineContext) -> None:
    note = _require_note(ctx)
    if note is None:
        return
    ctx.note = relationship_service.apply_relationship(note)
    _reload_note(ctx)


def _step_classification(ctx: PipelineContext) -> None:
    note = _require_note(ctx)
    if note is None:
        return
    category = classification_service.classify_text(note.text)
    note_service.update_category(note.id, category)
    note.category = category
    _reload_note(ctx)


def _step_urgency(ctx: PipelineContext) -> None:
    note = _require_note(ctx)
    if note is None:
        return
    urgency_service.apply_urgency(note)
    _reload_note(ctx)


def _step_estimate_duration(ctx: PipelineContext) -> None:
    note = _require_note(ctx)
    if note is None or not note.deadline_at:
        return

    estimate_duration_service.apply_estimate(note)
    _reload_note(ctx)
    if ctx.note is not None and ctx.note.estimated_duration_minutes is not None:
        urgency_service.refresh_scores(ctx.note)
        _reload_note(ctx)


def _step_location(ctx: PipelineContext) -> None:
    note = _require_note(ctx)
    if note is None:
        return
    location_service.apply_location(note)
    _reload_note(ctx)


def _step_recurrence(ctx: PipelineContext) -> None:
    note = _require_note(ctx)
    if note is None:
        return

    recurrence = recurrence_service.analyze_text(note.text)
    if recurrence.repeat_cycle is None:
        return

    note_service.update_recurrence(
        note.id,
        recurrence.repeat_cycle,
        recurrence.repeat_days,
        recurrence.repeat_months,
        recurrence.repeat_time,
    )
    note_service.update_category(note.id, "Goal")
    _reload_note(ctx)


INTAKE_STEPS: tuple[Step, ...] = (
    Step(PipelineStep.DETECT_COMMAND, _step_detect_command),
    Step(PipelineStep.SAVE_NOTE, _step_save_note),
)

ENRICH_STEPS: tuple[Step, ...] = (
    Step(PipelineStep.RELATIONSHIP, _step_relationship),
    Step(PipelineStep.CLASSIFICATION, _step_classification),
    Step(PipelineStep.URGENCY, _step_urgency),
    Step(PipelineStep.ESTIMATE_DURATION, _step_estimate_duration),
    Step(PipelineStep.LOCATION, _step_location),
    Step(PipelineStep.RECURRENCE, _step_recurrence),
)


def _run_steps(
    steps: tuple[Step, ...],
    ctx: PipelineContext,
    *,
    error_policy: ErrorPolicy,
) -> None:
    for step in steps:
        if ctx.stopped:
            return

        if error_policy is ErrorPolicy.FAIL_FAST:
            step.run(ctx)
            continue

        try:
            step.run(ctx)
        except Exception as exc:
            note_id = ctx.note.id if ctx.note is not None else None
            log_service_step(f"{step.id.value} failed", note_id=note_id, error=repr(exc))


def _new_context(text: str) -> PipelineContext | None:
    cleaned = text.strip()
    if not cleaned:
        log_service_step("empty text ignored")
        return None
    return PipelineContext(text=cleaned)


@log_service_call
def run_intake(text: str) -> CaptureResult:
    """Command detection + raw note save (no enrichment)."""
    ctx = _new_context(text)
    if ctx is None:
        return _empty_result()

    _run_steps(INTAKE_STEPS, ctx, error_policy=ErrorPolicy.FAIL_FAST)
    return to_capture_result(ctx)


@log_service_call
def run_enrich(note_id: int) -> CaptureResult:
    """Run enrich steps on an existing note."""
    note = note_service.get_by_id(note_id)
    if note is None:
        return _empty_result()

    ctx = PipelineContext(
        text=note.text,
        note=note,
        saved=True,
        command_type=CommandType.TAKE_NOTE,
    )
    _run_steps(ENRICH_STEPS, ctx, error_policy=ErrorPolicy.CONTINUE)
    _reload_note(ctx)
    _publish_enriched(note_id)
    return to_capture_result(ctx)


@log_service_call
def process_text(text: str) -> CaptureResult:
    """Full pipeline: intake then enrich when a note was saved."""
    ctx = _new_context(text)
    if ctx is None:
        return _empty_result()

    _run_steps(INTAKE_STEPS, ctx, error_policy=ErrorPolicy.FAIL_FAST)
    if ctx.stopped or ctx.note is None:
        return to_capture_result(ctx)

    _run_steps(ENRICH_STEPS, ctx, error_policy=ErrorPolicy.CONTINUE)
    _reload_note(ctx)
    if ctx.note is not None:
        _publish_enriched(ctx.note.id)
    return to_capture_result(ctx)
