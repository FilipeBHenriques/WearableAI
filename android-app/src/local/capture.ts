import { fixTranscript } from "./analysis";
import type { TypedEventBus } from "./eventBus";
import type { NotePipeline } from "./pipeline";
import type { LocalRepository } from "./repository";
import type {
  AudioCapture,
  AudioProvider,
  CaptureJob,
  CaptureJobStatus,
  DomainEvents,
  NativeAi,
} from "./types";

export class CaptureQueue {
  private recordingJobId: number | null = null;

  constructor(
    private readonly repository: LocalRepository,
    private readonly events: TypedEventBus<DomainEvents>,
    private readonly pipeline: NotePipeline,
    private readonly audio: AudioProvider,
    private readonly ai?: NativeAi,
  ) {}

  async startRecording(): Promise<CaptureJob> {
    if (this.recordingJobId != null) throw new Error("A recording is already active.");
    const job = await this.repository.createCaptureJob("recording");
    try {
      await this.audio.start();
    } catch (error) {
      await this.update(job.id, { status: "failed", error: errorText(error) });
      throw error;
    }
    this.recordingJobId = job.id;
    this.events.publish("capture_job", job);
    return job;
  }

  async stopRecording(): Promise<CaptureJob> {
    if (this.recordingJobId == null) throw new Error("No recording is active.");
    const jobId = this.recordingJobId;
    this.recordingJobId = null;
    let audio: AudioCapture;
    try {
      audio = await this.audio.stop();
    } catch (error) {
      await this.update(jobId, { status: "failed", error: errorText(error) });
      throw error;
    }
    const job = await this.update(jobId, { status: "transcribing", error: null });
    if (!job) throw new Error("Recording job was not found.");
    void this.processAudio(jobId, audio);
    return job;
  }

  async processAudio(jobId: number, audio: AudioCapture): Promise<CaptureJob | null> {
    try {
      if (!audio.native_path && !audio.data?.length)
        return this.update(jobId, { status: "failed", error: "No audio captured." });
      const transcript = await this.transcribe(audio);
      if (!transcript) {
        await this.discardTemporary(audio);
        return this.update(jobId, {
          status: "failed",
          error: "Could not transcribe audio.",
        });
      }
      const finalText = await fixTranscript(transcript, this.ai);
      await this.update(jobId, {
        status: "saved_raw",
        final_transcript: finalText,
        error: null,
      });
      const raw = await this.pipeline.runIntake(finalText);
      if (raw.id == null) {
        await this.discardTemporary(audio);
        return this.update(jobId, {
          status: raw.command_processed ? "ready" : "failed",
          error: raw.command_processed ? null : raw.message ?? "Could not save note.",
        });
      }
      const path = (await this.audio.saveForNote?.(audio, raw.id)) ?? null;
      if (path) await this.repository.updateNote(raw.id, { audio_path: path });
      await this.update(jobId, { status: "saved_raw", note_id: raw.id });
      this.events.publish("notes_changed", { note_id: raw.id, stage: "saved_raw" });
      await this.update(jobId, { status: "enriching" });
      await this.pipeline.runEnrich(raw.id);
      const ready = await this.update(jobId, { status: "ready", error: null });
      this.events.publish("notes_changed", { note_id: raw.id, stage: "ready" });
      return ready;
    } catch (error) {
      await this.discardTemporary(audio);
      return this.update(jobId, { status: "failed", error: errorText(error) });
    }
  }

  activeJobs(): Promise<CaptureJob[]> {
    return this.repository.listActiveCaptureJobs();
  }

  getJob(id: number): Promise<CaptureJob | null> {
    return this.repository.getCaptureJob(id);
  }

  private async transcribe(audio: AudioCapture): Promise<string> {
    if (!this.ai) return "";
    if ((await this.ai.isAvailable?.()) === false) return "";
    return (await this.ai.transcribe(audio)).trim();
  }

  private async discardTemporary(audio: AudioCapture): Promise<void> {
    if (audio.native_path) {
      try {
        await this.audio.delete?.(audio.native_path);
      } catch {
        // Preserve the capture error; stale private temp files can be pruned later.
      }
    }
  }

  private async update(
    id: number,
    patch: {
      status?: CaptureJobStatus;
      final_transcript?: string | null;
      note_id?: number | null;
      error?: string | null;
    },
  ): Promise<CaptureJob | null> {
    const job = await this.repository.updateCaptureJob(id, patch);
    if (job) this.events.publish("capture_job", job);
    return job;
  }
}

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
