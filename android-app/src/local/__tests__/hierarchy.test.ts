import { describe, expect, it } from "vitest";
import { TypedEventBus } from "../eventBus";
import { InMemoryRepository } from "../memoryRepository";
import { NoteService } from "../noteService";

describe("note hierarchy", () => {
  it("builds trees and cascades status changes", async () => {
    const repository = new InMemoryRepository();
    const service = new NoteService(repository, new TypedEventBus());
    const root = await repository.createNote("project");
    const child = await repository.createNote("project task");
    const grandchild = await repository.createNote("project task detail");
    await repository.updateNote(child.id, { parent_note_id: root.id });
    await repository.updateNote(grandchild.id, { parent_note_id: child.id });

    expect((await service.getTree(root.id))?.subnotes?.[0].subnotes?.[0].id).toBe(grandchild.id);
    await service.markAs(root.id, "done");
    expect((await repository.listNotes()).map((note) => note.status)).toEqual([
      "done",
      "done",
      "done",
    ]);
    await service.markAs(root.id, "active");
    expect((await repository.listNotes()).every((note) => note.status === "active")).toBe(true);
  });

  it("cascades deletion and detaches capture jobs", async () => {
    const repository = new InMemoryRepository();
    const service = new NoteService(repository, new TypedEventBus());
    const root = await repository.createNote("root");
    const child = await repository.createNote("child");
    await repository.updateNote(child.id, { parent_note_id: root.id });
    const job = await repository.createCaptureJob("ready");
    await repository.updateCaptureJob(job.id, { note_id: child.id });

    expect(await service.delete(root.id)).toEqual([root.id, child.id]);
    expect(await repository.listNotes()).toEqual([]);
    expect((await repository.getCaptureJob(job.id))?.note_id).toBeNull();
  });

  it("rejects missing parents and hierarchy cycles", async () => {
    const repository = new InMemoryRepository();
    const root = await repository.createNote("root");
    const child = await repository.createNote("child");
    await repository.updateNote(child.id, { parent_note_id: root.id });

    await expect(repository.updateNote(root.id, { parent_note_id: child.id })).rejects.toThrow(
      "cycle",
    );
    await expect(repository.updateNote(root.id, { parent_note_id: 999 })).rejects.toThrow(
      "does not exist",
    );
  });
});
