import type {
  CaptureJob,
  CaptureJobStatus,
  Location,
  Note,
  NoteStatus,
  RepeatCycle,
} from "./types";

export type NotePatch = Partial<
  Pick<
    Note,
    | "category"
    | "status"
    | "parent_note_id"
    | "deadline_at"
    | "urgency_score"
    | "rank_score"
    | "urgency_reason"
    | "location_id"
    | "repeat_cycle"
    | "repeat_days"
    | "repeat_months"
    | "repeat_time"
    | "estimated_duration_minutes"
    | "audio_path"
  >
>;

export type CaptureJobPatch = Partial<
  Pick<CaptureJob, "status" | "final_transcript" | "note_id" | "error">
>;

export interface LocalRepository {
  initialize(): Promise<void>;

  createNote(text: string, category?: string): Promise<Note>;
  getNote(id: number): Promise<Note | null>;
  listNotes(status?: NoteStatus | null): Promise<Note[]>;
  listChildNotes(parentId: number, status?: NoteStatus | null): Promise<Note[]>;
  updateNote(id: number, patch: NotePatch): Promise<Note | null>;
  deleteNotes(ids: number[]): Promise<void>;

  upsertLocation(name: string, latitude: number, longitude: number): Promise<Location>;
  listLocations(): Promise<Location[]>;
  deleteLocation(id: number): Promise<boolean>;

  createCaptureJob(status?: CaptureJobStatus): Promise<CaptureJob>;
  getCaptureJob(id: number): Promise<CaptureJob | null>;
  listActiveCaptureJobs(): Promise<CaptureJob[]>;
  updateCaptureJob(id: number, patch: CaptureJobPatch): Promise<CaptureJob | null>;
}

export async function assertValidParent(
  repository: Pick<LocalRepository, "getNote">,
  noteId: number,
  parentId: number | null,
): Promise<void> {
  if (parentId == null) return;
  if (parentId === noteId) throw new Error("A note cannot be its own parent.");
  const visited = new Set<number>([noteId]);
  let current: number | null = parentId;
  while (current != null) {
    if (visited.has(current)) throw new Error("A note hierarchy cannot contain a cycle.");
    visited.add(current);
    const parent = await repository.getNote(current);
    if (!parent) throw new Error(`Parent note ${current} does not exist.`);
    current = parent.parent_note_id;
  }
}

export function newNote(
  id: number,
  text: string,
  category: string,
  createdAt: string,
): Note {
  return {
    id,
    text,
    category,
    created_at: createdAt,
    status: "active",
    parent_note_id: null,
    deadline_at: null,
    urgency_score: 0,
    rank_score: 0,
    urgency_reason: null,
    location_id: null,
    location_name: null,
    location_latitude: null,
    location_longitude: null,
    repeat_cycle: null,
    repeat_days: null,
    repeat_months: null,
    repeat_time: null,
    estimated_duration_minutes: null,
    audio_path: null,
  };
}

export function normalizeRepeatCycle(value: unknown): RepeatCycle | null {
  return value === "daily" || value === "weekly" || value === "monthly" || value === "yearly"
    ? value
    : null;
}
