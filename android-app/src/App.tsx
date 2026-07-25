import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { HashRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { CaptureJob, Location, NoteView } from "./local/types";
import { createLocalRuntime, type LocalRuntime, type RuntimeStatus } from "./platform/localRuntime";
import { useAndroidBackButton } from "./useAndroidBackButton";

let runtimePromise: Promise<LocalRuntime> | null = null;
let latestStartup: RuntimeStatus | null = null;
const startupListeners = new Set<(status: RuntimeStatus) => void>();

function getRuntime() {
  runtimePromise ??= createLocalRuntime((status) => {
    latestStartup = status;
    startupListeners.forEach((listener) => listener(status));
  });
  return runtimePromise;
}

export default function App() {
  return (
    <HashRouter>
      <AppRoutes />
    </HashRouter>
  );
}

function AppRoutes() {
  useAndroidBackButton();
  return (
    <Routes>
      <Route path="*" element={<LocalApp />} />
    </Routes>
  );
}

type Screen = "main" | "notes" | "goals" | "locations";

function LocalApp() {
  const location = useLocation();
  const navigate = useNavigate();
  const [runtime, setRuntime] = useState<LocalRuntime | null>(null);
  const [startup, setStartup] = useState<RuntimeStatus | null>(null);
  const [startupError, setStartupError] = useState<string | null>(null);
  const [notes, setNotes] = useState<NoteView[]>([]);
  const [today, setToday] = useState<NoteView[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [jobs, setJobs] = useState<CaptureJob[]>([]);
  const [gpsNotes, setGpsNotes] = useState<NoteView[]>([]);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [recordState, setRecordState] = useState<"idle" | "recording" | "processing">("idle");
  const notesRef = useRef<NoteView[]>([]);
  notesRef.current = notes;

  useEffect(() => {
    let active = true;
    const listener = (status: RuntimeStatus) => {
      if (active) setStartup(status);
    };
    startupListeners.add(listener);
    if (latestStartup) listener(latestStartup);
    getRuntime().then((value) => {
      if (active) {
        setRuntime(value);
        setStartup(value.status);
      }
    }).catch((error: unknown) => {
      if (active) {
        setStartupError(errorText(error));
        const status = (error as { runtimeStatus?: RuntimeStatus }).runtimeStatus;
        if (status) setStartup(status);
      }
    });
    return () => {
      active = false;
      startupListeners.delete(listener);
    };
  }, []);

  const reload = useCallback(async () => {
    if (!runtime) return;
    const [allNotes, repeats, savedLocations, activeJobs] = await Promise.all([
      runtime.service.listNotes("all"),
      runtime.service.todayRepeats(),
      runtime.service.listLocations(),
      runtime.service.activeCaptureJobs(),
    ]);
    setNotes(allNotes);
    setToday(repeats);
    setLocations(savedLocations);
    setJobs(activeJobs.filter((job) => ACTIVE_CAPTURE_STATUSES.has(job.status)));
  }, [runtime]);

  const applyCaptureJob = useCallback((job: CaptureJob) => {
    setJobs((current) => {
      const next = new Map(current.map((item) => [item.id, item]));
      if (ACTIVE_CAPTURE_STATUSES.has(job.status)) next.set(job.id, job);
      else next.delete(job.id);
      return Array.from(next.values()).sort((a, b) => b.id - a.id);
    });
    if (
      job.status === "saved_raw" ||
      job.status === "enriching" ||
      job.status === "ready" ||
      job.status === "failed"
    ) {
      void reload().catch((error) => setOperationError(errorText(error)));
    }
  }, [reload]);

  useEffect(() => {
    if (!runtime) return;
    void reload().catch((error) => setOperationError(errorText(error)));
    const subscriptions = [
      runtime.service.subscribe("notes_changed", () => {
        void reload().catch((error) => setOperationError(errorText(error)));
      }),
      runtime.service.subscribe("locations_changed", () => {
        void reload().catch((error) => setOperationError(errorText(error)));
      }),
      runtime.service.subscribe("capture_job", applyCaptureJob),
      runtime.service.subscribe("gps_suggestions", (payload) => {
        const ids = new Set(payload.notes.map((note) => note.id));
        setGpsNotes(flatten(notesRef.current).filter((note) => ids.has(note.id)));
      }),
    ];
    return () => {
      subscriptions.forEach((unsubscribe) => unsubscribe());
    };
  }, [applyCaptureJob, reload, runtime]);

  const screen = screenFromPath(location.pathname);
  const selectedId = noteIdFromPath(location.pathname);
  const selected = selectedId == null ? null : flatten(notes).find((note) => note.id === selectedId) ?? null;

  const run = useCallback(async (action: () => Promise<unknown>) => {
    setOperationError(null);
    try {
      await action();
    } catch (error) {
      setOperationError(errorText(error));
      throw error;
    }
  }, []);

  if (!runtime) {
    return <StartupView status={startup} error={startupError} />;
  }

  return (
    <AppShell
      screen={screen}
      status={runtime.status}
      onScreen={(next) => navigate(next === "main" ? "/" : `/${next}`)}
      capture={<CaptureControls
        runtime={runtime}
        jobs={jobs}
        state={recordState}
        setState={setRecordState}
        run={run}
        reload={reload}
      />}
    >
      {operationError ? <ErrorBanner message={operationError} onClose={() => setOperationError(null)} /> : null}
      <ModelBanner status={runtime.status} />
      {selected ? (
        <NoteDetail
          note={selected}
          runtime={runtime}
          onBack={() => navigate(`/${screen === "goals" ? "goals" : "notes"}`)}
          onOpen={(id) => navigate(`/${screen === "goals" ? "goals" : "notes"}/${id}`)}
          onDelete={(id) => {
            void run(() => runtime.service.deleteNote(id))
              .then(() => navigate(screen === "goals" ? "/goals" : "/notes"))
              .catch(() => undefined);
          }}
          onToggle={(id) => {
            void run(() => runtime.service.toggleNoteStatus(id)).catch(() => undefined);
          }}
        />
      ) : screen === "main" ? (
        <MainScreen notes={notes} today={today} gpsNotes={gpsNotes} runtime={runtime} navigate={navigate} run={run} />
      ) : screen === "notes" || screen === "goals" ? (
        <NotesScreen
          notes={notes}
          goals={screen === "goals"}
          onOpen={(id) => navigate(`/${screen}/${id}`)}
          onDelete={(id) => {
            void run(() => runtime.service.deleteNote(id)).catch(() => undefined);
          }}
          onToggle={(id) => {
            void run(() => runtime.service.toggleNoteStatus(id)).catch(() => undefined);
          }}
        />
      ) : (
        <LocationsScreen
          locations={locations}
          onDelete={(id) => {
            void run(() => runtime.service.deleteLocation(id)).catch(() => undefined);
          }}
          onCheck={() => {
            void run(() => runtime.service.checkProximity()).catch(() => undefined);
          }}
        />
      )}
    </AppShell>
  );
}

function MainScreen({
  notes, today, gpsNotes, runtime, navigate, run,
}: {
  notes: NoteView[];
  today: NoteView[];
  gpsNotes: NoteView[];
  runtime: LocalRuntime;
  navigate: ReturnType<typeof useNavigate>;
  run: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const active = flatten(notes).filter((note) => note.status === "active");
  const timetable = [...today, ...active.filter((note) => note.deadline_at && !note.is_repeating)]
    .sort((a, b) => (a.repeat_time ?? a.deadline_at ?? "").localeCompare(b.repeat_time ?? b.deadline_at ?? ""));
  const suggestions = [...gpsNotes, ...active.sort((a, b) => b.rank_score - a.rank_score)]
    .filter((note, index, all) => all.findIndex((item) => item.id === note.id) === index)
    .slice(0, 8);

  return (
    <>
      <TextCapture onSubmit={(text) => run(() => runtime.service.processText(text))} />
      <div className="grid main-grid">
        <Panel title="TODAY">
          <div className="date">{formatToday()}</div>
          <div className="list">
            {today.length ? today.map((note) => (
              <TaskRow
                key={note.id}
                note={note}
                onOpen={(id) => navigate(`/notes/${id}`)}
                onToggle={(id) => {
                  void run(() => runtime.service.toggleNoteStatus(id)).catch(() => undefined);
                }}
              />
            )) : <p className="empty">No goals due today.</p>}
          </div>
        </Panel>
        <Panel title="TIMETABLE">
          <div className="timeline">
            {timetable.length ? timetable.map((note) => (
              <button className="time-row" key={note.id} onClick={() => navigate(`/notes/${note.id}`)} type="button">
                <span>{note.repeat_time ?? formatTime(note.deadline_at)}</span>
                <div>{note.text}<small>{note.is_repeating ? "goal" : note.category}</small></div>
              </button>
            )) : <p className="empty">No timed items.</p>}
          </div>
        </Panel>
        <Panel title="SUGGESTIONS">
          <div className="list">
            {suggestions.length ? suggestions.map((note) => (
              <button className="suggestion-item" key={note.id} onClick={() => navigate(`/notes/${note.id}`)} type="button">
                <span>{gpsNotes.some((item) => item.id === note.id) ? `GPS · ${note.location_name ?? "nearby"}` : displayCategory(note)}</span>
                <strong>{note.text}</strong>
                <small>{note.urgency_reason ?? note.deadline_at ?? note.created_at}</small>
              </button>
            )) : <p className="empty">No suggestions yet.</p>}
          </div>
        </Panel>
      </div>
    </>
  );
}

function NotesScreen({ notes, goals, onOpen, onDelete, onToggle }: {
  notes: NoteView[];
  goals: boolean;
  onOpen: (id: number) => void;
  onDelete: (id: number) => void;
  onToggle: (id: number) => void;
}) {
  const items = goals ? flatten(notes).filter((note) => note.is_repeating) : notes.filter((note) => !note.is_repeating);
  return (
    <div className="notes-screen">
      <Panel title={goals ? "GOALS" : "NOTES"}>
        <div className="notes-tree">
          {items.length ? items.map((note) => (
            <NoteTreeItem key={note.id} note={note} onOpen={onOpen} onDelete={onDelete} onToggle={onToggle} />
          )) : <p className="empty">No {goals ? "goals" : "notes"} yet.</p>}
        </div>
      </Panel>
    </div>
  );
}

function LocationsScreen({ locations, onDelete, onCheck }: {
  locations: Location[];
  onDelete: (id: number) => void;
  onCheck: () => void;
}) {
  return <Panel title="LOCATIONS">
    <button className="secondary-btn" onClick={onCheck} type="button">CHECK NEARBY</button>
    <div className="debug-locations">
      {locations.length ? locations.map((item) => (
        <div className="debug-location" key={item.id}>
          <div className="debug-location__topline"><strong>@{item.name}</strong><button className="delete-btn" onClick={() => onDelete(item.id)}>x</button></div>
          <small>{item.latitude.toFixed(5)}, {item.longitude.toFixed(5)}</small>
          <small>Updated {item.updated_at}</small>
        </div>
      )) : <p className="empty">No saved locations. Submit “save location Home” to add one.</p>}
    </div>
  </Panel>;
}

function AppShell({ children, screen, status, onScreen, capture }: {
  children: ReactNode;
  screen: Screen;
  status: RuntimeStatus;
  onScreen: (screen: Screen) => void;
  capture: ReactNode;
}) {
  return (
    <main className="device">
      <div className="shell shell--simple">
        <section className="screen">
          <header className="topbar">
            <button className="brand brand-button" onClick={() => onScreen("main")} type="button">LOCAL-MEM OS</button>
            <nav className="tabs" aria-label="Main sections">
              {(["main", "notes", "goals", "locations"] as Screen[]).map((item) => (
                <button className={screen === item ? "active" : ""} onClick={() => onScreen(item)} key={item} type="button">{item.toUpperCase()}</button>
              ))}
            </nav>
            <div className="status">{status.platform === "android-local" ? "OFFLINE" : "DEMO"}</div>
          </header>
          <div className="content">{children}</div>
        </section>
        {capture}
      </div>
    </main>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h1>{title}</h1>
      {children}
    </section>
  );
}

function TextCapture({ onSubmit }: { onSubmit: (text: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  return <form className="text-capture" onSubmit={(event) => {
    event.preventDefault();
    if (!text.trim() || saving) return;
    setSaving(true);
    void onSubmit(text)
      .then(() => setText(""))
      .catch(() => undefined)
      .finally(() => setSaving(false));
  }}>
    <input value={text} onChange={(event) => setText(event.target.value)} placeholder="Type a note or command…" aria-label="Text note" />
    <button type="submit" disabled={saving || !text.trim()}>{saving ? "SAVING…" : "SAVE"}</button>
  </form>;
}

function CaptureControls({ runtime, jobs, state, setState, run, reload }: {
  runtime: LocalRuntime;
  jobs: CaptureJob[];
  state: "idle" | "recording" | "processing";
  setState: (state: "idle" | "recording" | "processing") => void;
  run: (action: () => Promise<unknown>) => Promise<void>;
  reload: () => Promise<void>;
}) {
  const stateRef = useRef(state);
  stateRef.current = state;
  const startTask = useRef<Promise<boolean> | null>(null);
  const enabled = runtime.status.platform === "android-local" && runtime.status.model === "ready";

  const setRecordState = (next: "idle" | "recording" | "processing") => {
    stateRef.current = next;
    setState(next);
  };

  const start = () => {
    if (!enabled || stateRef.current !== "idle") return;
    setRecordState("recording");
    startTask.current = run(() => runtime.service.startRecording())
      .then(() => true)
      .catch(() => {
        setRecordState("idle");
        return false;
      });
  };

  const stop = () => {
    if (stateRef.current !== "recording") return;
    setRecordState("processing");
    void (async () => {
      const started = await (startTask.current ?? Promise.resolve(false));
      startTask.current = null;
      if (!started) {
        setRecordState("idle");
        return;
      }
      try {
        await run(() => runtime.service.stopRecording());
        await reload();
      } catch {
        // Shared error banner already surfaces the failure.
      } finally {
        setRecordState("idle");
      }
    })();
  };

  return <>
    <div
      className={jobs.length ? "capture-queue" : "capture-queue capture-queue--empty"}
      aria-label="Active capture queue"
    >
      {jobs.length === 0 ? null : jobs.map((job) => (
        <div className="capture-job" key={job.id}>
          <div className="capture-job__topline">
            <span>JOB {job.id}</span>
            <strong>{job.status.replace("_", " ")}</strong>
          </div>
          <p>{job.error ?? job.final_transcript ?? queueText(job.status)}</p>
        </div>
      ))}
    </div>
    <aside className="hardware-rec">
      <button
        className={`record-btn record-btn--${state}`}
        disabled={!enabled || state === "processing"}
        onMouseDown={start}
        onMouseUp={stop}
        onMouseLeave={() => {
          if (stateRef.current === "recording") stop();
        }}
        onTouchStart={(event) => {
          event.preventDefault();
          start();
        }}
        onTouchEnd={stop}
        onTouchCancel={stop}
        type="button"
        title={enabled ? "Hold to record" : "Native audio requires warm local models"}
      >
        {state === "recording" ? "● RECORDING…" : state === "processing" ? "PROCESSING…" : "HOLD TO RECORD"}
      </button>
    </aside>
  </>;
}

function TaskRow({ note, onOpen, onToggle }: { note: NoteView; onOpen: (id: number) => void; onToggle: (id: number) => void }) {
  return <div className="row">
    <button className={note.completed_today ? "check done" : "check"} onClick={() => onToggle(note.id)} type="button">{note.completed_today ? "■" : "□"}</button>
    <button className="row-main" onClick={() => onOpen(note.id)} type="button"><strong>{note.text}</strong><small>{note.repeat_display ?? note.created_at}</small></button>
    <span className="tag">GOAL</span>
  </div>;
}

function NoteTreeItem({ note, onOpen, onDelete, onToggle }: {
  note: NoteView;
  onOpen: (id: number) => void;
  onDelete: (id: number) => void;
  onToggle: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const children = note.subnotes ?? [];
  return <div className="note-tree-item">
    <div className="note-row">
      <button className="note-row__main" onClick={() => onOpen(note.id)} type="button">
        <span className={`note-category ${categoryClass(displayCategory(note))}`}>{displayCategory(note)}</span>
        <strong>{note.text}</strong><small>{note.status === "done" ? "Done" : note.created_at}</small>
      </button>
      <button className="status-btn" onClick={() => onToggle(note.id)} type="button">{note.status === "done" || note.completed_today ? "Reopen" : "Done"}</button>
      <button className="delete-btn" onClick={() => onDelete(note.id)} type="button">x</button>
    </div>
    {children.length ? <button className="children-toggle" onClick={() => setExpanded(!expanded)} type="button">{expanded ? "Hide" : "Show"} children ({children.length})</button> : null}
    {expanded ? <div className="note-children">{children.map((child) => <NoteTreeItem key={child.id} note={child} onOpen={onOpen} onDelete={onDelete} onToggle={onToggle} />)}</div> : null}
  </div>;
}

function NoteDetail({ note, runtime, onBack, onOpen, onDelete, onToggle }: {
  note: NoteView;
  runtime: LocalRuntime;
  onBack: () => void;
  onOpen: (id: number) => void;
  onDelete: (id: number) => void;
  onToggle: (id: number) => void;
}) {
  return <div className="note-detail-screen">
    <div className="detail-header"><button className="back-btn" onClick={onBack}>← Back</button><div className="detail-header__actions">
      <button className="status-btn" onClick={() => onToggle(note.id)}>{note.status === "done" || note.completed_today ? "Reopen" : "Done"}</button>
      <button className="delete-btn" onClick={() => onDelete(note.id)}>Delete</button>
    </div></div>
    <Panel title="NOTE">
      <span className={`note-category ${categoryClass(displayCategory(note))}`}>{displayCategory(note)}</span>
      <p className="detail-text">{note.text}</p><small>{note.created_at}</small>
      {note.repeat_display ? <span className="repeat-badge">{note.repeat_display}</span> : null}
      <UrgencyBadges note={note} />
      <LocationBadge note={note} />
      {note.audio_path ? <NoteAudioPlayer src={runtime.toAudioUrl(note.audio_path)} /> : null}
    </Panel>
    <Panel title={`CHILDREN (${note.subnotes?.length ?? 0})`}>
      <div className="notes-tree">{note.subnotes?.length ? note.subnotes.map((child) => <NoteTreeItem key={child.id} note={child} onOpen={onOpen} onDelete={onDelete} onToggle={onToggle} />) : <p className="empty">No children yet.</p>}</div>
    </Panel>
  </div>;
}

function UrgencyBadges({ note }: { note: NoteView }) {
  const showUrgency = note.deadline_at != null || note.urgency_score > 0;
  if (
    !note.deadline_at &&
    note.estimated_duration_minutes == null &&
    !showUrgency &&
    !note.urgency_reason
  ) {
    return null;
  }
  return <div className="urgency-badges">
    {note.deadline_at ? <span className="urgency-badge urgency-badge--deadline">Due {formatDeadline(note.deadline_at)}</span> : null}
    {note.estimated_duration_minutes != null ? <span className="urgency-badge">Est. {note.estimated_duration_minutes}m</span> : null}
    {showUrgency ? <span className="urgency-badge">Urgency {note.urgency_score}</span> : null}
    {note.urgency_reason ? <span className="urgency-badge urgency-badge--reason">{note.urgency_reason}</span> : null}
  </div>;
}

function LocationBadge({ note }: { note: NoteView }) {
  if (!note.location_name) return null;
  return <span className="location-badge">+ @{note.location_name}{note.location_latitude != null && note.location_longitude != null ? ` ${note.location_latitude.toFixed(5)}, ${note.location_longitude.toFixed(5)}` : ""}</span>;
}

function NoteAudioPlayer({ src }: { src: string }) {
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  return <div className="note-audio"><audio ref={audio} src={src} preload="none" onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
    <button className="audio-btn" onClick={() => {
      if (!audio.current) return;
      if (playing) audio.current.pause();
      else void audio.current.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
    }}>{playing ? "Pause" : "Play"}</button>
  </div>;
}

function StartupView({ status, error }: { status: RuntimeStatus | null; error: string | null }) {
  return <main className="device"><div className="startup-card"><h1>LOCAL-MEM OS</h1><p>{error ?? status?.message ?? "Starting local storage and models…"}</p>
    <div className="status-list"><div className="status-row"><span>Storage</span><strong>{status?.storage ?? "starting"}</strong></div>
      <div className="status-row"><span>Models</span><strong>{status?.model ?? "checking"}</strong></div></div>
    {error ? <p className="error-text">Restart the app after checking available device storage.</p> : null}
  </div></main>;
}

function ModelBanner({ status }: { status: RuntimeStatus }) {
  if (status.model === "ready") return null;
  return <div className="system-banner"><strong>{status.model === "missing" ? "MODEL ASSETS MISSING" : "TEXT-ONLY MODE"}</strong>
    <span>{status.missingModels.length ? status.missingModels.join(", ") : status.message}</span>
  </div>;
}

function ErrorBanner({ message, onClose }: { message: string; onClose: () => void }) {
  return <div className="error-banner" role="alert"><span>{message}</span><button onClick={onClose}>x</button></div>;
}

function flatten(notes: NoteView[]): NoteView[] {
  return notes.flatMap((note) => [note, ...flatten(note.subnotes ?? [])]);
}

function screenFromPath(path: string): Screen {
  if (path.startsWith("/goals")) return "goals";
  if (path.startsWith("/locations")) return "locations";
  if (path.startsWith("/notes")) return "notes";
  return "main";
}

function noteIdFromPath(path: string): number | null {
  const match = path.match(/^\/(?:notes|goals)\/(\d+)/);
  return match ? Number(match[1]) : null;
}

function categoryClass(category: string) {
  return `cat-${category.toLowerCase().replace(/\s+/g, "-")}`;
}

function displayCategory(note: NoteView) {
  return note.is_repeating ? "Goal" : note.category;
}

function formatToday() {
  return new Intl.DateTimeFormat(undefined, { weekday: "long", day: "2-digit", month: "long" }).format(new Date()).toUpperCase();
}

function formatTime(value: string | null) {
  if (!value) return "All day";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "All day" : new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function formatDeadline(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function queueText(status: CaptureJob["status"]) {
  if (status === "recording") return "Recording audio…";
  if (status === "transcribing") return "Transcribing locally…";
  if (status === "saved_raw") return "Raw note saved.";
  if (status === "enriching") return "Categorizing and ranking…";
  return status === "failed" ? "Capture failed." : "Finishing…";
}

const ACTIVE_CAPTURE_STATUSES = new Set<CaptureJob["status"]>([
  "recording",
  "transcribing",
  "saved_raw",
  "enriching",
  "failed",
]);

const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
