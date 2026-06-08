from pydantic import BaseModel


class TextInput(BaseModel):
    text: str


class CaptureResult(BaseModel):
    text: str
    category: str | None
    saved: bool
