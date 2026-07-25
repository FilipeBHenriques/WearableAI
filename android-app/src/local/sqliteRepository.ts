import {
  CapacitorSQLite,
  SQLiteConnection,
  type SQLiteDBConnection,
} from "@capacitor-community/sqlite";
import type { CaptureJobPatch, LocalRepository, NotePatch } from "./repository";
import { assertValidParent, normalizeRepeatCycle } from "./repository";
import {
  nowText,
  PENDING_CATEGORY,
  type CaptureJob,
  type CaptureJobStatus,
  type Location,
  type Note,
  type NoteStatus,
} from "./types";

/** Small seam that permits unit-testing SQLite behavior without a native runtime. */
export interface SqliteDatabase {
  open(): Promise<void>;
  execute(sql: string): Promise<unknown>;
  run(
    sql: string,
    values?: unknown[],
  ): Promise<{ changes?: { lastId?: number; changes?: number } | number }>;
  query(sql: string, values?: unknown[]): Promise<{ values?: Record<string, unknown>[] }>;
}

export async function createCapacitorDatabase(
  name = "wearable_ai",
): Promise<SqliteDatabase> {
  const manager = new SQLiteConnection(CapacitorSQLite);
  const consistency = await manager.checkConnectionsConsistency();
  const hasConnection = (await manager.isConnection(name, false)).result;
  let connection: SQLiteDBConnection;
  if (consistency.result && hasConnection) {
    connection = await manager.retrieveConnection(name, false);
  } else {
    connection = await manager.createConnection(name, false, "no-encryption", 1, false);
  }
  return connection;
}

export class CapacitorSqliteRepository implements LocalRepository {
  constructor(private readonly db: SqliteDatabase) {}

  static async create(name?: string): Promise<CapacitorSqliteRepository> {
    const repository = new CapacitorSqliteRepository(await createCapacitorDatabase(name));
    await repository.initialize();
    return repository;
  }

  async initialize(): Promise<void> {
    await this.db.open();
    await this.db.execute(`
      PRAGMA foreign_keys = ON;
      CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
        latitude REAL NOT NULL, longitude REAL NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL,
        category TEXT NOT NULL, created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        parent_note_id INTEGER REFERENCES notes(id),
        deadline_at TEXT, urgency_score INTEGER NOT NULL DEFAULT 0,
        rank_score INTEGER NOT NULL DEFAULT 0, urgency_reason TEXT,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        repeat_cycle TEXT, repeat_days TEXT, repeat_months TEXT,
        repeat_time TEXT, estimated_duration_minutes INTEGER, audio_path TEXT
      );
      CREATE TABLE IF NOT EXISTS capture_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT NOT NULL,
        final_transcript TEXT, note_id INTEGER REFERENCES notes(id) ON DELETE SET NULL,
        error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_notes_parent ON notes(parent_note_id);
      CREATE INDEX IF NOT EXISTS idx_notes_rank ON notes(rank_score DESC, deadline_at ASC, id DESC);
      CREATE INDEX IF NOT EXISTS idx_notes_location ON notes(location_id);
      CREATE INDEX IF NOT EXISTS idx_capture_status ON capture_jobs(status, id DESC);
    `);
  }

  async createNote(text: string, category = PENDING_CATEGORY): Promise<Note> {
    const createdAt = nowText().slice(0, 16);
    const result = await this.db.run(
      "INSERT INTO notes (text, category, created_at, status) VALUES (?, ?, ?, 'active')",
      [text, category, createdAt],
    );
    const id = lastInsertId(result);
    const note = await this.getNote(id);
    if (!note) throw new Error("SQLite did not return the inserted note.");
    return note;
  }

  async getNote(id: number): Promise<Note | null> {
    const rows = await this.noteQuery("WHERE notes.id = ?", [id]);
    return rows[0] ?? null;
  }

  async listNotes(status?: NoteStatus | null): Promise<Note[]> {
    const clause = status == null ? "" : "WHERE notes.status = ?";
    return this.noteQuery(clause, status == null ? [] : [status]);
  }

  async listChildNotes(parentId: number, status?: NoteStatus | null): Promise<Note[]> {
    const clause =
      status == null
        ? "WHERE notes.parent_note_id = ?"
        : "WHERE notes.parent_note_id = ? AND notes.status = ?";
    return this.noteQuery(clause, status == null ? [parentId] : [parentId, status]);
  }

  async updateNote(id: number, patch: NotePatch): Promise<Note | null> {
    if ("parent_note_id" in patch)
      await assertValidParent(this, id, patch.parent_note_id ?? null);
    const entries = Object.entries(patch);
    if (!entries.length) return this.getNote(id);
    const values = entries.map(([key, value]) =>
      key === "repeat_days" || key === "repeat_months"
        ? value == null
          ? null
          : JSON.stringify(value)
        : value,
    );
    await this.db.run(
      `UPDATE notes SET ${entries.map(([key]) => `${key} = ?`).join(", ")} WHERE id = ?`,
      [...values, id],
    );
    return this.getNote(id);
  }

  async deleteNotes(ids: number[]): Promise<void> {
    if (!ids.length) return;
    await this.db.run(
      `DELETE FROM notes WHERE id IN (${ids.map(() => "?").join(",")})`,
      ids,
    );
  }

  async upsertLocation(name: string, latitude: number, longitude: number): Promise<Location> {
    const clean = name.trim();
    const timestamp = nowText().slice(0, 16);
    await this.db.run(
      `INSERT INTO locations (name, latitude, longitude, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(name) DO UPDATE SET latitude=excluded.latitude,
         longitude=excluded.longitude, updated_at=excluded.updated_at`,
      [clean, latitude, longitude, timestamp, timestamp],
    );
    const result = await this.db.query("SELECT * FROM locations WHERE name = ?", [clean]);
    return result.values?.[0] as unknown as Location;
  }

  async listLocations(): Promise<Location[]> {
    const result = await this.db.query("SELECT * FROM locations ORDER BY name ASC");
    return (result.values ?? []) as unknown as Location[];
  }

  async deleteLocation(id: number): Promise<boolean> {
    const result = await this.db.run("DELETE FROM locations WHERE id = ?", [id]);
    return changedRows(result) > 0;
  }

  async createCaptureJob(status: CaptureJobStatus = "recording"): Promise<CaptureJob> {
    const timestamp = nowText();
    const result = await this.db.run(
      "INSERT INTO capture_jobs (status, created_at, updated_at) VALUES (?, ?, ?)",
      [status, timestamp, timestamp],
    );
    const job = await this.getCaptureJob(lastInsertId(result));
    if (!job) throw new Error("SQLite did not return the inserted capture job.");
    return job;
  }

  async getCaptureJob(id: number): Promise<CaptureJob | null> {
    const result = await this.db.query("SELECT * FROM capture_jobs WHERE id = ?", [id]);
    return (result.values?.[0] as unknown as CaptureJob | undefined) ?? null;
  }

  async listActiveCaptureJobs(): Promise<CaptureJob[]> {
    const result = await this.db.query(
      `SELECT * FROM capture_jobs
       WHERE status IN ('recording','transcribing','saved_raw','enriching','failed')
       ORDER BY id DESC`,
    );
    return (result.values ?? []) as unknown as CaptureJob[];
  }

  async updateCaptureJob(id: number, patch: CaptureJobPatch): Promise<CaptureJob | null> {
    const entries = Object.entries(patch);
    if (!entries.length) return this.getCaptureJob(id);
    await this.db.run(
      `UPDATE capture_jobs SET ${entries.map(([key]) => `${key} = ?`).join(", ")},
       updated_at = ? WHERE id = ?`,
      [...entries.map(([, value]) => value), nowText(), id],
    );
    return this.getCaptureJob(id);
  }

  private async noteQuery(clause: string, values: unknown[]): Promise<Note[]> {
    const result = await this.db.query(
      `SELECT notes.*, locations.name AS location_name,
       locations.latitude AS location_latitude,
       locations.longitude AS location_longitude
       FROM notes LEFT JOIN locations ON locations.id = notes.location_id
       ${clause}
       ORDER BY notes.rank_score DESC,
       CASE WHEN notes.deadline_at IS NULL THEN 1 ELSE 0 END,
       notes.deadline_at ASC, notes.id DESC`,
      values,
    );
    return (result.values ?? []).map(rowToNote);
  }
}

function rowToNote(row: Record<string, unknown>): Note {
  const list = (value: unknown): number[] | null => {
    if (typeof value !== "string") return null;
    try {
      const parsed: unknown = JSON.parse(value);
      return Array.isArray(parsed) ? parsed.filter((item): item is number => Number.isInteger(item)) : null;
    } catch {
      return null;
    }
  };
  return {
    ...(row as unknown as Note),
    repeat_cycle: normalizeRepeatCycle(row.repeat_cycle),
    repeat_days: list(row.repeat_days),
    repeat_months: list(row.repeat_months),
  };
}

function lastInsertId(result: Awaited<ReturnType<SqliteDatabase["run"]>>): number {
  const changes = result.changes;
  return typeof changes === "object" ? Number(changes.lastId) : Number.NaN;
}

function changedRows(result: Awaited<ReturnType<SqliteDatabase["run"]>>): number {
  const changes = result.changes;
  return typeof changes === "number" ? changes : Number(changes?.changes ?? 0);
}
