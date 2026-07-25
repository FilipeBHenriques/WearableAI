import type { NativeAi } from "./types";

export function extractJsonObject<T extends object>(raw: string): T {
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start < 0 || end < start) throw new Error("No JSON object found.");
  return JSON.parse(raw.slice(start, end + 1)) as T;
}

export async function aiJson<T extends object>(
  ai: NativeAi | undefined,
  prompt: string,
): Promise<T | null> {
  if (!ai) return null;
  try {
    if ((await ai.isAvailable?.()) === false) return null;
    return await ai.generateJson<T>(prompt);
  } catch {
    return null;
  }
}

export async function embeddings(
  ai: NativeAi | undefined,
  texts: string[],
): Promise<number[][] | null> {
  if (!ai) return null;
  try {
    if ((await ai.isAvailable?.()) === false) return null;
    const vectors = await ai.embed(texts);
    return vectors.length === texts.length ? vectors : null;
  } catch {
    return null;
  }
}

export function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length || !a.length) return 0;
  let dot = 0;
  let aa = 0;
  let bb = 0;
  for (let index = 0; index < a.length; index += 1) {
    dot += a[index] * b[index];
    aa += a[index] ** 2;
    bb += b[index] ** 2;
  }
  return aa && bb ? dot / Math.sqrt(aa * bb) : 0;
}

export function lexicalSimilarity(a: string, b: string): number {
  const words = (value: string) =>
    new Set(value.toLowerCase().match(/[a-z0-9]+/g)?.filter((word) => word.length > 2) ?? []);
  const left = words(a);
  const right = words(b);
  if (!left.size || !right.size) return 0;
  const intersection = [...left].filter((word) => right.has(word)).length;
  return intersection / Math.sqrt(left.size * right.size);
}
