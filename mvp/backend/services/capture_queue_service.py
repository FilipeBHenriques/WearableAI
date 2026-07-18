"""SQLite-backed voice capture job queue."""

from __future__ import annotations

import threading

import numpy as np

from database import (
    create_capture_job,
    get_active_capture_jobs,
    get_capture_job,
    update_capture_job,
)
from models import CaptureJob
from services import event_bus, fixup_service, note_pipeline, note_service, recording_service
from services.service_logger import log_service_call, log_service_step


def _serialize_job(job: CaptureJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "final_transcript": job.final_transcript,
        "note_id": job.note_id,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def serialize_job(job: CaptureJob) -> dict:
    return _serialize_job(job)


def _update_and_publish(job_id: int, **fields) -> CaptureJob | None:
    job = update_capture_job(job_id, **fields)
    if job is not None:
        event_bus.publish("capture_job", _serialize_job(job))
    return job


def _process_audio_job(job_id: int, audio: np.ndarray) -> None:
    try:
        if audio.size == 0:
            _update_and_publish(job_id, status="failed", error="No audio captured.")
            return

        final_text = recording_service.transcribe_audio(audio).strip()
        if not final_text:
            _update_and_publish(job_id, status="failed", error="Could not transcribe audio.")
            return

        final_text = fixup_service.fix_transcript(final_text)

        _update_and_publish(
            job_id,
            status="saved_raw",
            final_transcript=final_text,
        )
        raw_result = note_pipeline.run_intake(final_text)

        if raw_result.id is None:
            terminal_status = "ready" if raw_result.command_processed else "failed"
            _update_and_publish(
                job_id,
                status=terminal_status,
                error=None if raw_result.command_processed else raw_result.message or "Could not save note.",
            )
            return

        audio_path = recording_service.save_note_audio(audio, raw_result.id)
        if audio_path is not None:
            note_service.update_audio_path(raw_result.id, audio_path)

        _update_and_publish(job_id, status="saved_raw", note_id=raw_result.id)
        event_bus.publish("notes_changed", {"note_id": raw_result.id, "stage": "saved_raw"})
        _update_and_publish(job_id, status="enriching")
        note_pipeline.run_enrich(raw_result.id)
        _update_and_publish(job_id, status="ready")
        event_bus.publish("notes_changed", {"note_id": raw_result.id, "stage": "ready"})
    except Exception as exc:
        log_service_step("capture job failed", job_id=job_id, error=repr(exc))
        _update_and_publish(job_id, status="failed", error=repr(exc))


@log_service_call
def start_recording_job() -> CaptureJob:
    if recording_service.active_job_id() is not None:
        raise RuntimeError("A recording is already active.")

    job = create_capture_job("recording")
    recording_service.start_recording(job.id)
    event_bus.publish("capture_job", _serialize_job(job))
    return job


@log_service_call
def stop_recording_job() -> CaptureJob:
    job_id = recording_service.active_job_id()
    if job_id is None:
        raise RuntimeError("No recording is active.")

    audio = recording_service.stop_and_get_audio()
    job = _update_and_publish(job_id, status="transcribing")
    threading.Thread(
        target=_process_audio_job,
        args=(job_id, audio),
        daemon=True,
        name=f"capture-worker-{job_id}",
    ).start()
    if job is None:
        raise RuntimeError("Recording job was not found.")
    return job


@log_service_call
def active_jobs() -> list[CaptureJob]:
    return get_active_capture_jobs()


def get_job(job_id: int) -> CaptureJob | None:
    return get_capture_job(job_id)
