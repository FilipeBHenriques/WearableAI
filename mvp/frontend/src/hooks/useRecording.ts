import { useRef, useState } from "react";
import { startRecording, stopRecording } from "../api/notesApi";
import type { RecordingJobResult } from "../types/note";

export type RecordState = "idle" | "recording" | "processing";

export function useRecording(
  onStopped: (result: RecordingJobResult) => void | Promise<void>,
) {
  const [state, setState] = useState<RecordState>("idle");
  const stateRef = useRef<RecordState>("idle");
  const jobIdRef = useRef<number | null>(null);

  function setRecordState(next: RecordState) {
    stateRef.current = next;
    setState(next);
  }

  async function handleStart() {
    if (stateRef.current !== "idle") return;
    setRecordState("recording");
    try {
      const result = await startRecording();
      jobIdRef.current = result.job_id;
    } catch {
      jobIdRef.current = null;
      setRecordState("idle");
    }
  }

  async function handleStop() {
    if (stateRef.current !== "recording") return;
    setRecordState("processing");

    try {
      const result = await stopRecording();
      jobIdRef.current = null;
      await onStopped(result);
    } catch {
      // stop failed
      jobIdRef.current = null;
    } finally {
      setRecordState("idle");
    }
  }

  return { state, jobId: jobIdRef.current, handleStart, handleStop };
}
