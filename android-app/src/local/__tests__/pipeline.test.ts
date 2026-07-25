import { describe, expect, it, vi } from "vitest";
import { TypedEventBus } from "../eventBus";
import { InMemoryRepository } from "../memoryRepository";
import {
  ENRICH_STEPS,
  INTAKE_STEPS,
  NotePipeline,
  type PipelineHandler,
  type PipelineStep,
} from "../pipeline";
import { NoteService } from "../noteService";
import type { DomainEvents } from "../types";

function setup(handlers: Partial<Record<PipelineStep, PipelineHandler>>, errors: PipelineStep[] = []) {
  const repository = new InMemoryRepository();
  const events = new TypedEventBus<DomainEvents>();
  const notes = new NoteService(repository, events);
  return {
    repository,
    pipeline: new NotePipeline({
      repository,
      events,
      notes,
      handlers,
      onStepError: (step) => errors.push(step),
    }),
  };
}

describe("NotePipeline orchestration", () => {
  it("declares the exact intake and enrichment order", () => {
    expect(INTAKE_STEPS).toEqual(["detect_command", "save_note"]);
    expect(ENRICH_STEPS).toEqual([
      "relationship",
      "classification",
      "urgency",
      "estimate_duration",
      "location",
      "recurrence",
    ]);
  });

  it("runs intake in order and fails fast", async () => {
    const calls: string[] = [];
    const save = vi.fn(async () => {
      calls.push("save_note");
    });
    const { pipeline } = setup({
      detect_command: async () => {
        calls.push("detect_command");
        throw new Error("command failed");
      },
      save_note: save,
    });

    await expect(pipeline.runIntake("keep me")).rejects.toThrow("command failed");
    expect(calls).toEqual(["detect_command"]);
    expect(save).not.toHaveBeenCalled();
  });

  it("continues enrichment after each error in exact order", async () => {
    const calls: PipelineStep[] = [];
    const errors: PipelineStep[] = [];
    const handlers = Object.fromEntries(
      ENRICH_STEPS.map((step) => [
        step,
        async () => {
          calls.push(step);
          if (step === "relationship" || step === "urgency") throw new Error(step);
        },
      ]),
    ) as Partial<Record<PipelineStep, PipelineHandler>>;
    const { repository, pipeline } = setup(handlers, errors);
    const note = await repository.createNote("saved before enrichment");

    const result = await pipeline.runEnrich(note.id);

    expect(result.saved).toBe(true);
    expect(calls).toEqual(ENRICH_STEPS);
    expect(errors).toEqual(["relationship", "urgency"]);
    expect((await repository.getNote(note.id))?.text).toBe("saved before enrichment");
  });
});
