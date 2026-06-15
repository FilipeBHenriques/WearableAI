"""All note operations go through here.

Routes and other services call this module instead of database.py directly.
When the storage layer changes (e.g. adding projects or embeddings),
only this file and database.py need to change.
"""

from database import delete_note, get_all_notes, get_note_by_id, save_note, update_note_category
from models import Note

PENDING_CATEGORY = "Uncategorized"


def get_all() -> list[Note]:
    return get_all_notes()


def save(text: str, category: str = PENDING_CATEGORY) -> tuple[int, str]:
    return save_note(text, category)


def update_category(note_id: int, category: str) -> None:
    update_note_category(note_id, category)


def get_by_id(note_id: int) -> Note | None:
    return get_note_by_id(note_id)


def delete(note_id: int) -> None:
    delete_note(note_id)
