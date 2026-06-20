import { useCallback } from "react";
import { deleteNote } from "../api/notesApi";
import { RecordButton } from "../components/RecordButton";
import { NotesList } from "../components/NotesList";
import { useNotes } from "../hooks/useNotes";
import { useRecording } from "../hooks/useRecording";
import type { RecordResult } from "../types/note";

export function HomePage() {
  const { notes, reload } = useNotes();

  const handleStopped = useCallback(
    async (result: RecordResult) => {
      if (!result.saved || result.id == null) return;
      await reload();
    },
    [reload],
  );

  const { state, handleStart, handleStop } = useRecording(handleStopped);

  async function handleDelete(id: number) {
    await deleteNote(id);
    await reload();
  }

  return (
    <div className="page">
      <RecordButton state={state} onStart={handleStart} onStop={handleStop} />
      <NotesList notes={notes} onDelete={handleDelete} />
    </div>
  );
}
