import { del, get, post } from "./client";
import type { Note, RecordResult } from "../types/note";

export const fetchNotes = () =>
  get<Note[]>("/api/notes");

export const fetchNote = (id: number) =>
  get<Note>(`/api/notes/${id}`);

export const startRecording = () =>
  post<void>("/api/record/start");

export const stopRecording = () =>
  post<RecordResult>("/api/record/stop");

export const submitText = (text: string) =>
  post<RecordResult>("/api/text", { text });

export const deleteNote = (id: number) =>
  del(`/api/notes/${id}`);
