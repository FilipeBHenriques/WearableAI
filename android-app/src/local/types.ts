export type NoteStatus = "active" | "done" | `repeat_done:${string}`;
export type RepeatCycle = "daily" | "weekly" | "monthly" | "yearly";
export type CaptureJobStatus =
  | "recording"
  | "transcribing"
  | "saved_raw"
  | "enriching"
  | "ready"
  | "failed";

export interface Coordinates {
  latitude: number;
  longitude: number;
}

export interface Location extends Coordinates {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
}

/** Persisted/serialized shape intentionally matches the Python frontend API. */
export interface Note {
  id: number;
  text: string;
  category: string;
  created_at: string;
  status: NoteStatus;
  parent_note_id: number | null;
  deadline_at: string | null;
  urgency_score: number;
  rank_score: number;
  urgency_reason: string | null;
  location_id: number | null;
  location_name: string | null;
  location_latitude: number | null;
  location_longitude: number | null;
  repeat_cycle: RepeatCycle | null;
  repeat_days: number[] | null;
  repeat_months: number[] | null;
  repeat_time: string | null;
  estimated_duration_minutes: number | null;
  audio_path: string | null;
}

export interface NoteView extends Note {
  is_repeating: boolean;
  is_due_today: boolean;
  completed_today: boolean;
  repeat_display: string | null;
  audio_url: string | null;
  subnotes?: NoteView[];
}

export interface CaptureJob {
  id: number;
  status: CaptureJobStatus;
  final_transcript: string | null;
  note_id: number | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface CaptureResult
  extends Partial<
    Omit<
      NoteView,
      | "text"
      | "category"
      | "status"
      | "urgency_score"
      | "rank_score"
      | "is_repeating"
      | "is_due_today"
      | "completed_today"
    >
  > {
  text: string;
  category: string | null;
  status: NoteStatus;
  urgency_score: number;
  rank_score: number;
  is_repeating: boolean;
  is_due_today: boolean;
  completed_today: boolean;
  saved: boolean;
  command_processed: boolean;
  command_type: string | null;
  message: string | null;
}

export interface NativeAi {
  isAvailable?(): Promise<boolean>;
  transcribe(audio: AudioCapture): Promise<string>;
  embed(texts: string[]): Promise<number[][]>;
  generateJson<T extends object>(prompt: string): Promise<T>;
}

export interface AudioCapture {
  /** Browser captures may carry bytes; native captures stay path-backed. */
  data?: Uint8Array;
  native_path?: string;
  uri?: string;
  mime_type?: string;
  duration_ms?: number;
}

export interface AudioProvider {
  start(): Promise<void>;
  stop(): Promise<AudioCapture>;
  saveForNote?(audio: AudioCapture, noteId: number): Promise<string | null>;
  delete?(path: string): Promise<void>;
}

export interface LocationProvider {
  getCurrentCoordinates(): Promise<Coordinates>;
}

export type Unsubscribe = () => void;

export interface DomainEvents {
  notes_changed: { note_id?: number; note_ids?: number[]; stage?: string; reason?: string };
  locations_changed: { location_id: number };
  capture_job: CaptureJob;
  gps_suggestions: {
    location: Location | null;
    coordinates: Coordinates;
    notes: Note[];
  };
}

export interface RecordingJobResult {
  job_id: number;
  status: CaptureJobStatus;
}

export interface DeleteResult {
  deleted: number;
}

export interface StatusResult {
  id: number;
  status: NoteStatus;
}

export interface LocalHealth {
  storage: "local";
  native_ai_available: boolean;
  native_ai_error: string | null;
}

export interface ProximitySuggestion {
  location: Location;
  distance_meters: number;
  notes: Note[];
}

export const ACTIVE_STATUS = "active";
export const DONE_STATUS = "done";
export const PENDING_CATEGORY = "Uncategorized";

export function nowText(date = new Date()): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 19).replace("T", " ");
}

export function emptyCaptureResult(text = ""): CaptureResult {
  return {
    text,
    category: null,
    status: ACTIVE_STATUS,
    urgency_score: 0,
    rank_score: 0,
    is_repeating: false,
    is_due_today: false,
    completed_today: false,
    saved: false,
    command_processed: false,
    command_type: null,
    message: null,
  };
}
