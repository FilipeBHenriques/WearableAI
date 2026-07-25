import { describe, expect, it } from "vitest";
import { TypedEventBus } from "../eventBus";
import { haversineMeters, proximitySuggestions } from "../location";
import { InMemoryRepository } from "../memoryRepository";
import { repeatDoneStatus } from "../recurrence";
import type { DomainEvents } from "../types";

describe("GPS proximity", () => {
  it("calculates distance and returns only nearby suggestable notes", async () => {
    const repository = new InMemoryRepository();
    const gym = await repository.upsertLocation("gym", 40.1, -8.2);
    const home = await repository.upsertLocation("home", 41, -8);
    const nearby = await repository.createNote("stretch");
    const done = await repository.createNote("old reminder");
    const far = await repository.createNote("water plants");
    await repository.updateNote(nearby.id, { location_id: gym.id });
    await repository.updateNote(done.id, { location_id: gym.id, status: "done" });
    await repository.updateNote(far.id, { location_id: home.id });
    const current = { latitude: 40.1005, longitude: -8.2 };

    expect(haversineMeters(current, gym)).toBeLessThan(100);
    const result = await proximitySuggestions(current, repository, 200);
    expect(result).toHaveLength(1);
    expect(result[0].location.id).toBe(gym.id);
    expect(result[0].notes.map((note) => note.id)).toEqual([nearby.id]);
  });

  it("hides a repeat completed today but includes an available repeat", async () => {
    const repository = new InMemoryRepository();
    const location = await repository.upsertLocation("office", 40, -8);
    const available = await repository.createNote("daily standup");
    const completed = await repository.createNote("daily review");
    const day = new Date(2026, 6, 19, 12);
    await repository.updateNote(available.id, { location_id: location.id, repeat_cycle: "daily" });
    await repository.updateNote(completed.id, {
      location_id: location.id,
      repeat_cycle: "daily",
      status: repeatDoneStatus(day),
    });

    const result = await proximitySuggestions(location, repository, 10, day);
    expect(result[0].notes.map((note) => note.id)).toEqual([available.id]);
  });

  it("supports typed GPS events", () => {
    const events = new TypedEventBus<DomainEvents>();
    let seen = "";
    events.subscribe("gps_suggestions", ({ location }) => {
      seen = location?.name ?? "none";
    });
    events.publish("gps_suggestions", {
      location: null,
      coordinates: { latitude: 0, longitude: 0 },
      notes: [],
    });
    expect(seen).toBe("none");
  });
});
