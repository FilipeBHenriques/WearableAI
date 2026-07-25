"""Deadline parsing/urgency scoring primitives.

LLM-based deadline extraction lives in memory_extraction_service now, which reuses the
pure functions here (parse_deadline, calculate_urgency, relative_weekday_deadline).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import exp
import re

from models import Note
from services.date_words import WEEKDAY_NAMES_0MON as WEEKDAY_NAMES
from services import note_service
from services.service_logger import log_service_call, log_service_step

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


def parse_deadline(value: str | None) -> datetime | None:
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


def relative_weekday_deadline(text: str, captured_at: datetime) -> datetime | None:
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


def calculate_urgency(
    deadline_at: str | None,
    now: datetime,
    estimated_duration_minutes: int | None = None,
) -> int:
    deadline = parse_deadline(deadline_at)
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


@log_service_call
def refresh_scores(note: Note, captured_at: datetime | None = None) -> UrgencyResult:
    """Recalculate urgency/rank from existing deadline + duration (no LLM)."""
    captured_at = captured_at or datetime.now().astimezone()
    urgency_score = calculate_urgency(
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
