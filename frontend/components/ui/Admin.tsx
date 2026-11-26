"use client";
import { useState } from "react";
import { errorMessage } from "@/services/api";

export const inputCls = "rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent";
export const btn = "rounded-lg bg-navy text-white px-3 py-1.5 text-sm hover:bg-navy-700 disabled:opacity-60";
export const btn2 = "rounded-lg border border-navy text-navy px-3 py-1.5 text-sm disabled:opacity-60";

/** Runs an async admin action, showing a pending state and the error/success message next to the control. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  async function run<T>(fn: () => Promise<T>, okText = "Tersimpan", after?: (r: T) => void) {
    setBusy(true); setMsg(null);
    try { const r = await fn(); setMsg({ kind: "ok", text: okText }); after?.(r); }
    catch (e) { setMsg({ kind: "err", text: errorMessage(e) }); }
    finally { setBusy(false); }
  }
  return { busy, msg, run };
}

export function Msg({ m }: { m: { kind: "ok" | "err"; text: string } | null }) {
  if (!m) return null;
  return <span role={m.kind === "err" ? "alert" : "status"} className={`text-xs ml-2 ${m.kind === "err" ? "text-red-600" : "text-green-700"}`}>{m.text}</span>;
}

export function Card({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 p-4 mb-4">
      <div className="flex items-center justify-between gap-2 mb-3"><h2 className="font-semibold text-navy">{title}</h2>{right}</div>
      {children}
    </section>
  );
}

export function Badge({ children, tone }: { children: React.ReactNode; tone: "ok" | "warn" | "bad" | "idle" }) {
  const c = { ok: "bg-green-100 text-green-800", warn: "bg-amber-100 text-amber-900", bad: "bg-red-100 text-red-800", idle: "bg-slate-100 text-slate-700" }[tone];
  return <span className={`text-xs rounded-full px-2 py-0.5 ${c}`}>{children}</span>;
}

export const PROBLEMS: Record<string, string> = {
  no_published_prompt: "Belum ada prompt yang dipublikasikan", no_pricing_rule: "Belum ada aturan harga kredit",
  no_enabled_model: "Belum ada model aktif (provider aktif + model ditugaskan)", no_fx_rate: "Kurs USD→IDR belum diisi",
  no_model_price: "Harga model belum diisi",
};
