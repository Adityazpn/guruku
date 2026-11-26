"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { docsApi, errorMessage } from "@/services/api";
import type { DocSummary } from "@/types/api";

export default function DocumentsPage() {
  const [items, setItems] = useState<DocSummary[] | null>(null);
  const [total, setTotal] = useState(0); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [err, setErr] = useState<string | null>(null);
  useEffect(() => { docsApi.list(page, q).then((r) => { setItems(r.items); setTotal(r.total); }).catch((e) => setErr(errorMessage(e))); }, [page, q]);
  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-navy">Dokumen Saya</h1>
      <input className="mt-4 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Cari judul…" aria-label="Cari dokumen" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      {err && <p role="alert" className="mt-4 text-sm text-red-600">{err}</p>}
      {items === null && !err && <p className="mt-4 text-sm text-slate-600">Memuat…</p>}
      {items && items.length === 0 && <p className="mt-6 text-sm text-slate-600">Belum ada dokumen. Buat dari <Link href="/app/tools" className="text-navy underline">Generator AI</Link>.</p>}
      <ul className="mt-4 space-y-2">
        {items?.map((d) => (
          <li key={d.id}><Link href={`/app/documents/${d.id}`} className="block rounded-xl border border-slate-200 p-4 hover:border-accent">
            <div className="font-medium text-navy">{d.title}</div>
            <div className="text-xs text-slate-500 mt-1">Versi {d.version} · diubah {new Date(d.updated_at).toLocaleString("id-ID")}</div>
          </Link></li>
        ))}
      </ul>
      {total > 20 && (
        <div className="mt-4 flex gap-2 text-sm">
          <button disabled={page === 1} onClick={() => setPage(page - 1)} className="rounded-lg border px-3 py-1 disabled:opacity-50">Sebelumnya</button>
          <button disabled={page * 20 >= total} onClick={() => setPage(page + 1)} className="rounded-lg border px-3 py-1 disabled:opacity-50">Berikutnya</button>
        </div>
      )}
    </div>
  );
}
