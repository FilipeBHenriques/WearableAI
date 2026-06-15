import { useRef, useState } from "react";
import { startRecording, stopRecording } from "../api/notesApi";
import type { RecordResult } from "../types/note";

export type RecordState = "idle" | "recording" | "processing";

export function useRecording(
  onStopped: (result: RecordResult) => void | Promise<void>,
) {
  const [state, setState] = useState<RecordState>("idle");
  const stateRef = useRef<RecordState>("idle");

  function setRecordState(next: RecordState) {
    stateRef.current = next;
    setState(next);
  }

  async function handleStart() {
    if (stateRef.current !== "idle") return;
    setRecordState("recording");
    try {
      await startRecording();
    } catch {
      setRecordState("idle");
    }
  }

  async function handleStop() {
    if (stateRef.current !== "recording") return;
    setRecordState("processing");

    try {
      const result = await stopRecording();
      await onStopped(result);
    } catch {
      // stop failed
    } finally {
      setRecordState("idle");
    }
  }

  return { state, handleStart, handleStop };
}
