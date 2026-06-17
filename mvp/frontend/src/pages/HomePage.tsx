import { useCallback } from "react";
import { categorizeNote, deleteNote, submitText } from "../api/notesApi";
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

      void categorizeNote(result.id).then(() => reload());
    },
    [reload],
  );

  const { state, handleStart, handleStop } = useRecording(handleStopped);

  async function handleDelete(id: number) {
    await deleteNote(id);
    await reload();
  }

  async function handleAddRandomSubnote() {
    if (notes.length === 0) return;

    const result = await submitText("Quick random subnote");

    if (!result.saved || result.id == null) return;

    await categorizeNote(result.id, true);
    await reload();
  }

  return (
    <div className="page">
      <RecordButton state={state} onStart={handleStart} onStop={handleStop} />
      <button
        className="secondary-btn"
        onClick={handleAddRandomSubnote}
        disabled={notes.length === 0}
      >
        Add Random Subnote
      </button>
      <NotesList notes={notes} onDelete={handleDelete} />
    </div>
  );
}
