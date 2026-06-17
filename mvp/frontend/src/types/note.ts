export interface Note {
  id: number;
  text: string;
  category: string;
  created_at: string;
  parent_note_id: number | null;
  subnotes?: Note[];
}

export interface RecordResult {
  id: number | null;
  text: string;
  category: string | null;
  created_at: string | null;
  saved: boolean;
}

export interface CategorizeResult {
  id: number;
  category: string;
  parent_note_id: number | null;
}
