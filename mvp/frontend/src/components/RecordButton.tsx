import type { RecordState } from "../hooks/useRecording";

const LABELS: Record<RecordState, string> = {
  idle: "HOLD TO RECORD",
  recording: "● RECORDING…",
  processing: "PROCESSING…",
};

interface Props {
  state: RecordState;
  onStart: () => void;
  onStop: () => void;
}

export function RecordButton({ state, onStart, onStop }: Props) {
  function handleMouseLeave() {
    if (state === "recording") onStop();
  }

  return (
    <button
      className={`record-btn record-btn--${state}`}
      disabled={state === "processing"}
      onMouseDown={onStart}
      onMouseUp={onStop}
      onMouseLeave={handleMouseLeave}
      onTouchStart={(e) => {
        e.preventDefault();
        onStart();
      }}
      onTouchEnd={onStop}
    >
      {LABELS[state]}
    </button>
  );
}
