import { Link } from "react-router-dom";
import type { Note } from "../types/note";

interface Props {
  note: Note;
  onDelete: (id: number) => void;
}

export function NoteCard({ note, onDelete }: Props) {
  return (
    <div className="note-card">
      <div className="note-card__header">
        <span className={`note-category cat-${note.category.toLowerCase()}`}>
          {note.category}
        </span>
        <button
          className="delete-btn"
          onClick={() => onDelete(note.id)}
          aria-label="Delete note"
        >
          ✕
        </button>
      </div>
      <Link to={`/notes/${note.id}`} className="note-card__link">
        <p className="note-text">{note.text}</p>
        <span className="note-date">{note.created_at}</span>
      </Link>
    </div>
  );
}
