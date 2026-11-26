import type { Schema } from "@/types/api";

/** A blank value matching the schema (used when the teacher adds a list item). */
export function emptyOf(s: Schema): unknown {
  if (s.enum) return s.enum[0];
  if (s.type === "object") return Object.fromEntries(Object.entries(s.properties ?? {}).map(([k, v]) => [k, emptyOf(v)]));
  if (s.type === "array") return [];
  return s.type === "integer" ? (s.minimum ?? 0) : "";
}

export const humanize = (k: string) => k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** Client-side mirror of the server rules the teacher can break by editing: no empty required text, no empty required list. */
export function findProblems(v: unknown, s: Schema, path = ""): string[] {
  const out: string[] = [];
  if (s.type === "object") {
    for (const [k, sub] of Object.entries(s.properties ?? {}))
      out.push(...findProblems((v as Record<string, unknown>)?.[k], sub, path ? `${path} › ${humanize(k)}` : humanize(k)));
  } else if (s.type === "array") {
    const arr = (v as unknown[]) ?? [];
    if ((s.minItems ?? 0) > arr.length) out.push(`${path}: minimal ${s.minItems} butir`);
    arr.forEach((x, i) => out.push(...findProblems(x, s.items ?? {}, `${path} #${i + 1}`)));
  } else if (s.type === "string" && !s.enum && String(v ?? "").trim() === "" && (s as { minLength?: number }).minLength) {
    out.push(`${path}: tidak boleh kosong`);
  }
  return out;
}
