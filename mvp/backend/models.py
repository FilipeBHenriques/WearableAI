from dataclasses import dataclass


@dataclass
class Note:
    id: int
    text: str
    category: str
    created_at: str
