export type NoteStatus = "active" | "done";
export type NoteQueryStatus = NoteStatus | "all";

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
  saved: boolean;
}

export interface NoteStatusResult {
  id: number;
  status: NoteStatus;
}
