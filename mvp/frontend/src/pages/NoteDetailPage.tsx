import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { deleteNote, fetchNote } from "../api/notesApi";
import { UrgencyBadges } from "../components/UrgencyBadges";
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
        <button className="back-btn" onClick={() => navigate("/")}>Back</button>
        <p className="muted">Note not found.</p>
      </div>
    );
  }

  if (!note) {
    return (
      <div className="page">
        <p className="muted">Loading...</p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="detail-header">
        <button className="back-btn" onClick={() => navigate(-1)}>Back</button>
        <button className="delete-btn" onClick={handleDelete}>Delete</button>
      </div>

      <span className={`note-category cat-${note.category.toLowerCase()}`}>
        {note.category}
      </span>

      <p className="detail-text">{note.text}</p>
      <span className="note-date">{note.created_at}</span>
      <UrgencyBadges note={note} />

      <section className="subnotes-section">
        <div className="subnotes-header">
          <h2 className="section-title">Subnotes</h2>
          <span className="muted">{note.subnotes?.length ?? 0}</span>
        </div>

        {!note.subnotes || note.subnotes.length === 0 ? (
          <p className="empty">No subnotes yet.</p>
        ) : (
          <div className="notes-list">
            {note.subnotes.map((subnote) => (
              <div key={subnote.id} className="note-card note-card--subnote">
                <span className={`note-category cat-${subnote.category.toLowerCase()}`}>
                  {subnote.category}
                </span>
                <p className="note-text">{subnote.text}</p>
                <span className="note-date">{subnote.created_at}</span>
                <UrgencyBadges note={subnote} />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
