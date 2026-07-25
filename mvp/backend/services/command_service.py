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
- save_location: the user is directly announcing the place they are physically standing in right now, so its GPS coordinates should be saved (e.g. "this is my office", "we are at the gym", "this is the studio").
- take_note: everything else — reminders, tasks, plans, ideas, or any statement that merely mentions a place without the user declaring they are currently there. This includes the word "save" used in any other sense (saving data, a save system, a save file, saving money, etc.) — that is unrelated to save_location and must be take_note.

JSON shape:
{{"command":"take_note","location_name":null}}

Examples:
Transcript: this is my office
{{"command":"save_location","location_name":"office"}}

Transcript: need to book the venue and order the cake for the party
{{"command":"take_note","location_name":null}}

Transcript: remind me to call the gym about membership pricing
{{"command":"take_note","location_name":null}}

Transcript: the save system should store player position and inventory
{{"command":"take_note","location_name":null}}

Rules:
- Use save_location ONLY when the transcript is a direct present-tense declaration of the current location ("this is ...", "we are at ...", "I am at ...").
- If the place is mentioned as part of a task, plan, or reminder (book, call, visit, order, meet at), it is take_note.
- The word "save" alone does NOT mean save_location — only a location declaration does.
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
