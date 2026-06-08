import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { deleteNote, fetchNote } from "../api/notesApi";
import type { Note } from "../types/note";

export function NoteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [note, setNote] = useState<Note | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!id) return;
    fetchNote(Number(id))
      .then(setNote)
      .catch(() => setNotFound(true));
  }, [id]);

  async function handleDelete() {
    if (!note) return;
    await deleteNote(note.id);
    navigate("/");
  }

  if (notFound) {
    return (
      <div className="page">
        <button className="back-btn" onClick={() => navigate("/")}>← Back</button>
        <p className="muted">Note not found.</p>
      </div>
    );
  }

  if (!note) {
    return (
      <div className="page">
        <p className="muted">Loading…</p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="detail-header">
        <button className="back-btn" onClick={() => navigate(-1)}>← Back</button>
        <button className="delete-btn" onClick={handleDelete}>Delete</button>
      </div>

      <span className={`note-category cat-${note.category.toLowerCase()}`}>
        {note.category}
      </span>

      <p className="detail-text">{note.text}</p>

      <span className="note-date">{note.created_at}</span>
    </div>
  );
}
