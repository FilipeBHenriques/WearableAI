import { describe, expect, it } from "vitest";
import { InMemoryRepository } from "../memoryRepository";
import type { NativeAi } from "../types";
import {
  analyzeUrgency,
  calculateUrgency,
  estimateDuration,
  extractDeadline,
  parseDeadline,
  scoreFromSlackHours,
} from "../urgency";

function mockAi(payload: unknown): NativeAi {
  return {
    async transcribe() {
      return "";
    },
    async embed() {
      return [];
    },
    async generateJson<T extends object>() {
      return payload as T;
    },
  };
}

describe("urgency, deadline and duration", () => {
  it("parses date-only deadlines at end of day and exact next weekdays", () => {
    expect(parseDeadline("2026-07-20")?.getHours()).toBe(23);
    expect(
      extractDeadline("deliver homework by next Friday", new Date(2026, 6, 18, 15)),
    ).toBe("2026-07-24T23:59");
  });

  it("uses a monotonic bounded slack curve and duration raises urgency", () => {
    expect(scoreFromSlackHours(-1)).toBeGreaterThanOrEqual(97);
    expect(scoreFromSlackHours(0)).toBeGreaterThanOrEqual(scoreFromSlackHours(24));
    expect(scoreFromSlackHours(24)).toBeGreaterThanOrEqual(scoreFromSlackHours(168));
    expect(calculateUrgency(null)).toBe(0);
    const now = new Date(2026, 6, 19, 12);
    const deadline = "2026-07-19T18:00";
    expect(calculateUrgency(deadline, now, 300)).toBeGreaterThanOrEqual(
      calculateUrgency(deadline, now),
    );
  });

  it("leaves deadline and duration unset when there is no clear reason", async () => {
    const repository = new InMemoryRepository();
    const note = await repository.createNote("buy milk when convenient");
    const now = new Date(2026, 6, 19, 12);

    const urgency = await analyzeUrgency(
      note,
      mockAi({ has_deadline: false, deadline_at: null, reason: null }),
      now,
    );
    const duration = await estimateDuration(note);

    expect(urgency.deadline_at).toBeNull();
    expect(urgency.urgency_score).toBe(0);
    expect(urgency.urgency_reason).toBeNull();
    expect(duration.estimated_duration_minutes).toBeNull();
  });

  it("does not invent deadlines when AI is unavailable", async () => {
    const repository = new InMemoryRepository();
    const note = await repository.createNote("write report by tomorrow, about 2 hours");
    const now = new Date(2026, 6, 19, 12);

    const urgency = await analyzeUrgency(note, undefined, now);
    const duration = await estimateDuration(note);

    expect(urgency.deadline_at).toBeNull();
    expect(urgency.urgency_score).toBe(0);
    expect(duration.estimated_duration_minutes).toBeNull();
  });

  it("does not let weekday heuristics invent a deadline when LLM says none", async () => {
    const repository = new InMemoryRepository();
    const note = await repository.createNote("talk about Friday plans sometime");
    const now = new Date(2026, 6, 18, 15);

    const urgency = await analyzeUrgency(
      note,
      mockAi({ has_deadline: false, deadline_at: "2026-07-24T23:59", reason: "Friday" }),
      now,
    );

    expect(urgency.deadline_at).toBeNull();
    expect(urgency.urgency_score).toBe(0);
  });

  it("rejects invented deadlines when the note has no temporal cue", async () => {
    const repository = new InMemoryRepository();
    const note = await repository.createNote("buy milk when convenient");
    const now = new Date(2026, 6, 19, 12);

    const urgency = await analyzeUrgency(
      note,
      mockAi({
        has_deadline: true,
        deadline_at: "2026-07-19T23:59",
        reason: "model invented this",
      }),
      now,
    );

    expect(urgency.deadline_at).toBeNull();
    expect(urgency.urgency_score).toBe(0);
  });

  it("corrects next-weekday deadlines only after LLM affirms has_deadline", async () => {
    const repository = new InMemoryRepository();
    const note = await repository.createNote("deliver homework by next Friday");
    const now = new Date(2026, 6, 18, 15);

    const urgency = await analyzeUrgency(
      note,
      mockAi({
        has_deadline: true,
        deadline_at: "2026-07-20T23:59",
        reason: "Friday",
      }),
      now,
    );

    expect(urgency.deadline_at).toBe("2026-07-24T23:59");
    expect(urgency.rank_score).toBe(urgency.urgency_score);
    expect(urgency.urgency_reason).toBe("Friday");
  });

  it("keeps duration null when the model omits an estimate", async () => {
    const repository = new InMemoryRepository();
    const note = await repository.createNote("finish the essay by Friday");
    const duration = await estimateDuration(
      note,
      mockAi({ estimated_duration_minutes: null, reason: null }),
    );
    expect(duration.estimated_duration_minutes).toBeNull();
  });

  it("accepts explicit duration estimates from the model", async () => {
    const repository = new InMemoryRepository();
    const note = await repository.createNote("write report by tomorrow");
    const duration = await estimateDuration(
      note,
      mockAi({ estimated_duration_minutes: 120, reason: "about two hours" }),
    );
    expect(duration.estimated_duration_minutes).toBe(120);
    expect(duration.reason).toBe("about two hours");
  });
});
