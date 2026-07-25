import { describe, expect, it, vi } from "vitest";
import { CaptureQueue } from "../capture";
import { TypedEventBus } from "../eventBus";
import { InMemoryRepository } from "../memoryRepository";
import { NoteService } from "../noteService";
import { NotePipeline } from "../pipeline";
import type { AudioProvider, CaptureJobStatus, DomainEvents, NativeAi } from "../types";

function setup(ai?: NativeAi) {
  const repository = new InMemoryRepository();
  const events = new TypedEventBus<DomainEvents>();
  const notes = new NoteService(repository, events);
  const pipeline = new NotePipeline({ repository, events, notes, ai });
  const audio: AudioProvider = {
    start: vi.fn(async () => undefined),
    stop: vi.fn(async () => ({ data: new Uint8Array([1]) })),
    saveForNote: vi.fn(async (_capture, id) => `note-${id}.wav`),
  };
  return { repository, events, queue: new CaptureQueue(repository, events, pipeline, audio, ai) };
}

describe("capture queue transitions", () => {
  it("saves raw before enrichment and reaches ready", async () => {
    const ai: NativeAi = {
      async isAvailable() {
        return true;
      },
      async transcribe() {
        return "remember to send email tomorrow";
      },
      async embed(texts) {
        return texts.map((_, index) => [index === 0 ? 1 : 0, index]);
      },
      async generateJson<T extends object>() {
        return {} as T;
      },
    };
    const { repository, events, queue } = setup(ai);
    const statuses: CaptureJobStatus[] = [];
    events.subscribe("capture_job", (job) => {
      statuses.push(job.status);
    });
    const job = await repository.createCaptureJob();

    const ready = await queue.processAudio(job.id, { data: new Uint8Array([1, 2]) });

    expect(ready?.status).toBe("ready");
    expect(statuses).toEqual(["saved_raw", "saved_raw", "enriching", "ready"]);
    const saved = await repository.getNote(ready!.note_id!);
    expect(saved).toMatchObject({
      text: "remember to send email tomorrow",
      audio_path: `note-${ready!.note_id}.wav`,
    });
  });

  it("fails deterministically for empty audio or unavailable native transcription", async () => {
    const empty = setup();
    const first = await empty.repository.createCaptureJob();
    expect((await empty.queue.processAudio(first.id, { data: new Uint8Array() }))?.error).toBe(
      "No audio captured.",
    );

    const unavailable = setup();
    const second = await unavailable.repository.createCaptureJob();
    expect(
      (await unavailable.queue.processAudio(second.id, { data: new Uint8Array([1]) }))?.error,
    ).toBe("Could not transcribe audio.");
  });

  it("accepts native path-backed audio without copying WAV bytes into JavaScript", async () => {
    const transcribe = vi.fn(async () => "path backed note");
    const ai: NativeAi = {
      isAvailable: async () => true,
      transcribe,
      embed: async (texts) => texts.map(() => [1]),
      generateJson: async <T extends object>() => ({} as T),
    };
    const { repository, queue } = setup(ai);
    const job = await repository.createCaptureJob();

    const result = await queue.processAudio(job.id, {
      native_path: "/private/recordings/capture.wav",
      mime_type: "audio/wav",
    });

    expect(result?.status).toBe("ready");
    expect(transcribe).toHaveBeenCalledWith(expect.objectContaining({
      native_path: "/private/recordings/capture.wav",
    }));
  });

  it("marks the job failed when stopping audio fails", async () => {
    const repository = new InMemoryRepository();
    const events = new TypedEventBus<DomainEvents>();
    const notes = new NoteService(repository, events);
    const pipeline = new NotePipeline({ repository, events, notes });
    const queue = new CaptureQueue(repository, events, pipeline, {
      async start() {},
      async stop() {
        throw new Error("microphone disconnected");
      },
    });
    const job = await queue.startRecording();

    await expect(queue.stopRecording()).rejects.toThrow("microphone disconnected");
    expect(await queue.getJob(job.id)).toMatchObject({
      status: "failed",
      error: "microphone disconnected",
    });
  });
});
