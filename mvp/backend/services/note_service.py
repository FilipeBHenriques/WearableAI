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
    update_note_status,
)
from models import Note, NoteStatus

PENDING_CATEGORY = "Uncategorized"
ACTIVE_STATUS: NoteStatus = "active"
DONE_STATUS: NoteStatus = "done"


def get_all(status: NoteStatus | None = None) -> list[Note]:
    if status is None:
        return get_root_notes()

    notes = get_all_notes_flat(status)
    note_ids = {note.id for note in notes}
    return [
        note
        for note in notes
        if note.parent_note_id is None or note.parent_note_id not in note_ids
    ]


def get_subnotes(note_id: int, status: NoteStatus | None = None) -> list[Note]:
    return get_child_notes(note_id, status)


def get_all_flat(status: NoteStatus | None = None) -> list[Note]:
    return get_all_notes_flat(status)


def save(text: str, category: str = PENDING_CATEGORY) -> tuple[int, str]:
    return save_note(text, category)


def update_category(note_id: int, category: str) -> None:
    update_note_category(note_id, category)


def update_parent(note_id: int, parent_note_id: int | None) -> None:
    update_note_parent(note_id, parent_note_id)


def _descendant_ids(note_id: int) -> list[int]:
    children_by_parent: dict[int, list[int]] = {}
    for note in get_all_notes_flat():
        if note.parent_note_id is None:
            continue
        children_by_parent.setdefault(note.parent_note_id, []).append(note.id)

    pending = [note_id]
    descendants: list[int] = []
    while pending:
        current = pending.pop()
        for child_id in children_by_parent.get(current, []):
            descendants.append(child_id)
            pending.append(child_id)
    return descendants


def mark_note_as(note_id: int, status: NoteStatus) -> None:
    if status not in (ACTIVE_STATUS, DONE_STATUS):
        raise ValueError(f"Unsupported note status: {status}")

    note_ids = [note_id, *_descendant_ids(note_id)]

    for current_id in note_ids:
        update_note_status(current_id, status)


def toggle_note_status(note_id: int) -> NoteStatus | None:
    note = get_note_by_id(note_id)
    if note is None:
        return None

    next_status: NoteStatus = DONE_STATUS if note.status == ACTIVE_STATUS else ACTIVE_STATUS
    mark_note_as(note_id, next_status)
    return next_status


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
