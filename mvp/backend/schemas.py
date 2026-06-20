from pydantic import BaseModel
from typing import Literal

NoteStatus = Literal["active", "done"]


class TextInput(BaseModel):
    text: str


class CaptureResult(BaseModel):
    id: int | None = None
    text: str
    category: str | None
    created_at: str | None = None
    status: NoteStatus = "active"
    saved: bool


class NoteResponse(BaseModel):
    id: int
    text: str
    category: str
    created_at: str
    status: NoteStatus
    parent_note_id: int | None = None


class NoteDetailResponse(NoteResponse):
    subnotes: list[NoteResponse] = []


class NoteStatusInput(BaseModel):
    status: NoteStatus
