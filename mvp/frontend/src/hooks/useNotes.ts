import { useCallback, useEffect, useState } from "react";
import { fetchNotes } from "../api/notesApi";
import type { Note } from "../types/note";

export function useNotes() {
  const [activeNotes, setActiveNotes] = useState<Note[]>([]);
  const [doneNotes, setDoneNotes] = useState<Note[]>([]);

  const reload = useCallback(async () => {
    try {
      const [active, done] = await Promise.all([
        fetchNotes("active"),
        fetchNotes("done"),
      ]);
      setActiveNotes(active);
      setDoneNotes(done);
    } catch {
      // Backend unavailable — keep last known list.
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { notes: activeNotes, activeNotes, doneNotes, reload };
}
