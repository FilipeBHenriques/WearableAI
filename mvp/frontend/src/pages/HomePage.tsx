import { useCallback, useEffect, useState } from "react";
import { deleteLocation, deleteNote, fetchLocations, toggleNoteStatus } from "../api/notesApi";
import { LocationsDebugPanel } from "../components/LocationsDebugPanel";
import { RecordButton } from "../components/RecordButton";
import { NotesList } from "../components/NotesList";
import { useNotes } from "../hooks/useNotes";
import { useRecording } from "../hooks/useRecording";
import type { Location, RecordResult } from "../types/note";

export function HomePage() {
  const { activeNotes, doneNotes, reload } = useNotes();
  const [locations, setLocations] = useState<Location[]>([]);

  const reloadLocations = useCallback(async () => {
    const savedLocations = await fetchLocations();
    setLocations(savedLocations);
  }, []);

  useEffect(() => {
    reloadLocations().catch(() => {
      setLocations([]);
    });
  }, [reloadLocations]);

  const handleStopped = useCallback(
    async (result: RecordResult) => {
      await reloadLocations();
      if (!result.saved || result.id == null) return;
      await reload();
    },
    [reload, reloadLocations],
  );

  const { state, handleStart, handleStop } = useRecording(handleStopped);

  async function handleDelete(id: number) {
    await deleteNote(id);
    await reload();
    await reloadLocations();
  }

  async function handleDeleteLocation(id: number) {
    await deleteLocation(id);
    await reloadLocations();
    await reload();
  }

  async function handleToggleStatus(id: number) {
    await toggleNoteStatus(id);
    await reload();
  }

  return (
    <div className="app-shell">
      <main className="page">
        <RecordButton state={state} onStart={handleStart} onStop={handleStop} />
        <section className="notes-section">
          <div className="notes-section__header">
            <h2 className="section-title">Active</h2>
            <span className="muted">{activeNotes.length}</span>
          </div>
          <NotesList
            notes={activeNotes}
            onDelete={handleDelete}
            onToggleStatus={handleToggleStatus}
            emptyMessage="No active notes."
          />
        </section>

        <section className="notes-section">
          <div className="notes-section__header">
            <h2 className="section-title">Done</h2>
            <span className="muted">{doneNotes.length}</span>
          </div>
          <NotesList
            notes={doneNotes}
            onDelete={handleDelete}
            onToggleStatus={handleToggleStatus}
            emptyMessage="No done notes."
          />
        </section>
      </main>
      <LocationsDebugPanel locations={locations} onDelete={handleDeleteLocation} />
    </div>
  );
}
