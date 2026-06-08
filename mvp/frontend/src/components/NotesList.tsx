import type { Note } from "../types/note";
import { NoteCard } from "./NoteCard";

interface Props {
  notes: Note[];
  onDelete: (id: number) => void;
}

export function NotesList({ notes, onDelete }: Props) {
  if (notes.length === 0) {
    return <p className="empty">No notes yet.</p>;
  }

  return (
    <div className="notes-list">
      {notes.map((note) => (
        <NoteCard key={note.id} note={note} onDelete={onDelete} />
      ))}
    </div>
  );
}
