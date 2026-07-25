"""Experimental transcript cleanup (gaps / filler)."""

from feature_flags import FIXUP_ENABLED
from services import model_service
from services.llm_utils import extract_json_object
from services.service_logger import log_service_call, log_service_step


def _build_prompt(transcript: str) -> str:
    return f"""Return one JSON object only. Do not explain, do not use markdown, do not use a code fence.

Lightly correct this voice-note transcription.

Transcript: {transcript}

The JSON object must use this exact shape:
{{"fixed_text":"..."}}

Rules:
- Only fix clear typos, garbled words, or nonsense tokens that are obvious speech-to-text errors.
- Preserve every meaningful detail: names, places, times, deadlines, quantities, and intent.
- Do not delete, summarize, shorten, or rewrite the note into a cleaner version.
- Do not invent new facts, tasks, or deadlines.
- Do not remove filler only if removing it would drop meaning; prefer keeping wording when unsure.
- If nothing needs fixing, return the transcript unchanged.

JSON only:"""


@log_service_call
def fix_transcript(transcript: str) -> str:
    text = transcript.strip()
    if not FIXUP_ENABLED or not text:
        return text

    try:
        log_service_step("fixing transcript", length=len(text))
        raw_text = model_service.generate_llm(
            _build_prompt(text),
            max_tokens=512,
            json_mode=True,
        )
        parsed = extract_json_object(raw_text)
        fixed = str(parsed.get("fixed_text") or "").strip()
        if not fixed:
            log_service_step("fixup empty, keeping original")
            return text
        # Reject aggressive shrinks that likely dropped content.
        if len(fixed) < max(12, int(len(text) * 0.6)):
            log_service_step(
                "fixup too short, keeping original",
                original_length=len(text),
                fixed_length=len(fixed),
            )
            return text
        log_service_step("fixup applied", original_length=len(text), fixed_length=len(fixed))
        return fixed
    except Exception as exc:
        log_service_step("fixup failed, keeping original", error=repr(exc))
        return text
