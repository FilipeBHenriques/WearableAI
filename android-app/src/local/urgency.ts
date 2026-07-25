import { aiJson } from "./ai";
import type { NativeAi, Note } from "./types";

export interface UrgencyResult {
  deadline_at: string | null;
  urgency_score: number;
  rank_score: number;
  urgency_reason: string | null;
}

export interface DurationResult {
  estimated_duration_minutes: number | null;
  reason: string | null;
}

const weekdays: Record<string, number> = {
  sunday: 0,
  monday: 1,
  tuesday: 2,
  wednesday: 3,
  thursday: 4,
  friday: 5,
  saturday: 6,
};

export function parseDeadline(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? new Date(`${value}T23:59:00`)
    : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function scoreFromSlackHours(slackHours: number): number {
  if (slackHours < 0) {
    return clamp(Math.round(97 + 3 * (1 - Math.exp(-(-slackHours) / 6))), 97, 100);
  }
  const score = 100 / (1 + Math.exp(0.015 * (slackHours - 200)));
  return clamp(Math.round(Math.max(score, 5)), 0, 100);
}

export function calculateUrgency(
  deadlineAt: string | null,
  now = new Date(),
  durationMinutes: number | null = null,
): number {
  const deadline = parseDeadline(deadlineAt);
  if (!deadline) return 0;
  const hoursUntilDue = (deadline.getTime() - now.getTime()) / 3_600_000;
  const slackHours =
    durationMinutes == null ? hoursUntilDue : hoursUntilDue - durationMinutes / 60;
  return scoreFromSlackHours(slackHours);
}

/** Corrects weekday deadlines when the LLM already affirmed has_deadline (MVP parity). */
export function relativeWeekdayDeadline(text: string, now = new Date()): string | null {
  const weekday = text.match(
    /\b(?:by|before|due|deadline|deliver|finish|submit|complete)?\s*(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i,
  );
  if (!weekday) return null;
  let ahead = (weekdays[weekday[2].toLowerCase()] - now.getDay() + 7) % 7;
  if (weekday[1] || ahead === 0) ahead ||= 7;
  const deadline = new Date(now);
  deadline.setDate(now.getDate() + ahead);
  deadline.setHours(23, 59, 0, 0);
  return localIsoMinutes(deadline);
}

/** @deprecated Use relativeWeekdayDeadline — kept for tests that pin weekday math. */
export const extractDeadline = relativeWeekdayDeadline;

export async function analyzeUrgency(
  note: Note,
  ai?: NativeAi,
  now = new Date(),
): Promise<UrgencyResult> {
  const parsed = await aiJson<{
    has_deadline?: boolean;
    deadline_at?: string | null;
    deadline_date?: string | null;
    reason?: string | null;
  }>(ai, buildDeadlinePrompt(note, now));

  if (!parsed) {
    return emptyUrgency();
  }

  const hasDeadline = Boolean(parsed.has_deadline);
  // Small on-device models invent deadlines; require a real temporal cue in the note.
  if (!hasDeadline || !hasDeadlineSignal(note.text)) {
    return emptyUrgency();
  }

  const rawDeadline = String(parsed.deadline_at ?? parsed.deadline_date ?? "").trim();
  let deadline = parseDeadline(rawDeadline);
  const weekdayCorrection = relativeWeekdayDeadline(note.text, now);
  if (weekdayCorrection) deadline = parseDeadline(weekdayCorrection);

  const deadlineAt = deadline ? localIsoMinutes(deadline) : null;
  const score = calculateUrgency(deadlineAt, now, note.estimated_duration_minutes);
  const reason = String(parsed.reason ?? "").trim() || null;
  return {
    deadline_at: deadlineAt,
    urgency_score: score,
    rank_score: score,
    urgency_reason: reason,
  };
}

export async function estimateDuration(note: Note, ai?: NativeAi): Promise<DurationResult> {
  const parsed = await aiJson<{
    estimated_duration_minutes?: number | null;
    reason?: string | null;
  }>(ai, buildDurationPrompt(note));

  if (!parsed || parsed.estimated_duration_minutes == null) {
    return { estimated_duration_minutes: null, reason: null };
  }

  const minutes = Number(parsed.estimated_duration_minutes);
  if (!Number.isFinite(minutes)) {
    return { estimated_duration_minutes: null, reason: null };
  }

  return {
    estimated_duration_minutes: clamp(Math.round(minutes), 0, 20_160),
    reason: String(parsed.reason ?? "").trim() || null,
  };
}

export function refreshUrgency(note: Note, now = new Date()): UrgencyResult {
  const score = calculateUrgency(note.deadline_at, now, note.estimated_duration_minutes);
  return {
    deadline_at: note.deadline_at,
    urgency_score: score,
    rank_score: score,
    urgency_reason: note.urgency_reason,
  };
}

function emptyUrgency(): UrgencyResult {
  return {
    deadline_at: null,
    urgency_score: 0,
    rank_score: 0,
    urgency_reason: null,
  };
}

function hasDeadlineSignal(text: string): boolean {
  return (
    /\b(today|tonight|tomorrow|deadline|due|by|before)\b/i.test(text) ||
    /\b(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i.test(text) ||
    /\b(next\s+week|this\s+week|end\s+of\s+(the\s+)?(day|week|month))\b/i.test(text) ||
    /\bin\s+\d+\s*(minutes?|mins?|hours?|hrs?|days?|weeks?)\b/i.test(text) ||
    /\b\d{4}-\d{2}-\d{2}\b/.test(text) ||
    /\b\d{1,2}\/\d{1,2}(?:\/\d{2,4})?\b/.test(text) ||
    /\b(?:at|by)\s+\d{1,2}(?::\d{2})?\s*(am|pm)?\b/i.test(text)
  );
}

function buildDeadlinePrompt(note: Note, now: Date): string {
  return `Return one JSON object only. Do not explain, do not use markdown, do not use a code fence.

Analyze this note for deadline only.

Current local datetime: ${localIsoMinutes(now)}
Current local date: ${localIsoMinutes(now).slice(0, 10)}

The JSON object must use this exact shape:
{"has_deadline":false,"deadline_at":null,"reason":null}

Rules:
- has_deadline must be true only when the note contains a clear due date or relative deadline.
- deadline_at must be YYYY-MM-DDTHH:MM when has_deadline is true, otherwise null.
- Include the best inferred local time. If the note gives only a date, use 23:59 for that date.
- Resolve relative deadlines like today at 5pm, tomorrow, or next Friday using the current local datetime.
- reason must be a real short explanation for the chosen deadline, not a placeholder.
- If there is no clear deadline, return has_deadline false and null fields. Do not invent one.

Note: ${note.text}
JSON only:`;
}

function buildDurationPrompt(note: Note): string {
  return `Return one JSON object only. Do not explain, do not use markdown, do not use a code fence.

Estimate realistic hands-on effort time for a typical person to finish this note.

Category: ${note.category}
Note: ${note.text}

The JSON object must use this exact shape:
{"estimated_duration_minutes":0,"reason":null}

Rules:
- estimated_duration_minutes must be a non-negative integer (minutes of actual work).
- Scale by difficulty. Tiny chores and huge writing projects must NOT get the same estimate.
- Examples of scale:
  - take out garbage / quick email / short call: 5-15
  - groceries / clean room / short meeting: 30-90
  - study session / build a small feature: 120-240
  - write a long essay/report/thesis chapter: hundreds to thousands of minutes
  - "100 page essay" style work: at least several thousand minutes
- Use 0 for ideas, thoughts, or notes that are not actionable.
- Prefer effort time, not calendar span until a deadline.
- reason must briefly justify the scale chosen.

JSON only:`;
}

function localIsoMinutes(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));
