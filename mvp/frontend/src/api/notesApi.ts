import { del, get, patch, post } from "./client";
import type { CaptureJob, Location, Note, NoteQueryStatus, NoteStatus, NoteStatusResult, RecordResult, RecordingJobResult } from "../types/note";

export const fetchNotes = (status?: NoteQueryStatus) =>
  get<Note[]>(status ? `/api/notes?status=${status}` : "/api/notes");

export const fetchNote = (id: number) =>
  get<Note>(`/api/notes/${id}`);

export const fetchTodayRepeats = () =>
  get<Note[]>("/api/repeats/today");

export const fetchHealth = () =>
  get<Record<string, unknown>>("/api/health");

export const fetchLocations = () =>
  get<Location[]>("/api/locations");

export const fetchActiveCaptureJobs = () =>
  get<CaptureJob[]>("/api/capture/jobs/active");

export const deleteLocation = (id: number) =>
  del(`/api/locations/${id}`);

export const startRecording = () =>
  post<RecordingJobResult>("/api/record/start");

export const stopRecording = () =>
  post<RecordingJobResult>("/api/record/stop");

export const submitText = (text: string) =>
  post<RecordResult>("/api/text", { text });

export const deleteNote = (id: number) =>
  del(`/api/notes/${id}`);

export const markNoteAs = (noteId: number, status: NoteStatus) =>
  patch<NoteStatusResult>(`/api/notes/${noteId}/status`, { status });

export const toggleNoteStatus = (noteId: number) =>
  post<NoteStatusResult>(`/api/notes/${noteId}/toggle-status`);
