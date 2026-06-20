export type NoteStatus = "active" | "done";
export type NoteQueryStatus = NoteStatus | "all";

export interface Note {
  id: number;
  text: string;
  category: string;
  created_at: string;
  status: NoteStatus;
  parent_note_id: number | null;
  subnotes?: Note[];
}

export interface RecordResult {
  id: number | null;
  text: string;
  category: string | null;
  created_at: string | null;
  status: NoteStatus;
  saved: boolean;
}

export interface NoteStatusResult {
  id: number;
  status: NoteStatus;
}
