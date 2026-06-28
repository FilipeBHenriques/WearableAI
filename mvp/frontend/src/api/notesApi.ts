import { del, get, patch, post } from "./client";
import type { Location, Note, NoteQueryStatus, NoteStatus, NoteStatusResult, RecordResult } from "../types/note";

export const fetchNotes = (status?: NoteQueryStatus) =>
  get<Note[]>(status ? `/api/notes?status=${status}` : "/api/notes");

export const fetchNote = (id: number) =>
  get<Note>(`/api/notes/${id}`);

export const fetchLocations = () =>
  get<Location[]>("/api/locations");

export const deleteLocation = (id: number) =>
  del(`/api/locations/${id}`);

export const startRecording = () =>
  post<void>("/api/record/start");

export const stopRecording = () =>
  post<RecordResult>("/api/record/stop");

export const submitText = (text: string) =>
  post<RecordResult>("/api/text", { text });

export const deleteNote = (id: number) =>
  del(`/api/notes/${id}`);

export const markNoteAs = (noteId: number, status: NoteStatus) =>
  patch<NoteStatusResult>(`/api/notes/${noteId}/status`, { status });

export const toggleNoteStatus = (noteId: number) =>
  post<NoteStatusResult>(`/api/notes/${noteId}/toggle-status`);
