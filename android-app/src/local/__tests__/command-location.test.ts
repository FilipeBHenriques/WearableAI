import { describe, expect, it } from "vitest";
import { classifyText, detectCommand } from "../analysis";
import { LocalAppService } from "../localAppService";
import { findRelevantLocation } from "../location";
import { InMemoryRepository } from "../memoryRepository";
import type { NativeAi } from "../types";

const unavailableAi: NativeAi = {
  async isAvailable() {
    throw new Error("native bridge missing");
  },
  async transcribe() {
    throw new Error("unavailable");
  },
  async embed() {
    throw new Error("unavailable");
  },
  async generateJson() {
    throw new Error("unavailable");
  },
};

describe("commands and locations", () => {
  it("uses deterministic command and classification fallbacks when AI is unavailable", async () => {
    await expect(detectCommand("save this location as Workshop", unavailableAi)).resolves.toEqual({
      type: "save_location",
      location_name: "Workshop",
    });
    await expect(classifyText("Maybe consider a solar charger", unavailableAi)).resolves.toBe("Idea");
  });

  it("saves a location command without creating a note", async () => {
    const repository = new InMemoryRepository();
    const app = new LocalAppService({
      repository,
      ai: unavailableAi,
      locationProvider: {
        async getCurrentCoordinates() {
          return { latitude: 40.1, longitude: -8.2 };
        },
      },
    });

    const result = await app.processText("remember this place as Gym");

    expect(result).toMatchObject({
      saved: false,
      command_processed: true,
      command_type: "save_location",
      location_name: "Gym",
      location_latitude: 40.1,
      location_longitude: -8.2,
    });
    expect(await repository.listNotes()).toEqual([]);
  });

  it("links exact location references and clears links on deletion", async () => {
    const repository = new InMemoryRepository();
    const gym = await repository.upsertLocation("gym", 40.1, -8.2);
    const note = await repository.createNote("stretch once I get to the gym");
    const match = await findRelevantLocation(note.text, await repository.listLocations());
    await repository.updateNote(note.id, { location_id: match?.id ?? null });

    expect((await repository.getNote(note.id))?.location_name).toBe("gym");
    expect(await repository.deleteLocation(gym.id)).toBe(true);
    expect(await repository.getNote(note.id)).toMatchObject({
      location_id: null,
      location_name: null,
    });
  });
});
