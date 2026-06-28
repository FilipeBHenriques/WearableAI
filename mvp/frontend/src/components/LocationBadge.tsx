import type { Note } from "../types/note";

interface Props {
  note: Pick<Note, "location_name" | "location_latitude" | "location_longitude">;
}

function formatCoordinate(value: number | null) {
  if (value == null) return null;
  return value.toFixed(5);
}

export function LocationBadge({ note }: Props) {
  if (!note.location_name) return null;

  const latitude = formatCoordinate(note.location_latitude);
  const longitude = formatCoordinate(note.location_longitude);
  const coordinates = latitude && longitude ? `${latitude}, ${longitude}` : null;

  return (
    <div className="location-badge" title={coordinates ?? note.location_name}>
      <span className="location-badge__pin" aria-hidden="true">+</span>
      <span className="location-badge__name">@{note.location_name}</span>
      {coordinates ? <span className="location-badge__coords">{coordinates}</span> : null}
    </div>
  );
}
