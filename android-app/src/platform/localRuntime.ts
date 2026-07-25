import { Capacitor } from "@capacitor/core";
import { InMemoryRepository } from "../local/memoryRepository";
import { LocalAppService } from "../local/localAppService";
import { CapacitorSqliteRepository, createCapacitorDatabase } from "../local/sqliteRepository";
import type { LocalHealth, LocationProvider } from "../local/types";
import {
  CapacitorAudioProvider,
  CapacitorLocationProvider,
  CapacitorNativeAi,
  type LocalAiStatus,
} from "./nativePlugins";

export type StartupPhase = "starting" | "warming" | "ready" | "error";

export interface RuntimeStatus {
  phase: StartupPhase;
  platform: "android-local" | "browser-memory";
  storage: "starting" | "ready" | "error";
  model: "checking" | "ready" | "missing" | "unavailable";
  message: string;
  missingModels: string[];
  error: string | null;
}

export interface LocalRuntime {
  service: LocalAppService;
  status: RuntimeStatus;
  health: LocalHealth;
  toAudioUrl(path: string): string;
}

type StatusListener = (status: RuntimeStatus) => void;

const browserLocation: LocationProvider = {
  async getCurrentCoordinates() {
    return { latitude: 51.50735, longitude: -0.12776 };
  },
};

export async function createLocalRuntime(onStatus?: StatusListener): Promise<LocalRuntime> {
  const native = Capacitor.isNativePlatform();
  let status: RuntimeStatus = {
    phase: "starting",
    platform: native ? "android-local" : "browser-memory",
    storage: "starting",
    model: native ? "checking" : "unavailable",
    message: "Opening local storage…",
    missingModels: [],
    error: null,
  };
  const update = (patch: Partial<RuntimeStatus>) => {
    status = { ...status, ...patch };
    onStatus?.(status);
  };
  onStatus?.(status);

  try {
    const repository = native
      ? new CapacitorSqliteRepository(await createCapacitorDatabase())
      : new InMemoryRepository();
    const ai = native ? new CapacitorNativeAi() : undefined;
    const service = new LocalAppService({
      repository,
      ai,
      audio: native ? new CapacitorAudioProvider() : undefined,
      locationProvider: native ? new CapacitorLocationProvider() : browserLocation,
    });
    await service.initialize();
    update({ storage: "ready" });

    if (!native) {
      await seedBrowserDemo(service);
      const health = await service.health();
      update({
        phase: "ready",
        message: "Browser demo uses deterministic in-memory storage.",
      });
      return {
        service,
        status,
        health,
        toAudioUrl: (path) => path,
      };
    }

    update({ phase: "warming", message: "Warming local models…" });
    let modelStatus: LocalAiStatus;
    try {
      modelStatus = await ai!.warmup();
    } catch (warmupError) {
      try {
        modelStatus = await ai!.status();
      } catch {
        throw warmupError;
      }
    }
    const model = modelState(modelStatus);
    const health = await service.health();
    update({
      phase: "ready",
      model,
      missingModels: modelStatus.missingModels,
      error: modelStatus.error,
      message:
        model === "ready"
          ? "Local storage and models are ready."
          : "Text notes remain available; audio inference is unavailable.",
    });
    return {
      service,
      status,
      health,
      toAudioUrl: (path) => Capacitor.convertFileSrc(path),
    };
  } catch (error) {
    update({
      phase: "error",
      storage: status.storage === "ready" ? "ready" : "error",
      model: "unavailable",
      message: "Local startup failed.",
      error: errorText(error),
    });
    throw Object.assign(error instanceof Error ? error : new Error(errorText(error)), {
      runtimeStatus: status,
    });
  }
}

function modelState(status: LocalAiStatus): RuntimeStatus["model"] {
  if (status.available) return "ready";
  if (status.missingModels.length) return "missing";
  return "unavailable";
}

async function seedBrowserDemo(service: LocalAppService): Promise<void> {
  if ((await service.listNotes("all")).length) return;
  await service.processText("Review the wearable prototype tomorrow at 10:00");
  await service.processText("Write down local-first product ideas");
  await service.processText("Stretch every day at 08:00");
}

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
