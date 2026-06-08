import os
import sqlite3
from datetime import datetime

from models import Note

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            text        TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            created_at  TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_note(text: str, category: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO notes (text, category, created_at) VALUES (?, ?, ?)",
        (text, category, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    conn.close()


def get_all_notes() -> list[Note]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, text, category, created_at FROM notes ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [Note(id=r[0], text=r[1], category=r[2], created_at=r[3]) for r in rows]


def get_note_by_id(note_id: int) -> Note | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, text, category, created_at FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return Note(id=row[0], text=row[1], category=row[2], created_at=row[3])


def delete_note(note_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
