import { registerPlugin, type Plugin } from "@capacitor/core";
import { extractJsonObject } from "../local/ai";
import type {
  AudioCapture,
  AudioProvider,
  Coordinates,
  LocationProvider,
  NativeAi,
} from "../local/types";

export interface LocalAiStatus {
  available: boolean;
  nativeLoaded: boolean;
  embeddingAvailable: boolean;
  missingModels: string[];
  error: string | null;
  nativeStatus?: string | null;
}

interface LocalAiPlugin extends Plugin {
  warmup(): Promise<LocalAiStatus>;
  status(): Promise<LocalAiStatus>;
  transcribe(options: { path: string }): Promise<{ text: string }>;
  generate(options: { prompt: string; maxTokens?: number }): Promise<{ text: string }>;
  embed(options: { texts: string[] }): Promise<{ vectors: number[][] }>;
}

interface NativeAudioResult {
  path: string;
  uri: string;
  mimeType: string;
  sizeBytes: number;
  durationMs: number;
}

interface LocalAudioPlugin extends Plugin {
  start(): Promise<{ recording: boolean }>;
  stop(): Promise<NativeAudioResult>;
  retain(options: { path: string; noteId: number }): Promise<{ path: string; uri: string }>;
  delete(options: { path: string }): Promise<void>;
}

interface LocalLocationPlugin extends Plugin {
  getCurrentCoordinates(options?: {
    timeoutMs?: number;
    maxAgeMs?: number;
  }): Promise<Coordinates & { accuracyMeters?: number; timestamp?: number }>;
}

export const LocalAI = registerPlugin<LocalAiPlugin>("LocalAI");
export const LocalAudio = registerPlugin<LocalAudioPlugin>("LocalAudio");
export const LocalLocation = registerPlugin<LocalLocationPlugin>("LocalLocation");

export class CapacitorNativeAi implements NativeAi {
  private lastStatus: LocalAiStatus | null = null;

  async warmup(): Promise<LocalAiStatus> {
    return (this.lastStatus = await LocalAI.warmup());
  }

  async status(): Promise<LocalAiStatus> {
    return (this.lastStatus = await LocalAI.status());
  }

  async isAvailable(): Promise<boolean> {
    return (this.lastStatus ?? (await this.status())).available;
  }

  async transcribe(audio: AudioCapture): Promise<string> {
    if (!audio.native_path) throw new Error("Native transcription requires a WAV file path.");
    return (await LocalAI.transcribe({ path: audio.native_path })).text;
  }

  async embed(texts: string[]): Promise<number[][]> {
    return (await LocalAI.embed({ texts })).vectors;
  }

  async generateJson<T extends object>(prompt: string): Promise<T> {
    const result = await LocalAI.generate({ prompt, maxTokens: 512 });
    return extractJsonObject<T>(result.text);
  }
}

export class CapacitorAudioProvider implements AudioProvider {
  async start(): Promise<void> {
    await LocalAudio.start();
  }

  async stop(): Promise<AudioCapture> {
    const result = await LocalAudio.stop();
    return {
      native_path: result.path,
      uri: result.uri,
      mime_type: result.mimeType,
      duration_ms: result.durationMs,
    };
  }

  async saveForNote(audio: AudioCapture, noteId: number): Promise<string | null> {
    if (!audio.native_path) return null;
    return (await LocalAudio.retain({ path: audio.native_path, noteId })).path;
  }

  async delete(path: string): Promise<void> {
    await LocalAudio.delete({ path });
  }
}

export class CapacitorLocationProvider implements LocationProvider {
  async getCurrentCoordinates(): Promise<Coordinates> {
    const { latitude, longitude } = await LocalLocation.getCurrentCoordinates();
    return { latitude, longitude };
  }
}
