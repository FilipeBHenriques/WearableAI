import { useState } from "react";
import { startRecording, stopRecording } from "../api/notesApi";
import type { RecordResult } from "../types/note";

export type RecordState = "idle" | "recording" | "processing";

export function useRecording(onResult: (result: RecordResult) => void) {
  const [state, setState] = useState<RecordState>("idle");

  async function handleStart() {
    if (state !== "idle") return;
    setState("recording");
    try {
      await startRecording();
    } catch {
      setState("idle");
    }
  }

  async function handleStop() {
    if (state !== "recording") return;
    setState("processing");
    try {
      const result = await stopRecording();
      onResult(result);
    } catch {
      onResult({ text: "", category: null, saved: false });
    } finally {
      setState("idle");
    }
  }

  return { state, handleStart, handleStop };
}
