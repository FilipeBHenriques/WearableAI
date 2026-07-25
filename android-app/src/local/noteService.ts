import { completedOn, isAvailableOn, isDueOn, isRepeating, repeatDisplay, repeatDoneStatus } from "./recurrence";
import type { LocalRepository } from "./repository";
import {
  ACTIVE_STATUS,
  DONE_STATUS,
  type Note,
  type NoteStatus,
  type NoteView,
} from "./types";
import type { TypedEventBus } from "./eventBus";
import type { DomainEvents } from "./types";

export class NoteService {
  constructor(
    private readonly repository: LocalRepository,
    private readonly events: TypedEventBus<DomainEvents>,
  ) {}

  async getAll(status: NoteStatus | null = null, day = new Date()): Promise<Note[]> {
    const notes = await this.repository.listNotes(status === ACTIVE_STATUS ? null : status);
    const visible =
      status === ACTIVE_STATUS
        ? notes.filter((note) =>
            isRepeating(note)
              ? isAvailableOn(note, day)
              : note.status === ACTIVE_STATUS,
          )
        : notes;
    const ids = new Set(visible.map((note) => note.id));
    return visible.filter((note) => note.parent_note_id == null || !ids.has(note.parent_note_id));
  }

  async getSubnotes(
    noteId: number,
    status: NoteStatus | null = null,
    day = new Date(),
  ): Promise<Note[]> {
    const notes = await this.repository.listChildNotes(noteId, status === ACTIVE_STATUS ? null : status);
    return status === ACTIVE_STATUS
      ? notes.filter((note) =>
          isRepeating(note) ? isAvailableOn(note, day) : note.status === ACTIVE_STATUS,
        )
      : notes;
  }

  async getTree(
    noteId: number,
    status: NoteStatus | null = null,
    day = new Date(),
  ): Promise<NoteView | null> {
    return this.buildTree(noteId, status, day, new Set());
  }

  private async buildTree(
    noteId: number,
    status: NoteStatus | null,
    day: Date,
    ancestors: Set<number>,
  ): Promise<NoteView | null> {
    if (ancestors.has(noteId)) return null;
    const note = await this.repository.getNote(noteId);
    if (!note) return null;
    const nextAncestors = new Set(ancestors).add(noteId);
    const children = await this.getSubnotes(note.id, status, day);
    return this.view(
      note,
      await Promise.all(
        children.map((child) => this.buildTree(child.id, status, day, nextAncestors)),
      ),
      day,
    );
  }

  async listTrees(status: NoteStatus | null = null, day = new Date()): Promise<NoteView[]> {
    return Promise.all(
      (await this.getAll(status, day)).map(
        async (note) => (await this.getTree(note.id, status, day))!,
      ),
    );
  }

  async markAs(noteId: number, status: NoteStatus, day = new Date()): Promise<void> {
    if (status !== ACTIVE_STATUS && status !== DONE_STATUS)
      throw new Error(`Unsupported note status: ${status}`);
    const note = await this.repository.getNote(noteId);
    if (!note) return;
    if (isRepeating(note)) {
      await this.repository.updateNote(noteId, {
        status: status === DONE_STATUS ? repeatDoneStatus(day) : ACTIVE_STATUS,
      });
    } else {
      for (const id of [noteId, ...(await this.descendantIds(noteId))])
        await this.repository.updateNote(id, { status });
    }
    this.events.publish("notes_changed", { note_id: noteId });
  }

  async toggleStatus(noteId: number, day = new Date()): Promise<NoteStatus | null> {
    const note = await this.repository.getNote(noteId);
    if (!note) return null;
    const status = isRepeating(note)
      ? completedOn(note, day)
        ? ACTIVE_STATUS
        : repeatDoneStatus(day)
      : note.status === ACTIVE_STATUS
        ? DONE_STATUS
        : ACTIVE_STATUS;
    if (isRepeating(note)) {
      await this.repository.updateNote(noteId, { status });
      this.events.publish("notes_changed", { note_id: noteId });
    } else await this.markAs(noteId, status, day);
    return status;
  }

  async todayRepeats(day = new Date()): Promise<Note[]> {
    return (await this.repository.listNotes()).filter(
      (note) => isRepeating(note) && isDueOn(note, day),
    );
  }

  async todayRepeatViews(day = new Date()): Promise<NoteView[]> {
    return (await this.todayRepeats(day)).map((note) => this.view(note, undefined, day));
  }

  async delete(noteId: number, deleteAudio?: (path: string) => Promise<void>): Promise<number[]> {
    const ids = [noteId, ...(await this.descendantIds(noteId))];
    if (deleteAudio) {
      for (const id of ids) {
        const note = await this.repository.getNote(id);
        if (note?.audio_path) await deleteAudio(note.audio_path);
      }
    }
    await this.repository.deleteNotes(ids);
    this.events.publish("notes_changed", { note_ids: ids });
    return ids;
  }

  view(note: Note, subnotes?: (NoteView | null)[], day = new Date()): NoteView {
    return {
      ...note,
      is_repeating: isRepeating(note),
      is_due_today: isDueOn(note, day),
      completed_today: completedOn(note, day),
      repeat_display: repeatDisplay(note),
      audio_url: note.audio_path,
      ...(subnotes ? { subnotes: subnotes.filter((item): item is NoteView => item != null) } : {}),
    };
  }

  private async descendantIds(noteId: number): Promise<number[]> {
    const notes = await this.repository.listNotes();
    const pending = [noteId];
    const result: number[] = [];
    while (pending.length) {
      const current = pending.pop()!;
      for (const child of notes.filter((note) => note.parent_note_id === current)) {
        result.push(child.id);
        pending.push(child.id);
      }
    }
    return result;
  }
}
