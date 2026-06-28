import type { Location } from "../types/note";

interface Props {
  locations: Location[];
  onDelete: (id: number) => void | Promise<void>;
}

function formatCoordinate(value: number) {
  return value.toFixed(5);
}

export function LocationsDebugPanel({ locations, onDelete }: Props) {
  return (
    <aside className="debug-panel" aria-label="Saved locations debug panel">
      <div className="debug-panel__header">
        <h2 className="section-title">Locations</h2>
        <span className="muted">{locations.length}</span>
      </div>

      {locations.length === 0 ? (
        <p className="empty debug-panel__empty">No saved locations.</p>
      ) : (
        <div className="debug-locations">
          {locations.map((location) => (
            <div key={location.id} className="debug-location">
              <div className="debug-location__topline">
                <div className="debug-location__name">@{location.name}</div>
                <button
                  className="delete-btn debug-location__delete"
                  onClick={() => onDelete(location.id)}
                  type="button"
                  aria-label={`Delete ${location.name} location`}
                >
                  x
                </button>
              </div>
              <div className="debug-location__coords">
                {formatCoordinate(location.latitude)}, {formatCoordinate(location.longitude)}
              </div>
              <div className="debug-location__date">Updated {location.updated_at}</div>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
