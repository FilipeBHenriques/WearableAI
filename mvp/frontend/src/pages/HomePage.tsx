import { useEffect, useState } from "react";
import { deleteNote, fetchNotes } from "../api/notesApi";
import { RecordButton } from "../components/RecordButton";
import { NotesList } from "../components/NotesList";
import { useRecording } from "../hooks/useRecording";
import type { Note } from "../types/note";

export function HomePage() {
  const [notes, setNotes] = useState<Note[]>([]);

  async function loadNotes() {
    const data = await fetchNotes();
    setNotes(data);
  }

  useEffect(() => {
    loadNotes();
  }, []);

  const { state, handleStart, handleStop } = useRecording(async (result) => {
    if (result.saved) {
      await loadNotes();
    }
  });

  async function handleDelete(id: number) {
    await deleteNote(id);
    await loadNotes();
  }

  return (
    <div className="page">
      <RecordButton state={state} onStart={handleStart} onStop={handleStop} />
      <NotesList notes={notes} onDelete={handleDelete} />
    </div>
  );
}
