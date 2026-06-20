import { useState } from "react";
import { Link } from "react-router-dom";
import type { Note } from "../types/note";

interface Props {
  note: Note;
  onDelete: (id: number) => void;
  onToggleStatus: (id: number) => void;
  depth?: number;
}

export function NoteCard({ note, onDelete, onToggleStatus, depth = 0 }: Props) {
  const subnotes = note.subnotes ?? [];
  const hasSubnotes = subnotes.length > 0;
  const [isExpanded, setIsExpanded] = useState(true);
  const branchLabel = depth === 0 ? "Subnotes" : "Nested subnotes";
  const isDone = note.status === "done";

  return (
    <div className="note-card-shell" data-depth={depth} data-status={note.status}>
      <div className="note-card">
        <div className="note-card__header">
          <div className="note-card__meta">
            <span className={`note-category cat-${note.category.toLowerCase()}`}>
              {note.category}
            </span>
            {isDone ? <span className="note-status">Done</span> : null}
          </div>
          <div className="note-card__actions">
            <button
              className="status-btn"
              onClick={() => onToggleStatus(note.id)}
              aria-label={isDone ? "Mark note active" : "Mark note done"}
              type="button"
            >
              {isDone ? "Reopen" : "Done"}
            </button>
            <button
              className="delete-btn"
              onClick={() => onDelete(note.id)}
              aria-label="Delete note"
              type="button"
            >
              x
            </button>
          </div>
        </div>
        <Link to={`/notes/${note.id}`} className="note-card__link">
          <p className="note-text">{note.text}</p>
          <span className="note-date">{note.created_at}</span>
        </Link>
        {hasSubnotes ? (
          <button
            className="subnotes-toggle"
            onClick={() => setIsExpanded((current) => !current)}
            type="button"
          >
            {isExpanded ? "Hide" : "Show"} subnotes ({subnotes.length})
          </button>
        ) : null}
      </div>

      {hasSubnotes && isExpanded ? (
        <div className="subnotes-branch">
          <span className="subnotes-branch__label">
            {branchLabel} ({subnotes.length})
          </span>
          <div className="subnotes-list">
          {subnotes.map((subnote) => (
            <NoteCard
              key={subnote.id}
              note={subnote}
              onDelete={onDelete}
              onToggleStatus={onToggleStatus}
              depth={depth + 1}
            />
          ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
