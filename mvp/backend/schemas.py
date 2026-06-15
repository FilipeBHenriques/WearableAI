from pydantic import BaseModel


class TextInput(BaseModel):
    text: str


class CaptureResult(BaseModel):
    id: int | None = None
    text: str
    category: str | None
    created_at: str | None = None
    saved: bool


class CategorizeResult(BaseModel):
    id: int
    category: str
