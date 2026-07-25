"""Owns the microphone stream and Moonshine transcription.

start_recording() / stop_and_transcribe() are the only public interface.
Everything else is module-level state that only this file touches.
"""

import threading
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile
import sounddevice as sd

from feature_flags import AUDIO_SAVE_ENABLED
from paths import AUDIO_DIR, MEDIA_DIR
from services import model_service
from services.service_logger import log_service_call, log_service_step

SAMPLE_RATE = 16_000

_frames: list[np.ndarray] = []
_stream: sd.InputStream | None = None
_active_job_id: int | None = None
_frames_lock = threading.Lock()


def _transcribe_audio(audio: np.ndarray) -> str:
    if audio.size == 0:
        return ""

    log_service_step("using moonshine transcription")
    result = model_service.get_transcription_model()({"array": audio, "sampling_rate": SAMPLE_RATE})
    return str(result.get("text", "")).strip()


def resolve_audio_path(relative_path: str) -> Path:
    return (MEDIA_DIR / relative_path).resolve()


@log_service_call
def save_note_audio(audio: np.ndarray, note_id: int) -> str | None:
    if not AUDIO_SAVE_ENABLED or audio.size == 0:
        return None

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    relative = f"audio/{note_id}.wav"
    absolute = resolve_audio_path(relative)
    wavfile.write(str(absolute), SAMPLE_RATE, (audio * 32_767).astype(np.int16))
    log_service_step("saved note audio", note_id=note_id, path=relative)
    return relative


@log_service_call
def delete_audio_file(relative_path: str | None) -> None:
    if not relative_path:
        return
    absolute = resolve_audio_path(relative_path)
    try:
        if absolute.is_file() and MEDIA_DIR in absolute.parents:
            absolute.unlink()
            log_service_step("deleted audio file", path=relative_path)
    except OSError as exc:
        log_service_step("audio delete failed", path=relative_path, error=repr(exc))


@log_service_call
def start_recording(job_id: int | None = None) -> None:
    global _active_job_id, _frames, _stream
    with _frames_lock:
        _frames = []
    _active_job_id = job_id
    log_service_step("starting microphone stream", sample_rate=SAMPLE_RATE, job_id=job_id)

    def _callback(indata, _frames_count, _time, _status):
        with _frames_lock:
            _frames.append(indata.copy())

    _stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        callback=_callback,
    )
    _stream.start()


def active_job_id() -> int | None:
    return _active_job_id


def snapshot_audio() -> np.ndarray:
    with _frames_lock:
        if not _frames:
            return np.array([], dtype=np.float32)
        return np.concatenate(_frames).flatten()


@log_service_call
def stop_and_get_audio() -> np.ndarray:
    global _active_job_id, _stream

    if _stream is None:
        log_service_step("no active stream")
        _active_job_id = None
        return np.array([], dtype=np.float32)

    _stream.stop()
    _stream.close()
    _stream = None
    log_service_step("microphone stream stopped", frames=len(_frames), job_id=_active_job_id)
    _active_job_id = None
    return snapshot_audio()


@log_service_call
def transcribe_audio(audio: np.ndarray) -> str:
    return _transcribe_audio(audio)


@log_service_call
def stop_and_transcribe() -> str:
    audio = stop_and_get_audio()
    if audio.size == 0:
        log_service_step("no audio frames captured")
        return ""
    return _transcribe_audio(audio)
