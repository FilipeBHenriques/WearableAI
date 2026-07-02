import { useCallback, useEffect, useState } from "react";
import { fetchTodayRepeats } from "../api/notesApi";
import type { Note } from "../types/note";

export function useTodayRepeats() {
  const [todayRepeats, setTodayRepeats] = useState<Note[]>([]);

  const reloadRepeats = useCallback(async () => {
    try {
      setTodayRepeats(await fetchTodayRepeats());
    } catch {
      // Backend unavailable - keep last known list.
    }
  }, []);

  useEffect(() => {
    reloadRepeats();
  }, [reloadRepeats]);

  return { todayRepeats, reloadRepeats };
}
