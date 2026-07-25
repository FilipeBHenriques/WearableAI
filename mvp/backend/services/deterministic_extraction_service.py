"""Non-LLM extraction of deadline/duration/recurrence fields from note text.

Runs before any LLM call. Code handles the closed set of patterns it can parse with
confidence (explicit/relative dates, stated durations, recurring-schedule phrasing).
Anything it cannot resolve, but that has a signal it *should* resolve to something
(soft deadline language, a repeat signal with no clean pattern), is listed in
`.unresolved` so the caller knows which fields — and only which fields — to ask an LLM
for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
import re

from models import RepeatCycle
from services.date_words import MONTH_NAMES
from services.recurrence_service import has_repeat_signal, heuristic_extract
from services.urgency_service import relative_weekday_deadline
from services.service_logger import log_service_call, log_service_step

_SOFT_DEADLINE_SIGNAL = re.compile(
    r"\b(by|before|due|deadline|deliver|finish|submit|complete|end of|sometime|soon|asap)\b",
    re.IGNORECASE,
)

_RELATIVE_DAY_PATTERNS = (
    (re.compile(r"\btomorrow\b", re.IGNORECASE), 1),
    (re.compile(r"\btoday\b", re.IGNORECASE), 0),
    (re.compile(r"\btonight\b", re.IGNORECASE), 0),
)

_NEXT_WEEK_RE = re.compile(r"\bnext week\b", re.IGNORECASE)
_IN_N_DAYS_RE = re.compile(r"\bin\s+(\d+)\s+day(?:s)?\b", re.IGNORECASE)
_IN_N_WEEKS_RE = re.compile(r"\bin\s+(\d+)\s+week(?:s)?\b", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_SLASH_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_MONTH_DAY_RE = re.compile(
    r"\b(" + "|".join(sorted(MONTH_NAMES, key=len, reverse=True)) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", re.IGNORECASE)

_DURATION_HOURS_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", re.IGNORECASE)
_DURATION_MINUTES_RE = re.compile(r"\b(\d+)\s*(?:minutes?|mins?|m)\b", re.IGNORECASE)
_HALF_HOUR_RE = re.compile(r"\bhalf an? hour\b", re.IGNORECASE)

# Regex date-matching can't tell "by tomorrow" from "I don't need this by
# tomorrow" — this catches the common negation phrasings so a note explicitly
# waving off urgency doesn't get a deadline stamped on it anyway.
_URGENCY_NEGATION_RE = re.compile(
    r"\b(don't|do not|doesn't|does not|didn't|did not|no)\s+(need|have|rush|hurry)\b",
    re.IGNORECASE,
)


@dataclass
class DeterministicResult:
    deadline_at: str | None = None
    urgency_reason: str | None = None
    estimated_duration_minutes: int | None = None
    repeat_cycle: RepeatCycle | None = None
    repeat_days: list[int] | None = None
    repeat_months: list[int] | None = None
    repeat_time: str | None = None
    unresolved: set[str] = field(default_factory=set)


def _normalize_time(value: str) -> time | None:
    raw = value.strip().lower()
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", raw)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    suffix = match.group(3)
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def _time_of_day(text: str) -> time | None:
    match = _TIME_RE.search(text)
    return _normalize_time(match.group(1)) if match else None


def _combine(day: datetime, time_of_day: time | None) -> datetime:
    return datetime.combine(day.date(), time_of_day or time(23, 59))


def _parse_relative_date(text: str, captured_at: datetime) -> datetime | None:
    time_of_day = _time_of_day(text)

    for pattern, day_offset in _RELATIVE_DAY_PATTERNS:
        if pattern.search(text):
            return _combine(captured_at + timedelta(days=day_offset), time_of_day)

    if _NEXT_WEEK_RE.search(text):
        return _combine(captured_at + timedelta(days=7), time_of_day)

    match = _IN_N_DAYS_RE.search(text)
    if match:
        return _combine(captured_at + timedelta(days=int(match.group(1))), time_of_day)

    match = _IN_N_WEEKS_RE.search(text)
    if match:
        return _combine(captured_at + timedelta(weeks=int(match.group(1))), time_of_day)

    match = _ISO_DATE_RE.search(text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return _combine(datetime(year, month, day), time_of_day)
        except ValueError:
            pass

    match = _SLASH_DATE_RE.search(text)
    if match:
        month, day, year_part = match.groups()
        month, day = int(month), int(day)
        year = captured_at.year if year_part is None else int(year_part)
        if year < 100:
            year += 2000
        try:
            candidate = datetime(year, month, day)
        except ValueError:
            candidate = None
        if candidate is not None:
            if year_part is None and candidate.date() < captured_at.date():
                candidate = candidate.replace(year=year + 1)
            return _combine(candidate, time_of_day)

    match = _MONTH_DAY_RE.search(text)
    if match:
        month = MONTH_NAMES[match.group(1).lower()]
        day = int(match.group(2))
        year = captured_at.year
        try:
            candidate = datetime(year, month, day)
        except ValueError:
            candidate = None
        if candidate is not None:
            if candidate.date() < captured_at.date():
                candidate = candidate.replace(year=year + 1)
            return _combine(candidate, time_of_day)

    if has_repeat_signal(text):
        # "every Monday" etc. is a recurrence, not a one-time deadline — let the
        # recurrence branch below handle it instead of misreading it as a due date.
        return None

    weekday_deadline = relative_weekday_deadline(text, captured_at)
    if weekday_deadline is not None and time_of_day is not None:
        weekday_deadline = datetime.combine(weekday_deadline.date(), time_of_day)
    return weekday_deadline


def _parse_duration_hint(text: str) -> int | None:
    if _HALF_HOUR_RE.search(text):
        return 30

    match = _DURATION_HOURS_RE.search(text)
    if match:
        return round(float(match.group(1)) * 60)

    match = _DURATION_MINUTES_RE.search(text)
    if match:
        return int(match.group(1))

    return None


@log_service_call
def extract(text: str, captured_at: datetime | None = None) -> DeterministicResult:
    captured_at = captured_at or datetime.now().astimezone()
    result = DeterministicResult()
    negated = _URGENCY_NEGATION_RE.search(text) is not None

    if negated:
        log_service_step("urgency negated; skipping deadline extraction", text=text)
    else:
        deadline = _parse_relative_date(text, captured_at)
        if deadline is not None:
            result.deadline_at = deadline.isoformat(timespec="minutes")
            result.urgency_reason = "Matched an explicit or relative date in the note."
        elif _SOFT_DEADLINE_SIGNAL.search(text):
            result.unresolved.add("deadline_at")

    # A stated duration ("for 45 minutes") is meaningful whether or not the note
    # has a one-time deadline — recurring tasks state durations too. Only fall
    # back to asking the LLM when there's a deadline to estimate duration for
    # and no explicit hint was found.
    duration = _parse_duration_hint(text)
    if duration is not None:
        result.estimated_duration_minutes = duration
    elif result.deadline_at is not None:
        result.unresolved.add("estimated_duration_minutes")

    recurrence = heuristic_extract(text)
    if recurrence.repeat_cycle is not None:
        result.repeat_cycle = recurrence.repeat_cycle
        result.repeat_days = recurrence.repeat_days
        result.repeat_months = recurrence.repeat_months
        result.repeat_time = recurrence.repeat_time
    elif has_repeat_signal(text):
        result.unresolved.add("repeat_cycle")

    log_service_step(
        "deterministic extraction",
        deadline_at=result.deadline_at,
        estimated_duration_minutes=result.estimated_duration_minutes,
        repeat_cycle=result.repeat_cycle,
        unresolved=sorted(result.unresolved),
    )
    return result
