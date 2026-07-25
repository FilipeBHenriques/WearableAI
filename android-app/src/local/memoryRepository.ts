import type { CaptureJobPatch, LocalRepository, NotePatch } from "./repository";
import { assertValidParent, newNote } from "./repository";
import {
  nowText,
  PENDING_CATEGORY,
  type CaptureJob,
  type CaptureJobStatus,
  type Location,
  type Note,
  type NoteStatus,
} from "./types";

const clone = <T>(value: T): T => structuredClone(value);

export class InMemoryRepository implements LocalRepository {
  private notes = new Map<number, Note>();
  private locations = new Map<number, Location>();
  private jobs = new Map<number, CaptureJob>();
  private nextNoteId = 1;
  private nextLocationId = 1;
  private nextJobId = 1;

  async initialize(): Promise<void> {}

  async createNote(text: string, category = PENDING_CATEGORY): Promise<Note> {
    const note = newNote(this.nextNoteId++, text, category, nowText().slice(0, 16));
    this.notes.set(note.id, note);
    return clone(note);
  }

  async getNote(id: number): Promise<Note | null> {
    return this.hydrate(this.notes.get(id));
  }

  async listNotes(status?: NoteStatus | null): Promise<Note[]> {
    return [...this.notes.values()]
      .filter((note) => status == null || note.status === status)
      .sort(noteOrder)
      .map((note) => this.hydrate(note)!);
  }

  async listChildNotes(parentId: number, status?: NoteStatus | null): Promise<Note[]> {
    return (await this.listNotes(status)).filter((note) => note.parent_note_id === parentId);
  }

  async updateNote(id: number, patch: NotePatch): Promise<Note | null> {
    const note = this.notes.get(id);
    if (!note) return null;
    if ("parent_note_id" in patch)
      await assertValidParent(this, id, patch.parent_note_id ?? null);
    Object.assign(note, clone(patch));
    return this.hydrate(note);
  }

  async deleteNotes(ids: number[]): Promise<void> {
    for (const id of ids) this.notes.delete(id);
    for (const job of this.jobs.values()) {
      if (job.note_id != null && ids.includes(job.note_id)) job.note_id = null;
    }
  }

  async upsertLocation(name: string, latitude: number, longitude: number): Promise<Location> {
    const normalized = name.trim();
    const existing = [...this.locations.values()].find((item) => item.name === normalized);
    const timestamp = nowText().slice(0, 16);
    if (existing) {
      Object.assign(existing, { latitude, longitude, updated_at: timestamp });
      return clone(existing);
    }
    const location: Location = {
      id: this.nextLocationId++,
      name: normalized,
      latitude,
      longitude,
      created_at: timestamp,
      updated_at: timestamp,
    };
    this.locations.set(location.id, location);
    return clone(location);
  }

  async listLocations(): Promise<Location[]> {
    return [...this.locations.values()]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map(clone);
  }

  async deleteLocation(id: number): Promise<boolean> {
    if (!this.locations.delete(id)) return false;
    for (const note of this.notes.values()) {
      if (note.location_id === id) {
        note.location_id = null;
        note.location_name = null;
        note.location_latitude = null;
        note.location_longitude = null;
      }
    }
    return true;
  }

  async createCaptureJob(status: CaptureJobStatus = "recording"): Promise<CaptureJob> {
    const timestamp = nowText();
    const job: CaptureJob = {
      id: this.nextJobId++,
      status,
      final_transcript: null,
      note_id: null,
      error: null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    this.jobs.set(job.id, job);
    return clone(job);
  }

  async getCaptureJob(id: number): Promise<CaptureJob | null> {
    const job = this.jobs.get(id);
    return job ? clone(job) : null;
  }

  async listActiveCaptureJobs(): Promise<CaptureJob[]> {
    const active = new Set<CaptureJobStatus>([
      "recording",
      "transcribing",
      "saved_raw",
      "enriching",
      "failed",
    ]);
    return [...this.jobs.values()]
      .filter((job) => active.has(job.status))
      .sort((a, b) => b.id - a.id)
      .map(clone);
  }

  async updateCaptureJob(id: number, patch: CaptureJobPatch): Promise<CaptureJob | null> {
    const job = this.jobs.get(id);
    if (!job) return null;
    Object.assign(job, clone(patch), { updated_at: nowText() });
    return clone(job);
  }

  private hydrate(note?: Note): Note | null {
    if (!note) return null;
    const result = clone(note);
    const location = result.location_id == null ? undefined : this.locations.get(result.location_id);
    result.location_name = location?.name ?? null;
    result.location_latitude = location?.latitude ?? null;
    result.location_longitude = location?.longitude ?? null;
    return result;
  }
}

function noteOrder(a: Note, b: Note): number {
  return (
    b.rank_score - a.rank_score ||
    Number(a.deadline_at == null) - Number(b.deadline_at == null) ||
    (a.deadline_at ?? "").localeCompare(b.deadline_at ?? "") ||
    b.id - a.id
  );
}
