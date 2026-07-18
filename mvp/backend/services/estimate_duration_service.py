"""Estimates how long a note/task will take to complete."""

from dataclasses import dataclass

from models import Note
from services import model_service, note_service
from services.llm_utils import extract_json_object
from services.service_logger import log_service_call, log_service_step


@dataclass
class DurationResult:
    estimated_duration_minutes: int | None = None
    reason: str | None = None


def _clamp_minutes(value: int) -> int:
    return max(0, min(value, 60 * 24 * 14))


def _build_prompt(note: Note) -> str:
    return f"""Return one JSON object only. Do not explain, do not use markdown, do not use a code fence.

Estimate realistic hands-on effort time for a typical person to finish this note.

Category: {note.category}
Note: {note.text}

The JSON object must use this exact shape:
{{"estimated_duration_minutes":0,"reason":null}}

Rules:
- estimated_duration_minutes must be a non-negative integer (minutes of actual work).
- Scale by difficulty. Tiny chores and huge writing projects must NOT get the same estimate.
- Examples of scale:
  - take out garbage / quick email / short call: 5-15
  - groceries / clean room / short meeting: 30-90
  - study session / build a small feature: 120-240
  - write a long essay/report/thesis chapter: hundreds to thousands of minutes
  - "100 page essay" style work: at least several thousand minutes
- Use 0 for ideas, thoughts, or notes that are not actionable.
- Prefer effort time, not calendar span until a deadline.
- reason must briefly justify the scale chosen.

JSON only:"""


@log_service_call
def analyze_note(note: Note) -> DurationResult:
    try:
        log_service_step("using llm duration estimate", note_id=note.id)
        raw_text = model_service.generate_llm(
            _build_prompt(note),
            max_tokens=160,
            json_mode=True,
        )
        log_service_step("llm duration response", note_id=note.id, response=raw_text)
        parsed = extract_json_object(raw_text)
        minutes = int(parsed.get("estimated_duration_minutes"))
        reason = str(parsed.get("reason") or "").strip() or None
        return DurationResult(
            estimated_duration_minutes=_clamp_minutes(minutes),
            reason=reason,
        )
    except Exception as exc:
        log_service_step("duration estimate failed", note_id=note.id, error=repr(exc))
        return DurationResult(estimated_duration_minutes=None, reason=None)


@log_service_call
def apply_estimate(note: Note) -> DurationResult:
    result = analyze_note(note)
    if result.estimated_duration_minutes is None:
        log_service_step("duration not set", note_id=note.id)
        return result
    note_service.update_estimated_duration(note.id, result.estimated_duration_minutes)
    note.estimated_duration_minutes = result.estimated_duration_minutes
    return result
