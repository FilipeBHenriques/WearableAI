export interface Note {
  id: number;
  text: string;
  category: "Idea" | "Task" | "Reminder";
  created_at: string;
}

export interface RecordResult {
  text: string;
  category: string | null;
  saved: boolean;
}
