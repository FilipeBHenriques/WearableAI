import { aiJson } from "./ai";
import type { NativeAi, Note, RepeatCycle } from "./types";

export const REPEAT_DONE_PREFIX = "repeat_done:";

export interface RecurrenceResult {
  repeat_cycle: RepeatCycle | null;
  repeat_days: number[] | null;
  repeat_months: number[] | null;
  repeat_time: string | null;
}

const none = (): RecurrenceResult => ({
  repeat_cycle: null,
  repeat_days: null,
  repeat_months: null,
  repeat_time: null,
});

const weekdays: Record<string, number> = {
  monday: 1, mon: 1, tuesday: 2, tue: 2, tues: 2, wednesday: 3, wed: 3,
  thursday: 4, thu: 4, thur: 4, thurs: 4, friday: 5, fri: 5,
  saturday: 6, sat: 6, sunday: 7, sun: 7,
};
const months: Record<string, number> = {
  january: 1, jan: 1, february: 2, feb: 2, march: 3, mar: 3, april: 4, apr: 4,
  may: 5, june: 6, jun: 6, july: 7, jul: 7, august: 8, aug: 8,
  september: 9, sep: 9, sept: 9, october: 10, oct: 10,
  november: 11, nov: 11, december: 12, dec: 12,
};

export function isRepeating(note: Note): boolean {
  return ["daily", "weekly", "monthly", "yearly"].includes(note.repeat_cycle ?? "");
}

export function localDateKey(day = new Date()): string {
  const local = new Date(day.getTime() - day.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

export function repeatDoneStatus(day = new Date()): `repeat_done:${string}` {
  return `${REPEAT_DONE_PREFIX}${localDateKey(day)}`;
}

export function completedOn(note: Note, day = new Date()): boolean {
  return note.status === repeatDoneStatus(day);
}

export function isDueOn(note: Note, day = new Date()): boolean {
  const isoWeekday = day.getDay() || 7;
  if (note.repeat_cycle === "daily") return true;
  if (note.repeat_cycle === "weekly") return (note.repeat_days ?? []).includes(isoWeekday);
  if (note.repeat_cycle === "monthly") return (note.repeat_days ?? []).includes(day.getDate());
  if (note.repeat_cycle === "yearly")
    return (
      (note.repeat_months ?? []).includes(day.getMonth() + 1) &&
      (note.repeat_days ?? []).includes(day.getDate())
    );
  return false;
}

export function isAvailableOn(note: Note, day = new Date()): boolean {
  return isDueOn(note, day) && !completedOn(note, day);
}

export function repeatDisplay(note: Note): string | null {
  if (!isRepeating(note)) return null;
  let base: string;
  if (note.repeat_cycle === "daily") base = "Daily";
  else if (note.repeat_cycle === "weekly") {
    const names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    base = (note.repeat_days ?? []).map((day) => names[day - 1]).filter(Boolean).join(" / ") || "Weekly";
  } else if (note.repeat_cycle === "monthly") {
    base = note.repeat_days?.length ? `Monthly on ${note.repeat_days.join(", ")}` : "Monthly";
  } else {
    const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const month = (note.repeat_months ?? []).map((item) => names[item - 1]).filter(Boolean).join(", ");
    const days = (note.repeat_days ?? []).join(", ");
    base = month || days ? `Yearly on ${month} ${days}`.trim() : "Yearly";
  }
  return note.repeat_time ? `${base} · ${note.repeat_time}` : base;
}

function normalizeTime(value: unknown): string | null {
  const match = String(value ?? "").trim().toLowerCase().match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$/);
  if (!match) return null;
  let hour = Number(match[1]);
  const minute = Number(match[2] ?? 0);
  if (match[3] === "pm" && hour < 12) hour += 12;
  if (match[3] === "am" && hour === 12) hour = 0;
  return hour <= 23 && minute <= 59
    ? `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`
    : null;
}

const repeatSignal = (text: string) =>
  /\b(every|each|repeat|repeating|recurring|daily|weekly|monthly|yearly|annually|weekdays?|weekends?)\b/i.test(text);
const weekdayNumbers = (text: string) =>
  [...new Set(Object.entries(weekdays).filter(([name]) => new RegExp(`\\b${name}\\b`, "i").test(text)).map(([, n]) => n))].sort((a, b) => a - b);
const oneTimeDeadline = (text: string) =>
  /\b(by|before|due|deadline|deliver|finish|submit|complete)\b/i.test(text) &&
  /\b(next\s+)?(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i.test(text);

export function heuristicRecurrence(text: string): RecurrenceResult {
  const dayNumbers = weekdayNumbers(text);
  if (oneTimeDeadline(text) && !repeatSignal(text) && dayNumbers.length <= 1) return none();
  const time = normalizeTime(text.match(/\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b/i)?.[1]);
  if (/\b(every day|daily)\b/i.test(text)) return { repeat_cycle: "daily", repeat_days: null, repeat_months: null, repeat_time: time };
  if (/\bweekdays?\b/i.test(text)) return { repeat_cycle: "weekly", repeat_days: [1, 2, 3, 4, 5], repeat_months: null, repeat_time: time };
  if (dayNumbers.length && (repeatSignal(text) || dayNumbers.length > 1))
    return { repeat_cycle: "weekly", repeat_days: dayNumbers, repeat_months: null, repeat_time: time };
  const monthly = text.match(/\bevery\s+month\s+(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\b/i);
  if (monthly && Number(monthly[1]) <= 31)
    return { repeat_cycle: "monthly", repeat_days: [Number(monthly[1])], repeat_months: null, repeat_time: time };
  if (/\b(every year|yearly|annually)\b/i.test(text)) {
    const keys = Object.keys(months).sort((a, b) => b.length - a.length).join("|");
    const match = text.match(new RegExp(`\\b(${keys})\\s+(\\d{1,2})(?:st|nd|rd|th)?\\b`, "i"));
    return {
      repeat_cycle: "yearly",
      repeat_days: match ? [Number(match[2])] : null,
      repeat_months: match ? [months[match[1].toLowerCase()]] : null,
      repeat_time: time,
    };
  }
  return none();
}

export async function analyzeRecurrence(text: string, ai?: NativeAi): Promise<RecurrenceResult> {
  const parsed = await aiJson<Record<string, unknown>>(ai, `Detect recurrence. Return JSON only. Note: ${text}`);
  if (parsed && !oneTimeDeadline(text)) {
    const cycle = parsed.repeat_cycle;
    if (parsed.is_repeating && ["daily", "weekly", "monthly", "yearly"].includes(String(cycle))) {
      return {
        repeat_cycle: cycle as RepeatCycle,
        repeat_days: normalizeList(parsed.repeat_days, 1, 31),
        repeat_months: normalizeList(parsed.repeat_months, 1, 12),
        repeat_time: normalizeTime(parsed.repeat_time),
      };
    }
  }
  return heuristicRecurrence(text);
}

function normalizeList(value: unknown, min: number, max: number): number[] | null {
  if (!Array.isArray(value)) return null;
  const result = [...new Set(value.filter((item): item is number => Number.isInteger(item) && item >= min && item <= max))].sort((a, b) => a - b);
  return result.length ? result : null;
}
