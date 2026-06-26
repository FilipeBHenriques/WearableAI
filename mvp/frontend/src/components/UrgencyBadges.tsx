import type { Note } from "../types/note";

interface Props {
  note: Pick<Note, "deadline_at" | "importance_score" | "urgency_score" | "urgency_reason">;
}

function formatDeadline(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function UrgencyBadges({ note }: Props) {
  return (
    <div className="urgency-badges" aria-label="Urgency details">
      {note.deadline_at ? (
        <span className="urgency-badge urgency-badge--deadline">
          Due {formatDeadline(note.deadline_at)}
        </span>
      ) : null}
      <span className="urgency-badge">Importance {note.importance_score}</span>
      <span className="urgency-badge">Urgency {note.urgency_score}</span>
      {note.urgency_reason ? (
        <span className="urgency-badge urgency-badge--reason">
          {note.urgency_reason}
        </span>
      ) : null}
    </div>
  );
}
