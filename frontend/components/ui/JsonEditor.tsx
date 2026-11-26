"use client";
import { emptyOf, humanize } from "@/lib/schema";
import type { Schema } from "@/types/api";

const base = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent";

/** Generic editor driven by the tool's output schema: works for every tool, including ones added later. */
export function JsonEditor({ value, schema, onChange, label }: { value: unknown; schema: Schema; onChange: (v: unknown) => void; label?: string }) {
  if (schema.enum)
    return (
      <label className="block"><span className="text-xs font-medium text-slate-600">{label}</span>
        <select className={base} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>{schema.enum.map((o) => <option key={o}>{o}</option>)}</select></label>
    );
  if (schema.type === "object") {
    const obj = (value ?? {}) as Record<string, unknown>;
    return (
      <div className={label ? "rounded-lg border border-slate-200 p-3 space-y-3" : "space-y-4"}>
        {label && <div className="text-sm font-semibold text-navy">{label}</div>}
        {Object.entries(schema.properties ?? {}).map(([k, sub]) => (
          <JsonEditor key={k} label={humanize(k)} schema={sub} value={obj[k]} onChange={(v) => onChange({ ...obj, [k]: v })} />
        ))}
      </div>
    );
  }
  if (schema.type === "array") {
    const arr = (value ?? []) as unknown[];
    const item = schema.items ?? {};
    const simple = item.type !== "object" && item.type !== "array";
    return (
      <div>
        <div className="text-sm font-semibold text-navy mb-1">{label}</div>
        <div className="space-y-2">
          {arr.map((x, i) => (
            <div key={i} className={simple ? "flex gap-2 items-start" : "rounded-lg border border-slate-200 p-3"}>
              <div className="flex-1"><JsonEditor schema={item} value={x} label={simple ? undefined : `#${i + 1}`} onChange={(v) => onChange(arr.map((y, j) => (j === i ? v : y)))} /></div>
              <button type="button" aria-label={`Hapus butir ${i + 1}`} className="text-xs text-red-600 px-2 py-1" onClick={() => onChange(arr.filter((_, j) => j !== i))}>Hapus</button>
            </div>
          ))}
        </div>
        <button type="button" className="mt-2 text-sm text-navy underline" onClick={() => onChange([...arr, emptyOf(item)])}>+ Tambah butir</button>
      </div>
    );
  }
  const text = String(value ?? "");
  return (
    <label className="block">
      {label && <span className="text-xs font-medium text-slate-600">{label}</span>}
      {schema.type === "integer"
        ? <input type="number" className={base} value={text} min={schema.minimum} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />
        : text.length > 70 || text.includes("\n")
          ? <textarea className={base} rows={Math.min(10, Math.ceil(text.length / 70) + 1)} value={text} onChange={(e) => onChange(e.target.value)} />
          : <input className={base} value={text} onChange={(e) => onChange(e.target.value)} />}
    </label>
  );
}
