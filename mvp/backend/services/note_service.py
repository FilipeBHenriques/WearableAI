"""All note operations go through here.

Routes and other services call this module instead of database.py directly.
When the storage layer changes (e.g. adding projects or embeddings),
only this file and database.py need to change.
"""

from database import delete_note, get_all_notes, get_note_by_id, save_note
from models import Note


def get_all() -> list[Note]:
    return get_all_notes()


def save(text: str, category: str) -> None:
    save_note(text, category)


def get_by_id(note_id: int) -> Note | None:
    return get_note_by_id(note_id)


def delete(note_id: int) -> None:
    delete_note(note_id)
