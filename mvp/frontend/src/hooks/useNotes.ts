import { useCallback, useEffect, useState } from "react";
import { fetchNotes } from "../api/notesApi";
import type { Note } from "../types/note";

export function useNotes() {
  const [notes, setNotes] = useState<Note[]>([]);

  const reload = useCallback(async () => {
    try {
      setNotes(await fetchNotes());
    } catch {
      // Backend unavailable — keep last known list.
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { notes, reload };
}
