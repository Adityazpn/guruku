"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Notice } from "@/components/ui/AuthCard";
import { api, assistantApi, errorMessage, messageFor } from "@/services/api";

type Conv = { id: string; title: string };
type Msg = { id: string; role: "user" | "assistant"; content: string };

export default function AssistantPage() {
  const [convs, setConvs] = useState<Conv[]>([]); const [cur, setCur] = useState<string | null>(null); const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState(""); const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);
  const keyRef = useRef(crypto.randomUUID()); const bottom = useRef<HTMLDivElement>(null);

  const loadList = useCallback(() => assistantApi.list().then(setConvs).catch((e) => setErr(errorMessage(e))), []);
  const open = useCallback(async (id: string) => { setCur(id); setErr(null); const c = await assistantApi.get(id); setMsgs(c.messages); }, []);
  useEffect(() => { void loadList(); }, [loadList]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  async function newChat() { const c = await assistantApi.create(); await loadList(); await open(c.id); }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const content = text.trim();
    if (!content || busy) return;
    setBusy(true); setErr(null);
    try {
      let id = cur;
      if (!id) { const c = await assistantApi.create(); id = c.id; setCur(id); }
      setMsgs((m) => [...m, { id: "tmp", role: "user", content }]); setText("");
      const r = await assistantApi.send(id, content, keyRef.current);
      keyRef.current = crypto.randomUUID();
      for (let i = 0; i < 80; i++) {
        const s = await api.request(r.request_id);
        if (s.status === "succeeded") break;
        if (s.status === "failed") { setErr(messageFor(s.error_code)); break; }
        await new Promise((res) => setTimeout(res, 1200));
      }
      await open(id); await loadList();
    } catch (x) { setErr(errorMessage(x)); if (cur) await open(cur); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-5xl md:flex gap-4">
      <aside className="md:w-56 shrink-0">
        <h1 className="text-2xl font-semibold text-navy">Asisten AI</h1>
        <button onClick={newChat} className="mt-3 w-full rounded-lg bg-navy text-white py-2 text-sm">Percakapan baru</button>
        <ul className="mt-3 space-y-1 text-sm max-h-60 md:max-h-[60vh] overflow-y-auto">
          {convs.map((c) => (
            <li key={c.id} className={`flex items-center gap-1 rounded-lg px-2 py-1.5 ${cur === c.id ? "bg-accent-100" : "hover:bg-slate-100"}`}>
              <button className="flex-1 text-left truncate" onClick={() => open(c.id)}>{c.title}</button>
              <button aria-label={`Hapus ${c.title}`} className="text-xs text-red-600" onClick={async () => { if (confirm("Hapus percakapan ini secara permanen?")) { await assistantApi.remove(c.id); if (cur === c.id) { setCur(null); setMsgs([]); } void loadList(); } }}>Hapus</button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="flex-1 mt-4 md:mt-0 min-w-0">
        <div className="rounded-xl border border-slate-200 p-3 min-h-[40vh] max-h-[60vh] overflow-y-auto space-y-3" aria-live="polite">
          {msgs.length === 0 && <p className="text-sm text-slate-500">Tanyakan ide mengajar, perencanaan pembelajaran, atau bantuan administrasi. Jangan masukkan data pribadi siswa. 1 kredit per pesan.</p>}
          {msgs.map((m, i) => <div key={m.id + i} className={`text-sm whitespace-pre-wrap rounded-lg px-3 py-2 max-w-[90%] ${m.role === "user" ? "bg-navy text-white ml-auto" : "bg-slate-100"}`}>{m.content}</div>)}
          {busy && <div className="text-xs text-slate-500" role="status">Asisten sedang mengetik…</div>}
          <div ref={bottom} />
        </div>
        {err && <div className="mt-2"><Notice kind="error">{err}</Notice></div>}
        <form onSubmit={send} className="mt-3 flex gap-2">
          <textarea className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm" rows={2} maxLength={4000} placeholder="Tulis pertanyaan Anda…" aria-label="Pesan" value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(e as unknown as React.FormEvent); } }} />
          <button className="rounded-lg bg-navy text-white px-4 text-sm disabled:opacity-50" disabled={busy || !text.trim()}>Kirim</button>
        </form>
        <p className="text-xs text-slate-500 mt-2">Jawaban AI berupa saran dan dapat keliru; tinjau sebelum digunakan.</p>
      </section>
    </div>
  );
}
