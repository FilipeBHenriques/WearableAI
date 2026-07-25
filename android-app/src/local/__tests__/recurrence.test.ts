import { describe, expect, it } from "vitest";
import { TypedEventBus } from "../eventBus";
import { InMemoryRepository } from "../memoryRepository";
import { NoteService } from "../noteService";
import {
  analyzeRecurrence,
  completedOn,
  isDueOn,
  repeatDoneStatus,
} from "../recurrence";

describe("recurrence and completion", () => {
  it("parses deterministic daily, weekly, monthly, yearly and one-time cases", async () => {
    await expect(analyzeRecurrence("drink water every day")).resolves.toMatchObject({
      repeat_cycle: "daily",
    });
    await expect(analyzeRecurrence("gym every Monday and Friday at 6 pm")).resolves.toEqual({
      repeat_cycle: "weekly",
      repeat_days: [1, 5],
      repeat_months: null,
      repeat_time: "18:00",
    });
    await expect(analyzeRecurrence("pay rent every month on the 1st")).resolves.toMatchObject({
      repeat_cycle: "monthly",
      repeat_days: [1],
    });
    await expect(analyzeRecurrence("renew every year on July 2")).resolves.toMatchObject({
      repeat_cycle: "yearly",
      repeat_days: [2],
      repeat_months: [7],
    });
    await expect(analyzeRecurrence("finish this by next Friday")).resolves.toMatchObject({
      repeat_cycle: null,
    });
  });

  it("completes only today's occurrence and can reopen it", async () => {
    const repository = new InMemoryRepository();
    const service = new NoteService(repository, new TypedEventBus());
    const note = await repository.createNote("daily water");
    await repository.updateNote(note.id, { repeat_cycle: "daily" });
    const day = new Date(2026, 6, 19, 12);

    expect(await service.toggleStatus(note.id, day)).toBe(repeatDoneStatus(day));
    const completed = (await repository.getNote(note.id))!;
    expect(completedOn(completed, day)).toBe(true);
    expect(await service.getAll("active", day)).toEqual([]);

    expect(await service.toggleStatus(note.id, day)).toBe("active");
    expect((await service.getAll("active", day)).map((item) => item.id)).toEqual([note.id]);
  });

  it("evaluates weekly due dates using ISO weekdays", async () => {
    const repository = new InMemoryRepository();
    const note = await repository.createNote("weekly");
    const monday = (await repository.updateNote(note.id, {
      repeat_cycle: "weekly",
      repeat_days: [1],
    }))!;
    expect(isDueOn(monday, new Date(2026, 6, 20, 12))).toBe(true);
    expect(isDueOn(monday, new Date(2026, 6, 21, 12))).toBe(false);
  });
});
