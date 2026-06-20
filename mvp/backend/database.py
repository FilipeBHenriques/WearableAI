import sqlite3
from datetime import datetime

from models import Note, NoteStatus
from paths import DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            text        TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            created_at  TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'done')),
            parent_note_id INTEGER REFERENCES notes(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notes_parent_note_id ON notes(parent_note_id)"
    )
    conn.commit()
    conn.close()


def save_note(text: str, category: str) -> tuple[int, str]:
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO notes (text, category, created_at, status) VALUES (?, ?, ?, 'active')",
        (text, category, created_at),
    )
    note_id = cur.lastrowid
    conn.commit()
    conn.close()
    return note_id, created_at


def update_note_category(note_id: int, category: str) -> None:
    conn = _connect()
    conn.execute("UPDATE notes SET category = ? WHERE id = ?", (category, note_id))
    conn.commit()
    conn.close()


def update_note_parent(note_id: int, parent_note_id: int | None) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE notes SET parent_note_id = ? WHERE id = ?",
        (parent_note_id, note_id),
    )
    conn.commit()
    conn.close()


def update_note_status(note_id: int, status: NoteStatus) -> None:
    conn = _connect()
    conn.execute("UPDATE notes SET status = ? WHERE id = ?", (status, note_id))
    conn.commit()
    conn.close()


def _row_to_note(row: sqlite3.Row) -> Note:
    return Note(
        id=row["id"],
        text=row["text"],
        category=row["category"],
        created_at=row["created_at"],
        status=row["status"],
        parent_note_id=row["parent_note_id"],
    )


def _status_clause(status: NoteStatus | None) -> tuple[str, tuple[str, ...]]:
    if status is None:
        return "", ()
    return "WHERE status = ?", (status,)


def get_root_notes(status: NoteStatus | None = None) -> list[Note]:
    conn = _connect()
    status_filter = "" if status is None else "AND status = ?"
    params: tuple[str, ...] = () if status is None else (status,)
    rows = conn.execute(
        f"""
        SELECT id, text, category, created_at, status, parent_note_id
        FROM notes
        WHERE parent_note_id IS NULL {status_filter}
        ORDER BY id DESC
        """,
        params,
    ).fetchall()
    conn.close()
    return [_row_to_note(row) for row in rows]


def get_child_notes(parent_note_id: int, status: NoteStatus | None = None) -> list[Note]:
    conn = _connect()
    status_filter = "" if status is None else "AND status = ?"
    params: tuple[int, ...] | tuple[int, str] = (
        (parent_note_id,) if status is None else (parent_note_id, status)
    )
    rows = conn.execute(
        f"""
        SELECT id, text, category, created_at, status, parent_note_id
        FROM notes
        WHERE parent_note_id = ? {status_filter}
        ORDER BY id ASC
        """,
        params,
    ).fetchall()
    conn.close()
    return [_row_to_note(row) for row in rows]


def get_all_notes_flat(status: NoteStatus | None = None) -> list[Note]:
    conn = _connect()
    clause, params = _status_clause(status)
    rows = conn.execute(
        f"""
        SELECT id, text, category, created_at, status, parent_note_id
        FROM notes
        {clause}
        ORDER BY id DESC
        """,
        params,
    ).fetchall()
    conn.close()
    return [_row_to_note(row) for row in rows]


def get_note_by_id(note_id: int) -> Note | None:
    conn = _connect()
    row = conn.execute(
        "SELECT id, text, category, created_at, status, parent_note_id FROM notes WHERE id = ?",
        (note_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_note(row)


def delete_notes(note_ids: list[int]) -> None:
    if not note_ids:
        return
    placeholders = ", ".join("?" for _ in note_ids)
    conn = _connect()
    conn.execute(f"DELETE FROM notes WHERE id IN ({placeholders})", note_ids)
    conn.commit()
    conn.close()
