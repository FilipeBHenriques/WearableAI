import { aiJson, cosineSimilarity, embeddings, lexicalSimilarity } from "./ai";
import { isAvailableOn, isRepeating } from "./recurrence";
import type { LocalRepository } from "./repository";
import {
  ACTIVE_STATUS,
  type Coordinates,
  type Location,
  type NativeAi,
  type Note,
} from "./types";

const contextPhrases = [
  "when i get to",
  "when i am at",
  "once i get to",
  "once i am at",
  "at",
  "near",
  "in",
];

export async function findRelevantLocation(
  text: string,
  locations: Location[],
  ai?: NativeAi,
): Promise<Location | null> {
  if (!locations.length) return null;
  const lowered = text.toLowerCase();
  const exact = locations
    .filter((location) => {
      const escaped = location.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return new RegExp(`\\b${escaped}\\b`, "i").test(lowered);
    })
    .sort((a, b) => b.name.length - a.name.length)[0];
  if (exact) return exact;

  const phrases = locations.flatMap((location) =>
    contextPhrases.map((phrase) => `${phrase} ${location.name}`),
  );
  const vectors = await embeddings(ai, [text, ...phrases]);
  const ranked = locations
    .map((location, locationIndex) => {
      const scores = contextPhrases.map((_, phraseIndex) => {
        const index = locationIndex * contextPhrases.length + phraseIndex;
        return vectors
          ? cosineSimilarity(vectors[0], vectors[index + 1])
          : lexicalSimilarity(text, phrases[index]);
      });
      return { location, score: Math.max(...scores) };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);
  if (!ai || !ranked.length) return ranked[0]?.score >= 0.75 ? ranked[0].location : null;
  const parsed = await aiJson<Record<string, unknown>>(
    ai,
    `Choose a saved location only if clearly relevant. JSON {location_id}. Note: ${text}. Candidates: ${ranked.map(({ location }) => `${location.id}:${location.name}`).join(", ")}`,
  );
  const id = Number(parsed?.location_id);
  return ranked.find(({ location }) => location.id === id)?.location ?? null;
}

export async function applyLocation(
  note: Note,
  repository: LocalRepository,
  ai?: NativeAi,
): Promise<Location | null> {
  const location = await findRelevantLocation(note.text, await repository.listLocations(), ai);
  if (location) await repository.updateNote(note.id, { location_id: location.id });
  return location;
}

export function haversineMeters(a: Coordinates, b: Coordinates): number {
  const radius = 6_371_000;
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const p1 = toRadians(a.latitude);
  const p2 = toRadians(b.latitude);
  const dp = toRadians(b.latitude - a.latitude);
  const dl = toRadians(b.longitude - a.longitude);
  const value =
    Math.sin(dp / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(value));
}

export async function proximitySuggestions(
  coordinates: Coordinates,
  repository: LocalRepository,
  radiusMeters = 200,
  day = new Date(),
): Promise<{ location: Location; distance_meters: number; notes: Note[] }[]> {
  const notes = await repository.listNotes();
  const result = [];
  for (const location of await repository.listLocations()) {
    const distance = haversineMeters(coordinates, location);
    if (distance > radiusMeters) continue;
    const suggestions = notes.filter(
      (note) =>
        note.location_id === location.id &&
        (isRepeating(note) ? isAvailableOn(note, day) : note.status === ACTIVE_STATUS),
    );
    if (suggestions.length) {
      result.push({ location, distance_meters: distance, notes: suggestions });
    }
  }
  return result.sort((a, b) => a.distance_meters - b.distance_meters);
}
