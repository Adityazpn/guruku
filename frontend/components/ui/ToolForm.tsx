"use client";
import { LABELS, LONG_TEXT } from "@/lib/form";
import type { JsonSchema } from "@/types/api";

const cls = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent";

export function ToolForm({ schema, values, errors, onChange }: {
  schema: JsonSchema; values: Record<string, string>; errors: Record<string, string>;
  onChange: (k: string, v: string) => void;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {Object.entries(schema.properties).map(([k, def]) => {
        const label = (LABELS[k] ?? k) + (schema.required?.includes(k) && !LABELS[k]?.includes("opsional") ? " *" : "");
        const long = LONG_TEXT.has(k);
        return (
          <label key={k} className={long ? "sm:col-span-2 block" : "block"}>
            <span className="text-sm font-medium text-slate-700">{label}</span>
            {def.enum ? (
              <select className={cls} value={values[k] ?? ""} onChange={(e) => onChange(k, e.target.value)} aria-invalid={!!errors[k]}>
                <option value="">Pilih…</option>
                {def.enum.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : long ? (
              <textarea rows={3} className={cls} value={values[k] ?? ""} maxLength={def.maxLength} onChange={(e) => onChange(k, e.target.value)} aria-invalid={!!errors[k]} />
            ) : (
              <input className={cls} type={def.type === "integer" ? "number" : "text"} min={def.minimum} max={def.maximum}
                value={values[k] ?? ""} maxLength={def.maxLength} onChange={(e) => onChange(k, e.target.value)} aria-invalid={!!errors[k]} />
            )}
            {errors[k] && <span role="alert" className="text-xs text-red-600">{errors[k]}</span>}
          </label>
        );
      })}
    </div>
  );
}
