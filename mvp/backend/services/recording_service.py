"""Owns the microphone stream and Whisper transcription.

start_recording() / stop_and_transcribe() are the only public interface.
Everything else is module-level state that only this file touches.
"""

import os
import tempfile

import numpy as np
import scipy.io.wavfile as wavfile
import sounddevice as sd

from services import model_service

SAMPLE_RATE = 16_000
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en")

_frames: list[np.ndarray] = []
_stream: sd.InputStream | None = None


def start_recording() -> None:
    global _frames, _stream
    _frames = []

    def _callback(indata, _frames_count, _time, _status):
        _frames.append(indata.copy())

    _stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        callback=_callback,
    )
    _stream.start()


def stop_and_transcribe() -> str:
    global _stream

    if _stream is None:
        return ""

    _stream.stop()
    _stream.close()
    _stream = None

    if not _frames:
        return ""

    audio = np.concatenate(_frames).flatten()
    tmp_path = tempfile.mktemp(suffix=".wav")
    wavfile.write(tmp_path, SAMPLE_RATE, (audio * 32_767).astype(np.int16))

    try:
        language = None if WHISPER_LANGUAGE.lower() == "auto" else WHISPER_LANGUAGE
        segments, _ = model_service.get_whisper_model().transcribe(
            tmp_path,
            beam_size=5,
            language=language,
        )
        return " ".join(seg.text for seg in segments).strip()
    finally:
        os.unlink(tmp_path)
