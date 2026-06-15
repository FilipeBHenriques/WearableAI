export interface Note {
  id: number;
  text: string;
  category: string;
  created_at: string;
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
}
