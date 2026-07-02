from pydantic import BaseModel
from typing import Literal

NoteStatus = str
RepeatCycle = Literal["daily", "weekly", "monthly", "yearly"]


class TextInput(BaseModel):
    text: str


class CaptureResult(BaseModel):
    id: int | None = None
    text: str
    category: str | None
    created_at: str | None = None
    status: NoteStatus = "active"
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
    is_repeating: bool = False
    is_due_today: bool = False
    completed_today: bool = False
    repeat_display: str | None = None
    saved: bool
    command_processed: bool = False
    command_type: str | None = None
    message: str | None = None


class NoteResponse(BaseModel):
    id: int
    text: str
    category: str
    created_at: str
    status: NoteStatus
    parent_note_id: int | None = None
    deadline_at: str | None = None
    importance_score: int
    urgency_score: int
    rank_score: int
    urgency_reason: str | None = None
    location_id: int | None = None
    location_name: str | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None
    repeat_cycle: RepeatCycle | None = None
    repeat_days: list[int] | None = None
    repeat_months: list[int] | None = None
    repeat_time: str | None = None
    is_repeating: bool = False
    is_due_today: bool = False
    completed_today: bool = False
    repeat_display: str | None = None


class NoteDetailResponse(NoteResponse):
    subnotes: list[NoteResponse] = []


class NoteStatusInput(BaseModel):
    status: NoteStatus


class LocationResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    created_at: str
    updated_at: str
