import { CaptureQueue } from "./capture";
import { TypedEventBus } from "./eventBus";
import { proximitySuggestions } from "./location";
import { NoteService } from "./noteService";
import { NotePipeline, type PipelineOptions } from "./pipeline";
import type { LocalRepository } from "./repository";
import {
  ACTIVE_STATUS,
  type AudioCapture,
  type AudioProvider,
  type CaptureJob,
  type CaptureResult,
  type Coordinates,
  type DeleteResult,
  type DomainEvents,
  type Location,
  type LocationProvider,
  type LocalHealth,
  type NativeAi,
  type NoteStatus,
  type NoteView,
  type ProximitySuggestion,
  type RecordingJobResult,
  type StatusResult,
  type Unsubscribe,
} from "./types";

export interface LocalAppServiceOptions {
  repository: LocalRepository;
  ai?: NativeAi;
  audio?: AudioProvider;
  locationProvider?: LocationProvider;
  events?: TypedEventBus<DomainEvents>;
  pipelineHandlers?: PipelineOptions["handlers"];
  onPipelineStepError?: PipelineOptions["onStepError"];
}

/** Local equivalent of every current backend API operation. */
export class LocalAppService {
  readonly events: TypedEventBus<DomainEvents>;
  readonly notes: NoteService;
  readonly pipeline: NotePipeline;
  readonly capture: CaptureQueue;

  constructor(private readonly options: LocalAppServiceOptions) {
    this.events = options.events ?? new TypedEventBus<DomainEvents>();
    this.notes = new NoteService(options.repository, this.events);
    this.pipeline = new NotePipeline({
      repository: options.repository,
      events: this.events,
      notes: this.notes,
      ai: options.ai,
      locationProvider: options.locationProvider,
      handlers: options.pipelineHandlers,
      onStepError: options.onPipelineStepError,
    });
    this.capture = new CaptureQueue(
      options.repository,
      this.events,
      this.pipeline,
      options.audio ?? unavailableAudio,
      options.ai,
    );
  }

  initialize(): Promise<void> {
    return this.options.repository.initialize();
  }

  async health(): Promise<LocalHealth> {
    try {
      const available = this.options.ai
        ? ((await this.options.ai.isAvailable?.()) ?? true)
        : false;
      return {
        storage: "local",
        native_ai_available: available,
        native_ai_error: null,
      };
    } catch (error) {
      return {
        storage: "local",
        native_ai_available: false,
        native_ai_error: error instanceof Error ? error.message : String(error),
      };
    }
  }

  subscribe<K extends keyof DomainEvents>(
    type: K,
    handler: (payload: DomainEvents[K]) => void | Promise<void>,
  ): Unsubscribe {
    return this.events.subscribe(type, handler);
  }

  listNotes(status: NoteStatus | "all" | null = null): Promise<NoteView[]> {
    return this.notes.listTrees(status === "all" ? null : status);
  }

  getNote(id: number): Promise<NoteView | null> {
    return this.notes.getTree(id);
  }

  async getNoteAudioPath(id: number): Promise<string | null> {
    return (await this.options.repository.getNote(id))?.audio_path ?? null;
  }

  todayRepeats(day = new Date()): Promise<NoteView[]> {
    return this.notes.todayRepeatViews(day);
  }

  async deleteNote(id: number): Promise<DeleteResult> {
    await this.notes.delete(id, this.options.audio?.delete?.bind(this.options.audio));
    return { deleted: id };
  }

  async markNoteStatus(id: number, status: NoteStatus, day = new Date()): Promise<StatusResult | null> {
    if (status !== ACTIVE_STATUS && status !== "done")
      throw new Error(`Unsupported note status: ${status}`);
    if (!(await this.options.repository.getNote(id))) return null;
    await this.notes.markAs(id, status, day);
    const note = await this.options.repository.getNote(id);
    return note ? { id, status: note.status } : null;
  }

  async toggleNoteStatus(id: number, day = new Date()): Promise<StatusResult | null> {
    const status = await this.notes.toggleStatus(id, day);
    return status == null ? null : { id, status };
  }

  processText(text: string): Promise<CaptureResult> {
    return this.pipeline.processText(text);
  }

  listLocations(): Promise<Location[]> {
    return this.options.repository.listLocations();
  }

  async deleteLocation(id: number): Promise<DeleteResult | null> {
    if (!(await this.options.repository.deleteLocation(id))) return null;
    this.events.publish("locations_changed", { location_id: id });
    return { deleted: id };
  }

  async startRecording(): Promise<RecordingJobResult> {
    const job = await this.capture.startRecording();
    return { job_id: job.id, status: job.status };
  }

  async stopRecording(): Promise<RecordingJobResult> {
    const job = await this.capture.stopRecording();
    return { job_id: job.id, status: job.status };
  }

  activeCaptureJobs(): Promise<CaptureJob[]> {
    return this.capture.activeJobs();
  }

  async checkProximity(
    coordinates?: Coordinates,
    radiusMeters = 200,
    day = new Date(),
  ): Promise<ProximitySuggestion[]> {
    const current =
      coordinates ??
      (await this.requireLocationProvider().getCurrentCoordinates());
    const suggestions = await proximitySuggestions(
      current,
      this.options.repository,
      radiusMeters,
      day,
    );
    const nearest = suggestions[0];
    this.events.publish("gps_suggestions", {
      location: nearest?.location ?? null,
      coordinates: current,
      notes: nearest?.notes ?? [],
    });
    return suggestions;
  }

  private requireLocationProvider(): LocationProvider {
    if (!this.options.locationProvider)
      throw new Error("A location provider is required for GPS operations.");
    return this.options.locationProvider;
  }
}

const unavailableAudio: AudioProvider = {
  async start(): Promise<void> {
    throw new Error("Audio capture is unavailable.");
  },
  async stop(): Promise<AudioCapture> {
    throw new Error("Audio capture is unavailable.");
  },
};
