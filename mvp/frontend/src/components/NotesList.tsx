import type { Note } from "../types/note";
import { NoteCard } from "./NoteCard";

interface Props {
  notes: Note[];
  onDelete: (id: number) => void;
  onToggleStatus: (id: number) => void;
  emptyMessage?: string;
}

export function NotesList({ notes, onDelete, onToggleStatus, emptyMessage = "No notes yet." }: Props) {
  if (notes.length === 0) {
    return <p className="empty">{emptyMessage}</p>;
  }

  return (
    <div className="notes-list">
      {notes.map((note) => (
        <NoteCard
          key={note.id}
          note={note}
          onDelete={onDelete}
          onToggleStatus={onToggleStatus}
        />
      ))}
    </div>
  );
}
