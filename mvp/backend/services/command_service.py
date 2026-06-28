"""Classifies transcripts into capture commands."""

from dataclasses import dataclass
from enum import Enum

from services import model_service
from services.llm_utils import extract_json_object
from services.service_logger import log_service_call, log_service_step


class CommandType(str, Enum):
    SAVE_LOCATION = "save_location"
    TAKE_NOTE = "take_note"


@dataclass(frozen=True)
class Command:
    type: CommandType
    location_name: str | None = None


def _ask_llm(text: str) -> Command:
    log_service_step("using llm command classification")
    prompt = f"""Return one JSON object only. Do not explain, do not use markdown.

Classify the transcript as one of these commands:
- save_location: the user is naming the current physical place so GPS coordinates should be saved.
- take_note: the user is saying content that should become a note.

JSON shape:
{{"command":"take_note","location_name":null}}

Rules:
- Use save_location only when the user is identifying the current place.
- Use take_note for reminders, tasks, ideas, or statements to remember.
- If command is save_location, location_name must be the exact short place name from the transcript.
- If command is take_note, location_name must be null.

Transcript: {text}
JSON:"""
    raw_text = model_service.generate_llm(prompt, max_tokens=128, json_mode=True)
    parsed = extract_json_object(raw_text)
    command = str(parsed.get("command") or "").strip().lower()
    location_name = str(parsed.get("location_name") or "").strip()
    log_service_step(
        "llm classified command",
        command=command,
        location_name=location_name or None,
    )

    if command == CommandType.SAVE_LOCATION.value and location_name:
        return Command(type=CommandType.SAVE_LOCATION, location_name=location_name)
    return Command(type=CommandType.TAKE_NOTE)


@log_service_call
def detect_command(text: str) -> Command:
    normalized_text = text.strip()
    if not normalized_text:
        log_service_step("empty text defaults to take_note")
        return Command(type=CommandType.TAKE_NOTE)

    llm_status = model_service.get_llm_config_status()
    if not llm_status["configured"]:
        log_service_step(
            "llm unavailable; defaulting to take_note",
            error=llm_status.get("error"),
        )
        return Command(type=CommandType.TAKE_NOTE)

    try:
        return _ask_llm(normalized_text)
    except Exception as exc:
        log_service_step("llm failed; defaulting to take_note", error=repr(exc))
        return Command(type=CommandType.TAKE_NOTE)
