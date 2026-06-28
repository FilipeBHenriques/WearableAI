export type NoteStatus = "active" | "done";
export type NoteQueryStatus = NoteStatus | "all";

export interface Location {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  created_at: string;
  updated_at: string;
}

export interface Note {
  id: number;
  text: string;
  category: string;
  created_at: string;
  status: NoteStatus;
  parent_note_id: number | null;
  deadline_at: string | null;
  importance_score: number;
  urgency_score: number;
  rank_score: number;
  urgency_reason: string | null;
  location_id: number | null;
  location_name: string | null;
  location_latitude: number | null;
  location_longitude: number | null;
  subnotes?: Note[];
}

export interface RecordResult {
  id: number | null;
  text: string;
  category: string | null;
  created_at: string | null;
  status: NoteStatus;
  deadline_at: string | null;
  importance_score: number;
  urgency_score: number;
  rank_score: number;
  urgency_reason: string | null;
  location_id: number | null;
  location_name: string | null;
  location_latitude: number | null;
  location_longitude: number | null;
  saved: boolean;
  command_processed: boolean;
  command_type: string | null;
  message: string | null;
}

export interface NoteStatusResult {
  id: number;
  status: NoteStatus;
}
