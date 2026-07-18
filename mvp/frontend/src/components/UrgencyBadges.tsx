import type { Note } from "../types/note";

interface Props {
  note: Pick<
    Note,
    | "deadline_at"
    | "importance_score"
    | "urgency_score"
    | "urgency_reason"
    | "estimated_duration_minutes"
  >;
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

function formatDuration(minutes: number) {
  if (minutes <= 0) return "Est. —";
  if (minutes < 60) return `Est. ${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (remainder === 0) return `Est. ${hours}h`;
  return `Est. ${hours}h ${remainder}m`;
}

export function UrgencyBadges({ note }: Props) {
  return (
    <div className="urgency-badges" aria-label="Urgency details">
      {note.deadline_at ? (
        <span className="urgency-badge urgency-badge--deadline">
          Due {formatDeadline(note.deadline_at)}
        </span>
      ) : null}
      {note.estimated_duration_minutes != null ? (
        <span className="urgency-badge urgency-badge--duration">
          {formatDuration(note.estimated_duration_minutes)}
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
