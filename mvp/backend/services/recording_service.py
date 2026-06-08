"""Owns the microphone stream and Whisper transcription.

start_recording() / stop_and_transcribe() are the only public interface.
Everything else is module-level state that only this file touches.
"""

import os
import tempfile

import numpy as np
import scipy.io.wavfile as wavfile
import sounddevice as sd
from faster_whisper import WhisperModel

SAMPLE_RATE = 16_000

_model: WhisperModel | None = None
_frames: list[np.ndarray] = []
_stream: sd.InputStream | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


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
        segments, _ = _get_model().transcribe(tmp_path, beam_size=5, language="en")
        return " ".join(seg.text for seg in segments).strip()
    finally:
        os.unlink(tmp_path)
