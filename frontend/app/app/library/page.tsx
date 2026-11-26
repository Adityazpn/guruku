"use client";
import { useCallback, useEffect, useState } from "react";
import { Notice } from "@/components/ui/AuthCard";
import { errorMessage, lib } from "@/services/api";
import type { LibItem } from "@/types/api";

export default function LibraryPage() {
  const [cats, setCats] = useState<{ slug: string; name: string }[]>([]); const [cat, setCat] = useState(""); const [q, setQ] = useState("");
  const [items, setItems] = useState<LibItem[] | null>(null); const [err, setErr] = useState<string | null>(null);
  useEffect(() => { lib.categories().then(setCats).catch(() => undefined); }, []);
  const load = useCallback(() => { lib.items({ q, category: cat }).then((r) => { setItems(r.items); setErr(null); }).catch((e) => setErr(errorMessage(e))); }, [q, cat]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  async function dl(i: LibItem) {
    try { const r = await lib.download(i.id); window.location.href = r.url; } catch (e) { setErr(errorMessage(e)); }
  }
  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-semibold text-navy">Pustaka Digital</h1>
      <input className="mt-4 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Cari materi…" aria-label="Cari materi" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="mt-3 flex flex-wrap gap-2 text-sm" role="group" aria-label="Kategori">
        {[{ slug: "", name: "Semua" }, ...cats].map((c) => <button key={c.slug} aria-pressed={cat === c.slug} onClick={() => setCat(c.slug)} className={`rounded-full border px-3 py-1 ${cat === c.slug ? "bg-navy text-white border-navy" : "border-slate-300"}`}>{c.name}</button>)}
      </div>
      {err && <div className="mt-3"><Notice kind="error">{err}</Notice></div>}
      {items && items.length === 0 && <p className="mt-6 text-sm text-slate-600">Belum ada materi yang cocok.</p>}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {items?.map((i) => (
          <article key={i.id} className="rounded-xl border border-slate-200 p-4">
            <div className="flex flex-wrap gap-1 text-xs mb-1">
              <span className="rounded-full bg-accent-100 text-navy px-2 py-0.5">{i.category_name}</span>
              {i.is_sample && <span className="rounded-full bg-amber-100 text-amber-900 px-2 py-0.5">Contoh</span>}
              {i.access === "premium" && <span className="rounded-full bg-navy text-white px-2 py-0.5">Premium</span>}
            </div>
            <h2 className="font-medium text-navy">{i.title}</h2>
            <p className="text-sm text-slate-600 mt-1">{i.description}</p>
            <div className="text-xs text-slate-500 mt-1">{[i.level, i.subject, i.file_type?.toUpperCase(), i.size ? `${Math.ceil(i.size / 1024)} KB` : ""].filter(Boolean).join(" · ")}</div>
            <button onClick={() => dl(i)} className="mt-3 rounded-lg bg-navy text-white px-3 py-1.5 text-sm">{i.locked ? "Berlangganan untuk mengunduh" : "Unduh"}</button>
          </article>
        ))}
      </div>
    </div>
  );
}
