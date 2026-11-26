"use client";
import { useCallback, useEffect, useState } from "react";
import { btn, btn2, Badge, Card, inputCls, Msg, useAction } from "@/components/ui/Admin";
import { lib } from "@/services/api";
import type { LibItem } from "@/types/api";

function Row({ i, onChange }: { i: LibItem; onChange: () => void }) {
  const up = useAction(); const st = useAction();
  return (
    <div className="border-t border-slate-100 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2"><b>{i.title}</b><Badge tone={i.status === "published" ? "ok" : i.status === "draft" ? "warn" : "idle"}>{i.status}</Badge>
        <Badge tone="idle">{i.access}</Badge>{i.is_sample && <Badge tone="warn">contoh</Badge>}<span className="text-xs text-slate-500">{i.category_name} · {i.has_file ? `v${i.version} ${i.file_type}` : "belum ada berkas"}</span></div>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <label className={`${btn2} cursor-pointer`}>Unggah berkas<input type="file" className="sr-only" aria-label={`Berkas ${i.title}`} accept=".pdf,.docx,.pptx,.xlsx,.txt"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void up.run(() => lib.adminUpload(i.id, f), "Berkas terunggah (versi baru)", onChange); e.target.value = ""; }} /></label>
        {i.status !== "published" && <button className={btn2} disabled={st.busy} onClick={() => st.run(() => lib.adminPatch(i.id, { status: "published" }), "Dipublikasikan", onChange)}>Publikasikan</button>}
        {i.status === "published" && <button className={btn2} disabled={st.busy} onClick={() => st.run(() => lib.adminPatch(i.id, { status: "archived" }), "Diarsipkan", onChange)}>Arsipkan</button>}
        <button className={btn2} disabled={st.busy} onClick={() => st.run(() => lib.adminPatch(i.id, { access: i.access === "free" ? "premium" : "free" }), "Akses diubah", onChange)}>Jadikan {i.access === "free" ? "premium" : "gratis"}</button>
        <Msg m={up.msg} /><Msg m={st.msg} />
      </div>
    </div>
  );
}

export default function LibraryAdmin() {
  const [items, setItems] = useState<LibItem[]>([]); const [cats, setCats] = useState<{ slug: string; name: string }[]>([]);
  const [f, setF] = useState({ category_slug: "", title: "", description: "", level: "", subject: "", tags: "", access: "free" }); const a = useAction();
  const load = useCallback(() => { lib.adminItems().then(setItems).catch(() => undefined); lib.categories().then(setCats).catch(() => undefined); }, []);
  useEffect(() => { load(); }, [load]);
  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-4">Pustaka Digital</h1>
      <Card title="Tambah materi">
        <div className="grid gap-2 sm:grid-cols-2">
          <select className={inputCls} aria-label="Kategori" value={f.category_slug} onChange={(e) => setF({ ...f, category_slug: e.target.value })}><option value="">Kategori…</option>{cats.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select>
          <input className={inputCls} placeholder="Judul" aria-label="Judul" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          <input className={inputCls} placeholder="Jenjang (SD/MI, SMP/MTs…)" aria-label="Jenjang" value={f.level} onChange={(e) => setF({ ...f, level: e.target.value })} />
          <input className={inputCls} placeholder="Mata pelajaran" aria-label="Mata pelajaran" value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} />
          <input className={`${inputCls} sm:col-span-2`} placeholder="Tag (pisahkan koma)" aria-label="Tag" value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} />
          <textarea className={`${inputCls} sm:col-span-2`} rows={2} placeholder="Deskripsi" aria-label="Deskripsi" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          <select className={inputCls} aria-label="Akses" value={f.access} onChange={(e) => setF({ ...f, access: e.target.value })}><option value="free">Gratis</option><option value="premium">Premium</option></select>
        </div>
        <button className={`${btn} mt-3`} disabled={a.busy || !f.category_slug || f.title.length < 2} onClick={() => a.run(() => lib.adminCreate({ ...f, tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean) }), "Materi dibuat (draf). Unggah berkas lalu publikasikan.", () => { setF({ ...f, title: "", description: "" }); load(); })}>Buat draf</button><Msg m={a.msg} />
        <p className="text-xs text-slate-500 mt-2">Hanya unggah materi yang Anda miliki hak ciptanya atau berlisensi. Jenis berkas: pdf, docx, pptx, xlsx, txt (maks. 25 MB).</p>
      </Card>
      <Card title={`Semua materi (${items.length})`}>{items.map((i) => <Row key={i.id} i={i} onChange={load} />)}</Card>
    </div>
  );
}
