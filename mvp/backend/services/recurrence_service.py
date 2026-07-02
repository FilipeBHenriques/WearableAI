"""Detects and evaluates repeating notes."""

from dataclasses import dataclass
from datetime import date, datetime
import re

from models import Note, RepeatCycle
from services import model_service
from services.llm_utils import extract_json_object
from services.service_logger import log_service_call, log_service_step

REPEAT_DONE_PREFIX = "repeat_done:"
WEEKDAY_NAMES = {
    "monday": 1,
    "mon": 1,
    "tuesday": 2,
    "tue": 2,
    "tues": 2,
    "wednesday": 3,
    "wed": 3,
    "thursday": 4,
    "thu": 4,
    "thur": 4,
    "thurs": 4,
    "friday": 5,
    "fri": 5,
    "saturday": 6,
    "sat": 6,
    "sunday": 7,
    "sun": 7,
}
MONTH_NAMES = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


@dataclass
class RecurrenceResult:
    repeat_cycle: RepeatCycle | None = None
    repeat_days: list[int] | None = None
    repeat_months: list[int] | None = None
    repeat_time: str | None = None


def is_repeating(note: Note) -> bool:
    return note.repeat_cycle in ("daily", "weekly", "monthly", "yearly")


def repeat_done_status(day: date | None = None) -> str:
    return f"{REPEAT_DONE_PREFIX}{(day or date.today()).isoformat()}"


def completed_on(note: Note, day: date | None = None) -> bool:
    return note.status == repeat_done_status(day)


def is_repeat_done_status(status: str) -> bool:
    return status.startswith(REPEAT_DONE_PREFIX)


def is_due_on(note: Note, day: date | None = None) -> bool:
    day = day or date.today()
    if note.repeat_cycle == "daily":
        return True
    if note.repeat_cycle == "weekly":
        return day.isoweekday() in (note.repeat_days or [])
    if note.repeat_cycle == "monthly":
        return day.day in (note.repeat_days or [])
    if note.repeat_cycle == "yearly":
        return day.month in (note.repeat_months or []) and day.day in (note.repeat_days or [])
    return False


def is_available_today(note: Note, day: date | None = None) -> bool:
    return is_due_on(note, day) and not completed_on(note, day)


def repeat_display(note: Note) -> str | None:
    if not is_repeating(note):
        return None

    if note.repeat_cycle == "daily":
        base = "Daily"
    elif note.repeat_cycle == "weekly":
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        base = " / ".join(names[day - 1] for day in (note.repeat_days or []) if 1 <= day <= 7)
        base = base or "Weekly"
    elif note.repeat_cycle == "monthly":
        days = ", ".join(str(day) for day in (note.repeat_days or []))
        base = f"Monthly on {days}" if days else "Monthly"
    else:
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        month_text = ", ".join(months[month - 1] for month in (note.repeat_months or []) if 1 <= month <= 12)
        day_text = ", ".join(str(day) for day in (note.repeat_days or []))
        base = f"Yearly on {month_text} {day_text}".strip() if month_text or day_text else "Yearly"

    return f"{base} · {note.repeat_time}" if note.repeat_time else base


def _normalize_int_list(value, minimum: int, maximum: int) -> list[int] | None:
    if not isinstance(value, list):
        return None
    items = sorted({int(item) for item in value if isinstance(item, int) and minimum <= item <= maximum})
    return items or None


def _normalize_time(value) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
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
    return f"{hour:02d}:{minute:02d}"


def _from_parsed(parsed: dict) -> RecurrenceResult:
    repeats = bool(parsed.get("is_repeating") or parsed.get("repeats"))
    if not repeats:
        return RecurrenceResult()

    cycle = str(parsed.get("repeat_cycle") or parsed.get("cycle") or "").strip().lower()
    if cycle not in ("daily", "weekly", "monthly", "yearly"):
        return RecurrenceResult()

    return RecurrenceResult(
        repeat_cycle=cycle,
        repeat_days=_normalize_int_list(parsed.get("repeat_days"), 1, 31),
        repeat_months=_normalize_int_list(parsed.get("repeat_months"), 1, 12),
        repeat_time=_normalize_time(parsed.get("repeat_time")),
    )


def _extract_time(text: str) -> str | None:
    match = re.search(r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", text, re.IGNORECASE)
    return _normalize_time(match.group(1)) if match else None


def _extract_month_day(text: str) -> tuple[list[int] | None, list[int] | None]:
    month_pattern = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
    match = re.search(rf"\b({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", text, re.IGNORECASE)
    if not match:
        return None, None
    month = MONTH_NAMES[match.group(1).lower()]
    day = int(match.group(2))
    if not 1 <= day <= 31:
        return None, None
    return [day], [month]


def _heuristic(text: str) -> RecurrenceResult:
    lowered = text.lower()
    repeat_time = _extract_time(text)

    if "every day" in lowered or "daily" in lowered:
        return RecurrenceResult("daily", repeat_time=repeat_time)

    if "weekday" in lowered or "weekdays" in lowered:
        return RecurrenceResult("weekly", [1, 2, 3, 4, 5], repeat_time=repeat_time)

    week_days = sorted({number for name, number in WEEKDAY_NAMES.items() if re.search(rf"\b{name}\b", lowered)})
    if week_days:
        return RecurrenceResult("weekly", week_days, repeat_time=repeat_time)

    monthly_match = re.search(r"\bevery\s+month\s+(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\b", lowered)
    if monthly_match:
        day = int(monthly_match.group(1))
        if 1 <= day <= 31:
            return RecurrenceResult("monthly", [day], repeat_time=repeat_time)

    if "every year" in lowered or "yearly" in lowered or "annually" in lowered:
        days, months = _extract_month_day(text)
        return RecurrenceResult("yearly", days, months, repeat_time)

    return RecurrenceResult()


def _build_prompt(text: str, captured_at: datetime) -> str:
    return f"""Return one JSON object only. Do not explain.

Detect whether this note is a repeating task/reminder.

Current local date: {captured_at.date().isoformat()}

Shape:
{{"is_repeating":false,"repeat_cycle":null,"repeat_days":null,"repeat_months":null,"repeat_time":null}}

Rules:
- repeat_cycle is one of daily, weekly, monthly, yearly, or null.
- repeat_days must be numbers.
- For weekly, repeat_days uses Monday=1 through Sunday=7.
- For monthly, repeat_days uses day-of-month 1-31.
- For yearly, repeat_months uses 1-12 and repeat_days uses day-of-month 1-31.
- Daily uses repeat_days null and repeat_months null.
- repeat_time is HH:MM in 24-hour local time or null.
- Only mark is_repeating true when the note clearly asks for a repeated action.

Note: {text}
JSON only:"""


@log_service_call
def analyze_text(text: str, captured_at: datetime | None = None) -> RecurrenceResult:
    captured_at = captured_at or datetime.now().astimezone()
    try:
        raw_text = model_service.generate_llm(
            _build_prompt(text, captured_at),
            max_tokens=192,
            json_mode=True,
        )
        parsed = extract_json_object(raw_text)
        result = _from_parsed(parsed)
        if result.repeat_cycle is not None:
            log_service_step("llm recurrence selected", result=result)
            return result
    except Exception as exc:
        log_service_step("recurrence llm fallback", error=repr(exc))

    result = _heuristic(text)
    log_service_step("heuristic recurrence selected", result=result)
    return result
