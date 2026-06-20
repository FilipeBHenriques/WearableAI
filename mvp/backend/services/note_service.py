"""All note operations go through here.

Routes and other services call this module instead of database.py directly.
When the storage layer changes (e.g. adding projects or embeddings),
only this file and database.py need to change.
"""

from database import (
    delete_notes,
    get_child_notes,
    get_all_notes_flat,
    get_note_by_id,
    get_root_notes,
    save_note,
    update_note_category,
    update_note_parent,
)
from models import Note

PENDING_CATEGORY = "Uncategorized"


def get_all() -> list[Note]:
    return get_root_notes()


def get_subnotes(note_id: int) -> list[Note]:
    return get_child_notes(note_id)


def get_all_flat() -> list[Note]:
    return get_all_notes_flat()


def save(text: str, category: str = PENDING_CATEGORY) -> tuple[int, str]:
    return save_note(text, category)


def update_category(note_id: int, category: str) -> None:
    update_note_category(note_id, category)


def update_parent(note_id: int, parent_note_id: int | None) -> None:
    update_note_parent(note_id, parent_note_id)


def get_by_id(note_id: int) -> Note | None:
    return get_note_by_id(note_id)


def delete(note_id: int) -> None:
    children_by_parent: dict[int, list[int]] = {}
    for note in get_all_notes_flat():
        if note.parent_note_id is None:
            continue
        children_by_parent.setdefault(note.parent_note_id, []).append(note.id)

    pending = [note_id]
    to_delete: list[int] = []
    while pending:
        current = pending.pop()
        to_delete.append(current)
        pending.extend(children_by_parent.get(current, []))

    delete_notes(to_delete)
