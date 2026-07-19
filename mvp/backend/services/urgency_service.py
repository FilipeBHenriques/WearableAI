"""Detects note deadlines and ranks urgency from deadline slack."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import exp
import re

from models import Note
from services.llm_utils import extract_json_object
from services import model_service, note_service
from services.service_logger import log_service_call, log_service_step

WEEKDAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

# Logistic urgency on slack hours: overdue ~100, ~0h ~95, 1d ~90, 1w ~60, 1mo ~floor.
_URGENCY_K = 0.015
_URGENCY_MIDPOINT_HOURS = 200.0
_URGENCY_FLOOR = 5


@dataclass
class UrgencyResult:
    deadline_at: str | None = None
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


def _relative_weekday_deadline(text: str, captured_at: datetime) -> datetime | None:
    weekday_pattern = "|".join(WEEKDAY_NAMES)
    match = re.search(
        rf"\b(?:by|before|due|deadline|deliver|finish|submit|complete)?\s*(next\s+)?({weekday_pattern})\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    has_next = bool(match.group(1))
    target_weekday = WEEKDAY_NAMES[match.group(2).lower()]
    current_weekday = captured_at.weekday()
    days_ahead = (target_weekday - current_weekday) % 7
    if has_next or days_ahead == 0:
        days_ahead = days_ahead or 7

    return datetime.combine((captured_at + timedelta(days=days_ahead)).date(), time(23, 59))


def _score_from_slack_hours(slack_hours: float) -> int:
    """Map slack hours to 0–100 via a logistic curve (higher when slack is low)."""
    if slack_hours < 0:
        # Overdue: approach 100 as more overdue, floor at 97 for tiny overruns.
        overdue = -slack_hours
        return _clamp(round(97 + 3 * (1 - exp(-overdue / 6))), 97, 100)

    score = 100 / (1 + exp(_URGENCY_K * (slack_hours - _URGENCY_MIDPOINT_HOURS)))
    return _clamp(round(max(score, _URGENCY_FLOOR)), 0, 100)


def _calculate_urgency(
    deadline_at: str | None,
    now: datetime,
    estimated_duration_minutes: int | None = None,
) -> int:
    deadline = _parse_deadline(deadline_at)
    if deadline is None:
        return 0

    if deadline.tzinfo is not None:
        deadline = deadline.astimezone().replace(tzinfo=None)
    now = now.astimezone().replace(tzinfo=None) if now.tzinfo is not None else now

    hours_until_due = (deadline - now).total_seconds() / 3600
    if estimated_duration_minutes is not None:
        slack_hours = hours_until_due - (estimated_duration_minutes / 60)
    else:
        slack_hours = hours_until_due
    return _score_from_slack_hours(slack_hours)


def _fallback() -> UrgencyResult:
    return UrgencyResult()


def _build_prompt(note: Note, captured_at: datetime) -> str:
    return f"""Return one JSON object only. Do not explain, do not use markdown, do not use a code fence.

Analyze this note for deadline only.

Current local datetime: {captured_at.isoformat(timespec="minutes")}
Current local date: {captured_at.date().isoformat()}

The JSON object must use this exact shape:
{{"has_deadline":false,"deadline_at":null,"reason":null}}

Rules:
- has_deadline must be true only when the note contains a clear due date or relative deadline.
- deadline_at must be YYYY-MM-DDTHH:MM when has_deadline is true, otherwise null.
- Include the best inferred local time. If the note gives only a date, use 23:59 for that date.
- Resolve relative deadlines like today at 5pm, tomorrow, or next Friday using the current local datetime.
- reason must be a real short explanation for the chosen deadline, not a placeholder.

Note: {note.text}
JSON only:"""


@log_service_call
def analyze_note(note: Note, captured_at: datetime | None = None) -> UrgencyResult:
    captured_at = captured_at or datetime.now().astimezone()
    raw_text = ""
    try:
        log_service_step(
            "using llm urgency analysis",
            note_id=note.id,
            captured_at=captured_at.isoformat(timespec="minutes"),
        )
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
    deadline_at = (
        str(parsed.get("deadline_at") or parsed.get("deadline_date") or "").strip()
        if has_deadline
        else None
    )
    parsed_deadline = _parse_deadline(deadline_at)
    relative_deadline = _relative_weekday_deadline(note.text, captured_at) if has_deadline else None
    if relative_deadline is not None:
        parsed_deadline = relative_deadline
    deadline_at = parsed_deadline.isoformat(timespec="minutes") if parsed_deadline else None

    urgency_score = _calculate_urgency(
        deadline_at,
        captured_at,
        note.estimated_duration_minutes,
    )
    rank_score = urgency_score
    urgency_reason = str(parsed.get("reason") or "").strip() or None
    log_service_step(
        "urgency scores calculated",
        note_id=note.id,
        deadline_at=deadline_at,
        estimated_duration_minutes=note.estimated_duration_minutes,
        urgency_score=urgency_score,
        rank_score=rank_score,
    )

    return UrgencyResult(
        deadline_at=deadline_at,
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
        result.urgency_score,
        result.rank_score,
        result.urgency_reason,
    )
    note.deadline_at = result.deadline_at
    note.urgency_score = result.urgency_score
    note.rank_score = result.rank_score
    note.urgency_reason = result.urgency_reason
    return result


@log_service_call
def refresh_scores(note: Note, captured_at: datetime | None = None) -> UrgencyResult:
    """Recalculate urgency/rank from existing deadline + duration (no LLM)."""
    captured_at = captured_at or datetime.now().astimezone()
    urgency_score = _calculate_urgency(
        note.deadline_at,
        captured_at,
        note.estimated_duration_minutes,
    )
    rank_score = urgency_score
    note_service.update_urgency(
        note.id,
        note.deadline_at,
        urgency_score,
        rank_score,
        note.urgency_reason,
    )
    note.urgency_score = urgency_score
    note.rank_score = rank_score
    log_service_step(
        "urgency scores refreshed",
        note_id=note.id,
        deadline_at=note.deadline_at,
        estimated_duration_minutes=note.estimated_duration_minutes,
        urgency_score=urgency_score,
        rank_score=rank_score,
    )
    return UrgencyResult(
        deadline_at=note.deadline_at,
        urgency_score=urgency_score,
        rank_score=rank_score,
        urgency_reason=note.urgency_reason,
    )
