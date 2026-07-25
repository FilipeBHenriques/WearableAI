import { classifyText, decideParent, detectCommand, type Command, type CommandType } from "./analysis";
import type { TypedEventBus } from "./eventBus";
import { applyLocation } from "./location";
import { analyzeRecurrence } from "./recurrence";
import type { LocalRepository } from "./repository";
import { analyzeUrgency, estimateDuration, refreshUrgency } from "./urgency";
import {
  emptyCaptureResult,
  type CaptureResult,
  type DomainEvents,
  type LocationProvider,
  type NativeAi,
  type Note,
} from "./types";
import { NoteService } from "./noteService";

export type PipelineStep =
  | "detect_command"
  | "save_note"
  | "relationship"
  | "classification"
  | "urgency"
  | "estimate_duration"
  | "location"
  | "recurrence";

export const INTAKE_STEPS: readonly PipelineStep[] = ["detect_command", "save_note"];
export const ENRICH_STEPS: readonly PipelineStep[] = [
  "relationship",
  "classification",
  "urgency",
  "estimate_duration",
  "location",
  "recurrence",
];

export interface PipelineContext {
  text: string;
  note: Note | null;
  command_type: CommandType | null;
  stopped: boolean;
  saved: boolean;
  message: string | null;
  location_id: number | null;
  location_name: string | null;
  location_latitude: number | null;
  location_longitude: number | null;
}

export type PipelineHandler = (context: PipelineContext) => Promise<void>;

export interface PipelineOptions {
  repository: LocalRepository;
  events: TypedEventBus<DomainEvents>;
  notes: NoteService;
  ai?: NativeAi;
  locationProvider?: LocationProvider;
  handlers?: Partial<Record<PipelineStep, PipelineHandler>>;
  onStepError?: (step: PipelineStep, error: unknown) => void;
}

export class NotePipeline {
  private readonly handlers: Record<PipelineStep, PipelineHandler>;

  constructor(private readonly options: PipelineOptions) {
    this.handlers = {
      detect_command: (context) => this.detect(context),
      save_note: (context) => this.save(context),
      relationship: (context) => this.relationship(context),
      classification: (context) => this.classification(context),
      urgency: (context) => this.urgency(context),
      estimate_duration: (context) => this.duration(context),
      location: (context) => this.location(context),
      recurrence: (context) => this.recurrence(context),
      ...options.handlers,
    };
  }

  async runIntake(text: string): Promise<CaptureResult> {
    const context = this.newContext(text);
    if (!context) return emptyCaptureResult();
    await this.runSteps(INTAKE_STEPS, context, true);
    return this.result(context);
  }

  async runEnrich(noteId: number): Promise<CaptureResult> {
    const note = await this.options.repository.getNote(noteId);
    if (!note) return emptyCaptureResult();
    const context = this.context(note.text, note);
    await this.runSteps(ENRICH_STEPS, context, false);
    context.note = await this.options.repository.getNote(noteId);
    this.options.events.publish("notes_changed", { note_id: noteId, stage: "enriched" });
    return this.result(context);
  }

  async processText(text: string): Promise<CaptureResult> {
    const context = this.newContext(text);
    if (!context) return emptyCaptureResult();
    await this.runSteps(INTAKE_STEPS, context, true);
    if (context.stopped || !context.note) return this.result(context);
    await this.runSteps(ENRICH_STEPS, context, false);
    context.note = await this.options.repository.getNote(context.note.id);
    if (context.note)
      this.options.events.publish("notes_changed", { note_id: context.note.id, stage: "enriched" });
    return this.result(context);
  }

  private async runSteps(
    steps: readonly PipelineStep[],
    context: PipelineContext,
    failFast: boolean,
  ): Promise<void> {
    for (const step of steps) {
      if (context.stopped) return;
      if (failFast) await this.handlers[step](context);
      else {
        try {
          await this.handlers[step](context);
        } catch (error) {
          this.options.onStepError?.(step, error);
        }
      }
    }
  }

  private async detect(context: PipelineContext): Promise<void> {
    const command: Command = await detectCommand(context.text, this.options.ai);
    context.command_type = command.type;
    if (command.type !== "save_location") return;
    if (!command.location_name) {
      context.stopped = true;
      context.message = "Could not identify the location name.";
      return;
    }
    if (!this.options.locationProvider)
      throw new Error("A location provider is required to save the current location.");
    const coordinates = await this.options.locationProvider.getCurrentCoordinates();
    const location = await this.options.repository.upsertLocation(
      command.location_name,
      coordinates.latitude,
      coordinates.longitude,
    );
    this.options.events.publish("locations_changed", { location_id: location.id });
    Object.assign(context, {
      stopped: true,
      location_id: location.id,
      location_name: location.name,
      location_latitude: location.latitude,
      location_longitude: location.longitude,
      message: `Saved location '${location.name}'.`,
    });
  }

  private async save(context: PipelineContext): Promise<void> {
    const note = await this.options.repository.createNote(context.text);
    context.note = note;
    context.saved = true;
    context.command_type ??= "take_note";
    this.options.events.publish("notes_changed", { note_id: note.id });
  }

  private async relationship(context: PipelineContext): Promise<void> {
    if (!context.note || context.note.parent_note_id != null) return;
    const parent = await decideParent(context.note, this.options.repository, this.options.ai);
    if (parent != null) await this.update(context, { parent_note_id: parent });
  }

  private async classification(context: PipelineContext): Promise<void> {
    if (!context.note) return;
    await this.update(context, { category: await classifyText(context.note.text, this.options.ai) });
  }

  private async urgency(context: PipelineContext): Promise<void> {
    if (!context.note) return;
    await this.update(context, await analyzeUrgency(context.note, this.options.ai));
  }

  private async duration(context: PipelineContext): Promise<void> {
    if (!context.note?.deadline_at) return;
    const result = await estimateDuration(context.note, this.options.ai);
    if (result.estimated_duration_minutes == null) return;
    await this.update(context, {
      estimated_duration_minutes: result.estimated_duration_minutes,
    });
    if (context.note) await this.update(context, refreshUrgency(context.note));
  }

  private async location(context: PipelineContext): Promise<void> {
    if (!context.note) return;
    await applyLocation(context.note, this.options.repository, this.options.ai);
    context.note = await this.options.repository.getNote(context.note.id);
  }

  private async recurrence(context: PipelineContext): Promise<void> {
    if (!context.note) return;
    const recurrence = await analyzeRecurrence(context.note.text, this.options.ai);
    if (!recurrence.repeat_cycle) return;
    await this.update(context, { ...recurrence, category: "Goal" });
  }

  private async update(
    context: PipelineContext,
    patch: Parameters<LocalRepository["updateNote"]>[1],
  ): Promise<void> {
    if (context.note) context.note = await this.options.repository.updateNote(context.note.id, patch);
  }

  private newContext(text: string): PipelineContext | null {
    const clean = text.trim();
    return clean ? this.context(clean, null, false) : null;
  }

  private context(text: string, note: Note | null, saved = true): PipelineContext {
    return {
      text,
      note,
      command_type: note ? "take_note" : null,
      stopped: false,
      saved,
      message: null,
      location_id: null,
      location_name: null,
      location_latitude: null,
      location_longitude: null,
    };
  }

  private result(context: PipelineContext): CaptureResult {
    if (!context.note) {
      return {
        ...emptyCaptureResult(context.text),
        command_processed: context.stopped,
        command_type: context.command_type,
        message: context.message,
        location_id: context.location_id,
        location_name: context.location_name,
        location_latitude: context.location_latitude,
        location_longitude: context.location_longitude,
      };
    }
    return {
      ...this.options.notes.view(context.note),
      saved: true,
      command_processed: true,
      command_type: context.command_type ?? "take_note",
      message: context.message,
    };
  }
}
