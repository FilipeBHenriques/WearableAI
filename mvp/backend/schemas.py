from pydantic import BaseModel


class TextInput(BaseModel):
    text: str


class CaptureResult(BaseModel):
    id: int | None = None
    text: str
    category: str | None
    created_at: str | None = None
    saved: bool


class CategorizeInput(BaseModel):
    is_subnote: bool = False


class CategorizeResult(BaseModel):
    id: int
    category: str
    parent_note_id: int | None = None


class NoteResponse(BaseModel):
    id: int
    text: str
    category: str
    created_at: str
    parent_note_id: int | None = None


class NoteDetailResponse(NoteResponse):
    subnotes: list[NoteResponse] = []
