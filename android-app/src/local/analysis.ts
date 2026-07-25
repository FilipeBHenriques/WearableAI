import { aiJson, cosineSimilarity, embeddings, lexicalSimilarity } from "./ai";
import type { LocalRepository } from "./repository";
import type { NativeAi, Note } from "./types";

export type CommandType = "save_location" | "take_note";
export interface Command {
  type: CommandType;
  location_name: string | null;
}

export async function detectCommand(text: string, ai?: NativeAi): Promise<Command> {
  const clean = text.trim();
  if (!clean) return { type: "take_note", location_name: null };
  const parsed = await aiJson<Record<string, unknown>>(
    ai,
    `Classify as save_location only when naming the current physical place, otherwise take_note. JSON {command,location_name}. Transcript: ${clean}`,
  );
  const modelName = String(parsed?.location_name ?? "").trim();
  if (parsed?.command === "save_location" && modelName)
    return { type: "save_location", location_name: modelName };

  const patterns = [
    /\b(?:save|remember)\s+(?:this|current)\s+(?:place|location)\s+(?:as|called)\s+(.+?)\s*[.!]?$/i,
    /\b(?:save|mark)\s+(?:this|here)\s+as\s+(.+?)\s*[.!]?$/i,
    /\bthis\s+is\s+my\s+(?:current\s+)?(?:place|location)\s*[:,]?\s*(.+?)\s*[.!]?$/i,
    /\bi(?:'m| am)\s+(?:currently\s+)?at\s+(.+?)\s*[,;]?\s+(?:save|remember)\s+(?:this|here)\b/i,
  ];
  for (const pattern of patterns) {
    const name = clean.match(pattern)?.[1]?.trim();
    if (name) return { type: "save_location", location_name: name };
  }
  return { type: "take_note", location_name: null };
}

export async function fixTranscript(
  transcript: string,
  ai?: NativeAi,
  enabled = true,
): Promise<string> {
  const text = transcript.trim();
  if (!enabled || !text) return text;
  const parsed = await aiJson<Record<string, unknown>>(
    ai,
    `Lightly correct obvious speech-to-text errors without shortening or changing facts. JSON {fixed_text}. Transcript: ${text}`,
  );
  const fixed = String(parsed?.fixed_text ?? "").trim();
  return fixed && fixed.length >= Math.max(12, Math.floor(text.length * 0.6)) ? fixed : text;
}

export async function classifyText(text: string, ai?: NativeAi): Promise<string> {
  const labels = ["reminder", "task", "idea"];
  const vectors = await embeddings(ai, [text, ...labels]);
  if (vectors) {
    const scores = vectors.slice(1).map((vector) => cosineSimilarity(vectors[0], vector));
    return capitalize(labels[scores.indexOf(Math.max(...scores))]);
  }
  if (/\b(remember|remind|don't forget|appointment|at \d|on (?:mon|tue|wed|thu|fri|sat|sun))\b/i.test(text))
    return "Reminder";
  if (/\b(idea|maybe|what if|consider|thought)\b/i.test(text)) return "Idea";
  return "Task";
}

export async function decideParent(
  note: Note,
  repository: LocalRepository,
  ai?: NativeAi,
): Promise<number | null> {
  const notes = (await repository.listNotes("active")).filter((candidate) => candidate.id !== note.id);
  const descendants = await descendantIds(note.id, notes);
  const candidates = notes.filter((candidate) => !descendants.has(candidate.id));
  if (!candidates.length) return null;

  const vectors = await embeddings(ai, [note.text, ...candidates.map((item) => item.text)]);
  const scored = candidates.map((candidate, index) => ({
    candidate,
    score: vectors
      ? cosineSimilarity(vectors[0], vectors[index + 1])
      : lexicalSimilarity(note.text, candidate.text),
  }));
  const nearest = scored.sort((a, b) => b.score - a.score)[0];
  if (nearest.score > 0.85) return nearest.candidate.id;
  if (nearest.score < 0.45) return null;

  const parsed = await aiJson<Record<string, unknown>>(
    ai,
    `Decide SUB_IDEA or NEW_IDEA as JSON {decision}. Parent: ${nearest.candidate.text}. New note: ${note.text}`,
  );
  return parsed?.decision === "SUB_IDEA" ? nearest.candidate.id : null;
}

async function descendantIds(noteId: number, notes: Note[]): Promise<Set<number>> {
  const result = new Set<number>([noteId]);
  const pending = [noteId];
  while (pending.length) {
    const current = pending.pop()!;
    for (const child of notes.filter((note) => note.parent_note_id === current)) {
      if (!result.has(child.id)) {
        result.add(child.id);
        pending.push(child.id);
      }
    }
  }
  return result;
}

const capitalize = (value: string) => value[0].toUpperCase() + value.slice(1);
