from dataclasses import dataclass
from typing import Literal

NoteStatus = str
RepeatCycle = Literal["daily", "weekly", "monthly", "yearly"]


@dataclass
class Location:
    id: int
    name: str
    latitude: float
    longitude: float
    created_at: str
    updated_at: str


@dataclass
class Note:
    id: int
    text: str
    category: str
    created_at: str
    status: NoteStatus = "active"
    parent_note_id: int | None = None
    deadline_at: str | None = None
    importance_score: int = 1
    urgency_score: int = 0
    rank_score: int = 0
    urgency_reason: str | None = None
    location_id: int | None = None
    location_name: str | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None
    repeat_cycle: RepeatCycle | None = None
    repeat_days: list[int] | None = None
    repeat_months: list[int] | None = None
    repeat_time: str | None = None
