"""Detects note deadlines and ranks urgency/importance."""

from dataclasses import dataclass
from datetime import date, datetime, time

from models import Note
from services.llm_utils import extract_json_object
from services import model_service, note_service
from services.service_logger import log_service_call, log_service_step


@dataclass
class UrgencyResult:
    deadline_at: str | None = None
    importance_score: int = 1
    urgency_score: int = 0
    rank_score: int = 0
    urgency_reason: str | None = None


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    if "T" not in value and " " not in value:
        try:
            return datetime.combine(date.fromisoformat(value), time(23, 59))
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _calculate_urgency(deadline_at: str | None, now: datetime) -> int:
    deadline = _parse_deadline(deadline_at)
    if deadline is None:
        return 0

    if deadline.tzinfo is not None:
        deadline = deadline.astimezone().replace(tzinfo=None)
    now = now.astimezone().replace(tzinfo=None) if now.tzinfo is not None else now

    hours_until_due = (deadline - now).total_seconds() / 3600
    if hours_until_due < 0:
        return 100
    if hours_until_due <= 2:
        return 98
    if hours_until_due <= 6:
        return 95
    if hours_until_due <= 24:
        return 90
    if hours_until_due <= 72:
        return 80
    if hours_until_due <= 168:
        return 65
    if hours_until_due <= 336:
        return 45
    if hours_until_due <= 720:
        return 25
    return 10


def _calculate_rank(importance_score: int, urgency_score: int) -> int:
    importance_component = ((importance_score - 1) / 4) * 100
    return _clamp(round((urgency_score * 0.65) + (importance_component * 0.35)), 0, 100)


def _fallback() -> UrgencyResult:
    return UrgencyResult()


def _build_prompt(note: Note, captured_at: datetime) -> str:
    return f"""Return one JSON object only. Do not explain, do not use markdown, do not use a code fence.

Analyze this note for deadline and importance.

Current local datetime: {captured_at.isoformat(timespec="minutes")}
Current local date: {captured_at.date().isoformat()}

The JSON object must use this exact shape:
{{"has_deadline":false,"deadline_at":null,"importance_score":1,"reason":null}}

Rules:
- has_deadline must be true only when the note contains a clear due date or relative deadline.
- deadline_at must be YYYY-MM-DDTHH:MM when has_deadline is true, otherwise null.
- Include the best inferred local time. If the note gives only a date, use 23:59 for that date.
- Resolve relative deadlines like today at 5pm, tomorrow, or next Friday using the current local datetime.
- importance_score must be an integer from 1 to 5.
- Score 5 for serious consequences, explicit commitments, people depending on it, or high-stakes deadlines.
- Score 3 for normal actionable tasks or reminders.
- Score 1 for casual ideas, low-stakes notes, or non-actionable thoughts.
- reason must be a real short explanation for the chosen deadline and importance, not a placeholder.

Note: {note.text}
JSON only:"""


@log_service_call
def analyze_note(note: Note, captured_at: datetime | None = None) -> UrgencyResult:
    captured_at = captured_at or datetime.now().astimezone()
    try:
        log_service_step("using llm urgency analysis", note_id=note.id, captured_at=captured_at.isoformat(timespec="minutes"))
        raw_text = model_service.generate_llm(
            _build_prompt(note, captured_at),
            max_tokens=256,
            json_mode=True,
        )
        log_service_step("llm urgency response", note_id=note.id, response=raw_text)
        parsed = extract_json_object(raw_text)
    except ValueError as exc:
        log_service_step("urgency json fallback", note_id=note.id, error=repr(exc), response=raw_text)
        return _fallback()
    except Exception as exc:
        log_service_step("urgency fallback", note_id=note.id, error=repr(exc))
        return _fallback()

    has_deadline = bool(parsed.get("has_deadline"))
    deadline_at = str(parsed.get("deadline_at") or parsed.get("deadline_date") or "").strip() if has_deadline else None
    parsed_deadline = _parse_deadline(deadline_at)
    deadline_at = parsed_deadline.isoformat(timespec="minutes") if parsed_deadline else None

    try:
        importance_score = int(parsed.get("importance_score", 1))
    except (TypeError, ValueError):
        importance_score = 1

    importance_score = _clamp(importance_score, 1, 5)
    urgency_score = _calculate_urgency(deadline_at, captured_at)
    rank_score = _calculate_rank(importance_score, urgency_score)
    urgency_reason = str(parsed.get("reason") or "").strip() or None
    log_service_step(
        "urgency scores calculated",
        note_id=note.id,
        deadline_at=deadline_at,
        importance_score=importance_score,
        urgency_score=urgency_score,
        rank_score=rank_score,
    )

    return UrgencyResult(
        deadline_at=deadline_at,
        importance_score=importance_score,
        urgency_score=urgency_score,
        rank_score=rank_score,
        urgency_reason=urgency_reason,
    )


@log_service_call
def apply_urgency(note: Note, captured_at: datetime | None = None) -> UrgencyResult:
    result = analyze_note(note, captured_at)
    note_service.update_urgency(
        note.id,
        result.deadline_at,
        result.importance_score,
        result.urgency_score,
        result.rank_score,
        result.urgency_reason,
    )
    note.deadline_at = result.deadline_at
    note.importance_score = result.importance_score
    note.urgency_score = result.urgency_score
    note.rank_score = result.rank_score
    note.urgency_reason = result.urgency_reason
    return result
