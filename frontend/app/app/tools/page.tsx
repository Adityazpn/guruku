"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/services/api";
import type { ToolSummary } from "@/types/api";

export default function ToolsPage() {
  const [tools, setTools] = useState<ToolSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  useEffect(() => { api.tools().then(setTools).catch((e) => setErr(errorMessage(e))); }, []);
  const CATS: Record<string, string> = { planning: "Perencanaan", assessment: "Asesmen", administration: "Administrasi", analysis: "Analisis Siswa", media: "Media Belajar" };
  const shown = (tools ?? []).filter((t) => (!cat || t.category === cat) && (t.name + t.description).toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-navy">Generator AI</h1>
      <input className="mt-4 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Cari alat…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari alat" />
      <div className="mt-3 flex flex-wrap gap-2 text-sm" role="group" aria-label="Kategori">
        {[["", "Semua"], ...Object.entries(CATS)].map(([k, v]) => <button key={k} aria-pressed={cat === k} onClick={() => setCat(k)} className={`rounded-full border px-3 py-1 ${cat === k ? "bg-navy text-white border-navy" : "border-slate-300"}`}>{v}</button>)}
      </div>
      {err && <p role="alert" className="mt-4 text-sm text-red-600">{err}</p>}
      {tools === null && !err && <p className="mt-4 text-sm text-slate-600">Memuat…</p>}
      {tools && shown.length === 0 && <p className="mt-4 text-sm text-slate-600">Tidak ada alat yang cocok.</p>}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {shown.map((t) => (
          <Link key={t.slug} href={`/app/tools/${t.slug}`} className="block rounded-xl border border-slate-200 p-4 hover:border-accent">
            <div className="font-medium text-navy">{t.name}</div>
            <div className="text-sm text-slate-600 mt-1">{t.description}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
