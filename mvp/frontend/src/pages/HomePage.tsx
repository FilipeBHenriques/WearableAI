import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  deleteLocation,
  deleteNote,
  fetchLocations,
  fetchNotes,
  toggleNoteStatus,
} from "../api/notesApi";
import { LocationBadge } from "../components/LocationBadge";
import { LocationsDebugPanel } from "../components/LocationsDebugPanel";
import { RecordButton } from "../components/RecordButton";
import { UrgencyBadges } from "../components/UrgencyBadges";
import { useNotes } from "../hooks/useNotes";
import { useRecording } from "../hooks/useRecording";
import { useTodayRepeats } from "../hooks/useTodayRepeats";
import type { Location, Note, RecordResult } from "../types/note";

type Screen = "main" | "notes" | "locations";
type NotesMode = "notes" | "goals";

interface TimetableItem {
  id: string;
  time: string;
  title: string;
  type: string;
}

export function HomePage() {
  const { activeNotes, reload } = useNotes();
  const { todayRepeats, reloadRepeats } = useTodayRepeats();
  const [allNotes, setAllNotes] = useState<Note[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [screen, setScreen] = useState<Screen>("main");
  const [notesMode, setNotesMode] = useState<NotesMode>("notes");
  const [selectedNoteId, setSelectedNoteId] = useState<number | null>(null);

  const flatNotes = useMemo(() => flattenNotes(allNotes), [allNotes]);
  const selectedNote = selectedNoteId == null ? null : flatNotes.find((note) => note.id === selectedNoteId) ?? null;
  const normalNotes = allNotes.filter((note) => !note.is_repeating);
  const goals = flatNotes.filter((note) => note.is_repeating);
  const suggestions = activeNotes
    .sort(sortByRank)
    .slice(0, 5);

  const timetableItems = useMemo<TimetableItem[]>(() => {
    const repeatItems = todayRepeats
      .filter((note) => note.repeat_time)
      .map((note) => ({
        id: `repeat-${note.id}`,
        time: note.repeat_time ?? "All day",
        title: note.text,
        type: note.completed_today ? "goal done" : "goal",
      }));

    const deadlineItems = activeNotes
      .filter((note) => note.deadline_at && !note.is_repeating)
      .map((note) => ({
        id: `deadline-${note.id}`,
        time: formatTime(note.deadline_at),
        title: note.text,
        type: note.category.toLowerCase(),
      }));

    return [...repeatItems, ...deadlineItems].sort((a, b) => a.time.localeCompare(b.time));
  }, [activeNotes, todayRepeats]);

  const reloadAllNotes = useCallback(async () => {
    setAllNotes(await fetchNotes("all"));
  }, []);

  const reloadEverything = useCallback(async () => {
    await Promise.all([reload(), reloadRepeats(), reloadAllNotes()]);
  }, [reload, reloadAllNotes, reloadRepeats]);

  const reloadLocations = useCallback(async () => {
    setLocations(await fetchLocations());
  }, []);

  useEffect(() => {
    reloadAllNotes().catch(() => setAllNotes([]));
    reloadLocations().catch(() => setLocations([]));
  }, [reloadAllNotes, reloadLocations]);

  const handleStopped = useCallback(
    async (result: RecordResult) => {
      await reloadLocations();
      if (!result.saved || result.id == null) return;
      await reloadEverything();
    },
    [reloadEverything, reloadLocations],
  );

  const { state, handleStart, handleStop } = useRecording(handleStopped);

  async function handleDelete(id: number) {
    await deleteNote(id);
    if (selectedNoteId === id) setSelectedNoteId(null);
    await reloadEverything();
    await reloadLocations();
  }

  async function handleDeleteLocation(id: number) {
    await deleteLocation(id);
    await reloadLocations();
    await reloadEverything();
  }

  async function handleToggleStatus(id: number) {
    await toggleNoteStatus(id);
    await reloadEverything();
  }

  function openNote(noteId: number) {
    setSelectedNoteId(noteId);
    setScreen("notes");
  }

  return (
    <main className="device">
      <div className="shell shell--simple">
        <section className="screen">
          <header className="topbar">
            <div className="brand">LOCAL-MEM OS</div>
            <nav className="tabs" aria-label="Main sections">
              {(["main", "notes", "locations"] as Screen[]).map((item) => (
                <button
                  key={item}
                  className={screen === item ? "active" : ""}
                  onClick={() => {
                    setScreen(item);
                    setSelectedNoteId(null);
                  }}
                  type="button"
                >
                  {item.toUpperCase()}
                </button>
              ))}
            </nav>
            <div className="status">OFFLINE</div>
          </header>

          <div className="content">
            {screen === "main" ? (
              <div className="grid main-grid">
                <Panel title="TODAY">
                  <div className="date">{formatToday()}</div>
                  <div className="list">
                    {todayRepeats.length === 0 ? (
                      <p className="empty">No goals due today.</p>
                    ) : (
                      todayRepeats.map((note) => (
                        <TaskRow
                          key={note.id}
                          note={note}
                          onOpen={openNote}
                          onToggle={handleToggleStatus}
                        />
                      ))
                    )}
                  </div>
                </Panel>

                <Panel title="TIMETABLE">
                  <div className="timeline">
                    {timetableItems.length === 0 ? (
                      <p className="empty">No timed items.</p>
                    ) : (
                      timetableItems.map((item) => (
                        <button className="time-row time-row--button" key={item.id} type="button">
                          <span>{item.time}</span>
                          <div>
                            {item.title}
                            <small>{item.type}</small>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </Panel>

                <Panel title="SUGGESTIONS">
                  <SuggestionList notes={suggestions} onOpen={openNote} empty="No suggestions yet." />
                </Panel>
              </div>
            ) : null}

            {screen === "notes" ? (
              selectedNote ? (
                <NoteDetail
                  note={selectedNote}
                  onBack={() => setSelectedNoteId(null)}
                  onOpen={openNote}
                  onDelete={handleDelete}
                  onToggle={handleToggleStatus}
                />
              ) : (
                <div className="notes-screen">
                  <div className="subtabs">
                    {(["notes", "goals"] as NotesMode[]).map((item) => (
                      <button
                        key={item}
                        className={notesMode === item ? "active" : ""}
                        onClick={() => setNotesMode(item)}
                        type="button"
                      >
                        {item.toUpperCase()}
                      </button>
                    ))}
                  </div>

                  {notesMode === "notes" ? (
                    <Panel title="NOTES">
                      <div className="notes-tree">
                        {normalNotes.length === 0 ? (
                          <p className="empty">No notes yet.</p>
                        ) : (
                          normalNotes.map((note) => (
                            <NoteTreeItem
                              key={note.id}
                              note={note}
                              onOpen={openNote}
                              onDelete={handleDelete}
                              onToggle={handleToggleStatus}
                            />
                          ))
                        )}
                      </div>
                    </Panel>
                  ) : (
                    <Panel title="GOALS">
                      <div className="notes-tree">
                        {goals.length === 0 ? (
                          <p className="empty">No goals yet.</p>
                        ) : (
                          goals.map((note) => (
                            <GoalItem
                              key={note.id}
                              note={note}
                              onOpen={openNote}
                              onDelete={handleDelete}
                              onToggle={handleToggleStatus}
                            />
                          ))
                        )}
                      </div>
                    </Panel>
                  )}
                </div>
              )
            ) : null}

            {screen === "locations" ? (
              <Panel title="LOCATIONS">
                <LocationsDebugPanel locations={locations} onDelete={handleDeleteLocation} />
              </Panel>
            ) : null}
          </div>
        </section>

        <aside className="hardware-rec">
          <RecordButton state={state} onStart={handleStart} onStop={handleStop} />
        </aside>
      </div>
    </main>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="panel"><h1>{title}</h1>{children}</section>;
}

function TaskRow({
  note,
  onOpen,
  onToggle,
}: {
  note: Note;
  onOpen: (id: number) => void;
  onToggle: (id: number) => void;
}) {
  return (
    <div className="row">
      <button className={note.completed_today ? "check done" : "check"} onClick={() => onToggle(note.id)} type="button">
        {note.completed_today ? "■" : "□"}
      </button>
      <button className="row-main" onClick={() => onOpen(note.id)} type="button">
        <strong>{note.text}</strong>
        <small>{note.repeat_display ?? note.created_at}</small>
      </button>
      <span className="tag">GOAL</span>
    </div>
  );
}

function SuggestionList({ notes, onOpen, empty }: { notes: Note[]; onOpen: (id: number) => void; empty: string }) {
  if (notes.length === 0) return <p className="empty">{empty}</p>;

  return (
    <div className="list">
      {notes.map((note) => (
        <button key={note.id} className="suggestion-item" onClick={() => onOpen(note.id)} type="button">
          <span>{displayCategory(note)}</span>
          <strong>{note.text}</strong>
          <small>{note.urgency_reason ?? note.deadline_at ?? note.created_at}</small>
        </button>
      ))}
    </div>
  );
}

function NoteTreeItem({
  note,
  onOpen,
  onDelete,
  onToggle,
  depth = 0,
}: {
  note: Note;
  onOpen: (id: number) => void;
  onDelete: (id: number) => void;
  onToggle: (id: number) => void;
  depth?: number;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const children = (note.subnotes ?? []).filter((child) => !child.is_repeating);
  const childCount = children.length;

  return (
    <div className="note-tree-item" data-depth={depth}>
      <div className="note-row">
        <button className="note-row__main" onClick={() => onOpen(note.id)} type="button">
          <span className={`note-category ${categoryClass(displayCategory(note))}`}>{displayCategory(note)}</span>
          <strong>{note.text}</strong>
          <small>{note.status === "done" ? "Done" : note.created_at}</small>
        </button>
        <button className="status-btn" onClick={() => onToggle(note.id)} type="button">
          {note.status === "done" ? "Reopen" : "Done"}
        </button>
        <button className="delete-btn" onClick={() => onDelete(note.id)} type="button">x</button>
      </div>

      {childCount > 0 ? (
        <button className="children-toggle" onClick={() => setIsExpanded((current) => !current)} type="button">
          {isExpanded ? "Hide" : "Show"} children ({childCount})
        </button>
      ) : null}

      {childCount > 0 && isExpanded ? (
        <div className="note-children">
          {children.map((child) => (
            <NoteTreeItem
              key={child.id}
              note={child}
              onOpen={onOpen}
              onDelete={onDelete}
              onToggle={onToggle}
              depth={depth + 1}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function GoalItem({
  note,
  onOpen,
  onDelete,
  onToggle,
}: {
  note: Note;
  onOpen: (id: number) => void;
  onDelete: (id: number) => void;
  onToggle: (id: number) => void;
}) {
  return (
    <div className="note-row">
      <button className="note-row__main" onClick={() => onOpen(note.id)} type="button">
        <span className="note-category cat-repetitive-task">Goal</span>
        <strong>{note.text}</strong>
        <small>{note.repeat_display ?? "Repeating goal"} · {note.completed_today ? "done today" : "active"}</small>
      </button>
      <button className="status-btn" onClick={() => onToggle(note.id)} type="button">
        {note.completed_today ? "Reopen" : "Done"}
      </button>
      <button className="delete-btn" onClick={() => onDelete(note.id)} type="button">x</button>
    </div>
  );
}

function NoteDetail({
  note,
  onBack,
  onOpen,
  onDelete,
  onToggle,
}: {
  note: Note;
  onBack: () => void;
  onOpen: (id: number) => void;
  onDelete: (id: number) => void;
  onToggle: (id: number) => void;
}) {
  const [showChildren, setShowChildren] = useState(false);
  const childCount = note.subnotes?.length ?? 0;

  return (
    <div className="note-detail-screen">
      <div className="detail-header">
        <button className="back-btn" onClick={onBack} type="button">Back</button>
        <div className="detail-header__actions">
          <button className="status-btn" onClick={() => onToggle(note.id)} type="button">
            {note.status === "done" || note.completed_today ? "Reopen" : "Done"}
          </button>
          <button className="delete-btn" onClick={() => onDelete(note.id)} type="button">Delete</button>
        </div>
      </div>

      <section className="panel note-detail-panel">
        <span className={`note-category ${categoryClass(displayCategory(note))}`}>{displayCategory(note)}</span>
        <p className="detail-text">{note.text}</p>
        <span className="note-date">{note.created_at}</span>
        {note.repeat_display ? <span className="repeat-badge">{note.repeat_display}</span> : null}
        <UrgencyBadges note={note} />
        <LocationBadge note={note} />
      </section>

      <section className="panel">
        <div className="panel-title-row">
          <h1>CHILDREN</h1>
          {childCount > 0 ? (
            <button className="children-toggle children-toggle--inline" onClick={() => setShowChildren((current) => !current)} type="button">
              {showChildren ? "Hide" : "Show"} ({childCount})
            </button>
          ) : null}
        </div>
        {childCount > 0 && showChildren ? (
          <div className="notes-tree">
            {note.subnotes?.map((child) => (
              <NoteTreeItem
                key={child.id}
                note={child}
                onOpen={onOpen}
                onDelete={onDelete}
                onToggle={onToggle}
              />
            ))}
          </div>
        ) : childCount === 0 ? (
          <p className="empty">No children yet.</p>
        ) : null}
      </section>
    </div>
  );
}

function flattenNotes(notes: Note[]): Note[] {
  return notes.flatMap((note) => [note, ...flattenNotes(note.subnotes ?? [])]);
}

function sortByRank(a: Note, b: Note) {
  return b.rank_score - a.rank_score || b.importance_score - a.importance_score || b.id - a.id;
}

function categoryClass(category: string) {
  return `cat-${category.toLowerCase().replace(/\s+/g, "-")}`;
}

function displayCategory(note: Note) {
  return note.is_repeating ? "Goal" : note.category;
}

function formatToday() {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    day: "2-digit",
    month: "long",
  }).format(new Date()).toUpperCase();
}

function formatTime(value: string | null) {
  if (!value) return "All day";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "All day";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}
