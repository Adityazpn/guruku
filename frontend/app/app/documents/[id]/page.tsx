"use client";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Notice } from "@/components/ui/AuthCard";
import { JsonEditor } from "@/components/ui/JsonEditor";
import { findProblems } from "@/lib/schema";
import { api, docsApi, errorMessage, messageFor } from "@/services/api";
import type { DocFull, DocVersion } from "@/types/api";

function save(blob: Blob, filename: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = filename; a.click(); URL.revokeObjectURL(a.href);
}
const btn = "rounded-lg border border-navy text-navy px-3 py-1.5 text-sm disabled:opacity-50";

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [doc, setDoc] = useState<DocFull | null>(null);
  const [content, setContent] = useState<Record<string, unknown>>({});
  const [title, setTitle] = useState("");
  const [versions, setVersions] = useState<DocVersion[]>([]);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const regenKey = useRef(crypto.randomUUID());

  const load = useCallback(async () => {
    try {
      const d = await docsApi.get(id);
      setDoc(d); setContent(d.content); setTitle(d.title); setDirty(false);
      setVersions(await docsApi.versions(id));
    } catch (e) { setMsg({ kind: "error", text: errorMessage(e) }); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function run(fn: () => Promise<void>, ok?: string) {
    setBusy(true); setMsg(null);
    try { await fn(); if (ok) setMsg({ kind: "ok", text: ok }); } catch (e) { setMsg({ kind: "error", text: errorMessage(e) }); } finally { setBusy(false); }
  }

  if (!doc) return msg ? <Notice kind={msg.kind}>{msg.text}</Notice> : <p className="text-sm text-slate-600">Memuat…</p>;
  const problems = findProblems(content, doc.output_schema);

  const onSave = () => run(async () => {
    const d = await docsApi.save(id, { content, title, base_version: doc.version });
    setDoc(d); setContent(d.content); setDirty(false); setVersions(await docsApi.versions(id));
  }, "Tersimpan sebagai versi baru");

  const onRegenerate = () => {
    if (!confirm("Buat ulang dengan AI? Ini memakai kredit seperti generate biasa dan menambah versi baru (versi Anda sebelumnya tetap tersimpan).")) return;
    void run(async () => {
      const r = await docsApi.regenerate(id, regenKey.current);
      regenKey.current = crypto.randomUUID();
      for (let i = 0; i < 80; i++) {
        const s = await api.request(r.id);
        if (s.status === "succeeded") { await load(); return; }
        if (s.status === "failed") throw new Error(messageFor(s.error_code));
        await new Promise((res) => setTimeout(res, 1500));
      }
      throw new Error("Terlalu lama. Cek kembali nanti.");
    }, "Versi baru dari AI ditambahkan");
  };

  return (
    <div className="max-w-4xl">
      <p className="text-xs text-slate-500">{doc.tool_name} · versi {doc.version}</p>
      <input className="mt-1 w-full text-2xl font-semibold text-navy border-b border-transparent focus:border-slate-300 focus:outline-none" aria-label="Judul" value={title}
        onChange={(e) => { setTitle(e.target.value); setDirty(true); }} />
      <div className="mt-4 flex flex-wrap gap-2 sticky top-0 bg-white py-2 z-10 border-b border-slate-100">
        <button className="rounded-lg bg-navy text-white px-4 py-1.5 text-sm disabled:opacity-50" disabled={busy || !dirty || problems.length > 0} onClick={onSave}>Simpan</button>
        <button className={btn} disabled={busy || dirty} onClick={() => run(async () => { const f = await docsApi.export(id, "docx"); save(f.blob, f.filename); })}>Unduh DOCX</button>
        <button className={btn} disabled={busy || dirty} onClick={() => run(async () => { const f = await docsApi.export(id, "pdf"); save(f.blob, f.filename); })}>Unduh PDF</button>
        <button className={btn} disabled={busy} onClick={() => run(async () => { const d = await docsApi.duplicate(id); router.push(`/app/documents/${d.id}`); })}>Duplikat</button>
        <button className={btn} disabled={busy || dirty} onClick={onRegenerate}>Buat ulang (AI)</button>
        <button className="rounded-lg border border-red-600 text-red-600 px-3 py-1.5 text-sm disabled:opacity-50" disabled={busy}
          onClick={() => { if (confirm("Hapus dokumen ini?")) void run(async () => { await docsApi.remove(id); router.push("/app/documents"); }); }}>Hapus</button>
      </div>
      {dirty && <p className="text-xs text-amber-700 mt-2">Ada perubahan yang belum disimpan. Simpan dahulu sebelum mengunduh atau membuat ulang.</p>}
      {msg && <div className="mt-3"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
      {problems.length > 0 && <ul className="mt-3 text-xs text-red-700 list-disc pl-5">{problems.slice(0, 5).map((p) => <li key={p}>{p}</li>)}</ul>}
      <div className="mt-4"><JsonEditor value={content} schema={doc.output_schema} onChange={(v) => { setContent(v as Record<string, unknown>); setDirty(true); }} /></div>
      <p className="mt-6 text-xs text-slate-500">Draf buatan AI: tinjau dan sesuaikan sebelum digunakan. Bukan dokumen resmi.</p>
      <section className="mt-8">
        <h2 className="font-semibold text-navy">Riwayat versi</h2>
        <ul className="mt-2 divide-y divide-slate-100 text-sm">
          {versions.map((v) => (
            <li key={v.version} className="py-2 flex flex-wrap items-center gap-2">
              <span>v{v.version}</span><span className="text-xs text-slate-500">{{ ai: "AI", edit: "sunting", restore: "pemulihan", regenerate: "AI (ulang)", duplicate: "salinan" }[v.source] ?? v.source} · {new Date(v.created_at).toLocaleString("id-ID")} {v.note && `· ${v.note}`}</span>
              {v.version !== doc.version && (
                <>
                  <button className="text-navy underline text-xs" disabled={busy || dirty} onClick={() => run(async () => { await docsApi.restore(id, v.version); await load(); }, `Versi ${v.version} dipulihkan sebagai versi baru`)}>Pulihkan</button>
                  <button className="text-navy underline text-xs" onClick={() => run(async () => { const f = await docsApi.export(id, "docx", v.version); save(f.blob, f.filename); })}>Unduh DOCX</button>
                </>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
