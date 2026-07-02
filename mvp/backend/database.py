import json
import sqlite3
from datetime import datetime

from models import Location, Note, NoteStatus
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
            status      TEXT    NOT NULL DEFAULT 'active',
            parent_note_id INTEGER REFERENCES notes(id),
            deadline_at TEXT,
            importance_score INTEGER NOT NULL DEFAULT 1,
            urgency_score INTEGER NOT NULL DEFAULT 0,
            rank_score INTEGER NOT NULL DEFAULT 0,
            urgency_reason TEXT,
            location_id INTEGER REFERENCES locations(id),
            repeat_cycle TEXT,
            repeat_days TEXT,
            repeat_months TEXT,
            repeat_time TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            latitude    REAL    NOT NULL,
            longitude   REAL    NOT NULL,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        )
    """)
    _migrate_schema(conn)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notes_parent_note_id ON notes(parent_note_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notes_rank ON notes(rank_score DESC, importance_score DESC, deadline_at ASC, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notes_location_id ON notes(location_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_locations_name ON locations(name)"
    )
    conn.commit()
    conn.close()


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _migrate_schema(conn: sqlite3.Connection) -> None:
    note_columns = _table_columns(conn, "notes")
    if "location_id" not in note_columns:
        conn.execute("ALTER TABLE notes ADD COLUMN location_id INTEGER REFERENCES locations(id)")


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


def update_note_recurrence(
    note_id: int,
    repeat_cycle: str | None,
    repeat_days: list[int] | None,
    repeat_months: list[int] | None,
    repeat_time: str | None,
) -> None:
    conn = _connect()
    conn.execute(
        """
        UPDATE notes
        SET repeat_cycle = ?,
            repeat_days = ?,
            repeat_months = ?,
            repeat_time = ?
        WHERE id = ?
        """,
        (
            repeat_cycle,
            json.dumps(repeat_days) if repeat_days is not None else None,
            json.dumps(repeat_months) if repeat_months is not None else None,
            repeat_time,
            note_id,
        ),
    )
    conn.commit()
    conn.close()


def update_note_urgency(
    note_id: int,
    deadline_at: str | None,
    importance_score: int,
    urgency_score: int,
    rank_score: int,
    urgency_reason: str | None,
) -> None:
    conn = _connect()
    conn.execute(
        """
        UPDATE notes
        SET deadline_at = ?,
            importance_score = ?,
            urgency_score = ?,
            rank_score = ?,
            urgency_reason = ?
        WHERE id = ?
        """,
        (deadline_at, importance_score, urgency_score, rank_score, urgency_reason, note_id),
    )
    conn.commit()
    conn.close()


def update_note_location(note_id: int, location_id: int | None) -> None:
    conn = _connect()
    conn.execute("UPDATE notes SET location_id = ? WHERE id = ?", (location_id, note_id))
    conn.commit()
    conn.close()


def upsert_location(name: str, latitude: float, longitude: float) -> Location:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _connect()
    conn.execute(
        """
        INSERT INTO locations (name, latitude, longitude, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            latitude = excluded.latitude,
            longitude = excluded.longitude,
            updated_at = excluded.updated_at
        """,
        (name, latitude, longitude, now, now),
    )
    row = conn.execute(
        """
        SELECT id, name, latitude, longitude, created_at, updated_at
        FROM locations
        WHERE name = ?
        """,
        (name,),
    ).fetchone()
    conn.commit()
    conn.close()
    return _row_to_location(row)


def get_location_by_name(name: str) -> Location | None:
    conn = _connect()
    row = conn.execute(
        """
        SELECT id, name, latitude, longitude, created_at, updated_at
        FROM locations
        WHERE name = ?
        """,
        (name,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_location(row)


def get_all_locations() -> list[Location]:
    conn = _connect()
    rows = conn.execute(
        """
        SELECT id, name, latitude, longitude, created_at, updated_at
        FROM locations
        ORDER BY name ASC
        """
    ).fetchall()
    conn.close()
    return [_row_to_location(row) for row in rows]


def delete_location(location_id: int) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT id FROM locations WHERE id = ?",
        (location_id,),
    ).fetchone()
    if row is None:
        conn.close()
        return False

    conn.execute("UPDATE notes SET location_id = NULL WHERE location_id = ?", (location_id,))
    conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
    conn.commit()
    conn.close()
    return True


def _row_to_location(row: sqlite3.Row) -> Location:
    return Location(
        id=row["id"],
        name=row["name"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_note(row: sqlite3.Row) -> Note:
    def parse_int_list(value: str | None) -> list[int] | None:
        if value is None:
            return None
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(parsed, list):
            return None
        return [int(item) for item in parsed if isinstance(item, int)]

    return Note(
        id=row["id"],
        text=row["text"],
        category=row["category"],
        created_at=row["created_at"],
        status=row["status"],
        parent_note_id=row["parent_note_id"],
        deadline_at=row["deadline_at"],
        importance_score=row["importance_score"],
        urgency_score=row["urgency_score"],
        rank_score=row["rank_score"],
        urgency_reason=row["urgency_reason"],
        location_id=row["location_id"],
        location_name=row["location_name"],
        location_latitude=row["location_latitude"],
        location_longitude=row["location_longitude"],
        repeat_cycle=row["repeat_cycle"],
        repeat_days=parse_int_list(row["repeat_days"]),
        repeat_months=parse_int_list(row["repeat_months"]),
        repeat_time=row["repeat_time"],
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
        SELECT notes.id, notes.text, notes.category, notes.created_at, notes.status,
               notes.parent_note_id, notes.deadline_at, notes.importance_score,
               notes.urgency_score, notes.rank_score, notes.urgency_reason,
               notes.location_id, notes.repeat_cycle, notes.repeat_days,
               notes.repeat_months, notes.repeat_time, locations.name AS location_name,
               locations.latitude AS location_latitude,
               locations.longitude AS location_longitude
        FROM notes
        LEFT JOIN locations ON locations.id = notes.location_id
        WHERE parent_note_id IS NULL {status_filter}
        ORDER BY notes.rank_score DESC,
                 notes.importance_score DESC,
                 CASE WHEN notes.deadline_at IS NULL THEN 1 ELSE 0 END,
                 notes.deadline_at ASC,
                 notes.id DESC
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
        SELECT notes.id, notes.text, notes.category, notes.created_at, notes.status,
               notes.parent_note_id, notes.deadline_at, notes.importance_score,
               notes.urgency_score, notes.rank_score, notes.urgency_reason,
               notes.location_id, notes.repeat_cycle, notes.repeat_days,
               notes.repeat_months, notes.repeat_time, locations.name AS location_name,
               locations.latitude AS location_latitude,
               locations.longitude AS location_longitude
        FROM notes
        LEFT JOIN locations ON locations.id = notes.location_id
        WHERE parent_note_id = ? {status_filter}
        ORDER BY notes.rank_score DESC,
                 notes.importance_score DESC,
                 CASE WHEN notes.deadline_at IS NULL THEN 1 ELSE 0 END,
                 notes.deadline_at ASC,
                 notes.id DESC
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
        SELECT notes.id, notes.text, notes.category, notes.created_at, notes.status,
               notes.parent_note_id, notes.deadline_at, notes.importance_score,
               notes.urgency_score, notes.rank_score, notes.urgency_reason,
               notes.location_id, notes.repeat_cycle, notes.repeat_days,
               notes.repeat_months, notes.repeat_time, locations.name AS location_name,
               locations.latitude AS location_latitude,
               locations.longitude AS location_longitude
        FROM notes
        LEFT JOIN locations ON locations.id = notes.location_id
        {clause}
        ORDER BY notes.rank_score DESC,
                 notes.importance_score DESC,
                 CASE WHEN notes.deadline_at IS NULL THEN 1 ELSE 0 END,
                 notes.deadline_at ASC,
                 notes.id DESC
        """,
        params,
    ).fetchall()
    conn.close()
    return [_row_to_note(row) for row in rows]


def get_note_by_id(note_id: int) -> Note | None:
    conn = _connect()
    row = conn.execute(
        """
        SELECT notes.id, notes.text, notes.category, notes.created_at, notes.status,
               notes.parent_note_id, notes.deadline_at, notes.importance_score,
               notes.urgency_score, notes.rank_score, notes.urgency_reason,
               notes.location_id, notes.repeat_cycle, notes.repeat_days,
               notes.repeat_months, notes.repeat_time, locations.name AS location_name,
               locations.latitude AS location_latitude,
               locations.longitude AS location_longitude
        FROM notes
        LEFT JOIN locations ON locations.id = notes.location_id
        WHERE notes.id = ?
        """,
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
