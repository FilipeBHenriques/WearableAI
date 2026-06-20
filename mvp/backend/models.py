from dataclasses import dataclass
from typing import Literal

NoteStatus = Literal["active", "done"]


@dataclass
class Note:
    id: int
    text: str
    category: str
    created_at: str
    status: NoteStatus = "active"
    parent_note_id: int | None = None
