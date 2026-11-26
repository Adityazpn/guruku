"use client";
import { useCallback, useEffect, useState } from "react";
import { Badge, btn, btn2, Card, inputCls, Msg, PROBLEMS, useAction } from "@/components/ui/Admin";
import { adminApi, errorMessage } from "@/services/api";
import type { AdminTool, PromptVersion } from "@/types/api";

type ModelOpt = { id: string; label: string };

function Assign({ t, models, onChange }: { t: AdminTool; models: ModelOpt[]; onChange: () => void }) {
  const [main, setMain] = useState(t.models[0]?.id ?? ""); const [fb, setFb] = useState(t.models[1]?.id ?? "");
  const a = useAction();
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select className={inputCls} aria-label="Model utama" value={main} onChange={(e) => setMain(e.target.value)}><option value="">Model utama…</option>{models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}</select>
      <select className={inputCls} aria-label="Model cadangan" value={fb} onChange={(e) => setFb(e.target.value)}><option value="">Cadangan (opsional)…</option>{models.filter((m) => m.id !== main).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}</select>
      <button className={btn2} disabled={a.busy || !main} onClick={() => a.run(() => adminApi.assign(t.id, [main, fb].filter(Boolean)), "Model ditugaskan", onChange)}>Simpan</button><Msg m={a.msg} />
    </div>
  );
}

const FIELDS: [string, string][] = [["fixed_credits", "Kredit tetap"], ["base_credits", "Kredit dasar (hybrid)"], ["margin_pct", "Margin %"], ["processing_fee_idr", "Biaya proses Rp"],
  ["credit_value_idr", "Nilai 1 kredit Rp"], ["rounding_step", "Pembulatan"], ["min_credits", "Min kredit"], ["max_credits", "Maks kredit"], ["reserve_safety_factor", "Faktor cadangan"]];

function Rule({ t, onChange }: { t: AdminTool; onChange: () => void }) {
  const r = t.pricing_rule;
  const [mode, setMode] = useState(String(r?.mode ?? "fixed"));
  const [v, setV] = useState<Record<string, string>>(Object.fromEntries(FIELDS.map(([k]) => [k, String(r?.[k] ?? "")])));
  const a = useAction();
  const save = () => a.run(() => adminApi.setRule(t.id, { mode, ...Object.fromEntries(Object.entries(v).filter(([, x]) => x !== "").map(([k, x]) => [k, Number(x)])) }), "Aturan harga tersimpan (versi baru)", onChange);
  return (
    <div>
      <select className={inputCls} aria-label="Mode harga" value={mode} onChange={(e) => setMode(e.target.value)}>
        <option value="fixed">Tetap</option><option value="dynamic">Dinamis (berdasar biaya API)</option><option value="hybrid">Hybrid (dasar + dinamis)</option>
      </select>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-2">
        {FIELDS.map(([k, label]) => (
          <label key={k} className="text-xs text-slate-600">{label}
            <input className={`${inputCls} w-full mt-0.5`} inputMode="decimal" value={v[k]} onChange={(e) => setV((s) => ({ ...s, [k]: e.target.value }))} />
          </label>
        ))}
      </div>
      <button className={`${btn} mt-2`} disabled={a.busy} onClick={save}>Simpan aturan</button><Msg m={a.msg} />
      <p className="text-xs text-slate-500 mt-1">Pengguna tidak pernah ditagih di atas “Maks kredit”. Mode dinamis/hybrid memerlukan harga model dan kurs.</p>
    </div>
  );
}

function Prompts({ t, onChange }: { t: AdminTool; onChange: () => void }) {
  const [list, setList] = useState<PromptVersion[]>([]);
  const [sys, setSys] = useState(""); const [tpl, setTpl] = useState(""); const [note, setNote] = useState("");
  const a = useAction();
  const load = useCallback(() => adminApi.prompts(t.id).then((l) => {
    setList(l);
    const live = l.find((x) => x.status === "published") ?? l[0];
    if (live) { setSys((s) => s || live.system_prompt); setTpl((s) => s || live.user_template); }
  }), [t.id]);
  useEffect(() => { void load(); }, [load]);
  const reload = () => { void load(); onChange(); };
  return (
    <div>
      <label className="text-xs text-slate-600">Prompt sistem
        <textarea className={`${inputCls} w-full font-mono text-xs`} rows={4} value={sys} onChange={(e) => setSys(e.target.value)} /></label>
      <label className="text-xs text-slate-600 block mt-2">Templat pengguna (Jinja: {"{{ input.topic }}"}, {"{{ input_json }}"})
        <textarea className={`${inputCls} w-full font-mono text-xs`} rows={8} value={tpl} onChange={(e) => setTpl(e.target.value)} /></label>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <input className={`${inputCls} w-56`} placeholder="catatan perubahan" aria-label="Catatan perubahan" value={note} onChange={(e) => setNote(e.target.value)} />
        <button className={btn2} disabled={a.busy} onClick={() => a.run(() => adminApi.createPrompt(t.id, { system_prompt: sys, user_template: tpl, change_note: note }), "Draf versi baru dibuat (belum aktif)", reload)}>Simpan sebagai draf</button><Msg m={a.msg} />
      </div>
      <h4 className="text-sm font-medium mt-4">Riwayat versi</h4>
      {list.map((p) => (
        <div key={p.id} className="flex flex-wrap items-center gap-2 border-t border-slate-100 py-2 text-sm">
          <span>v{p.version}</span><Badge tone={p.status === "published" ? "ok" : p.status === "draft" ? "warn" : "idle"}>{p.status}</Badge>
          <span className="text-xs text-slate-600">{p.change_note}</span>
          {p.status === "draft" && <button className={btn2} onClick={() => adminApi.publishPrompt(p.id).then(reload).catch((e) => alert(errorMessage(e)))}>Publikasikan</button>}
          {p.status === "archived" && <button className={btn2} onClick={() => adminApi.rollback(t.id, p.version).then(reload).catch((e) => alert(errorMessage(e)))}>Kembalikan ke versi ini</button>}
        </div>
      ))}
      <p className="text-xs text-slate-500">Versi yang sudah dipublikasikan tidak bisa diedit; perubahan selalu membuat versi baru.</p>
    </div>
  );
}

export default function ToolsAdmin() {
  const [tools, setTools] = useState<AdminTool[]>([]);
  const [models, setModels] = useState<ModelOpt[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => {
    adminApi.tools().then(setTools).catch((e) => setErr(errorMessage(e)));
    adminApi.providers().then((d) => setModels(d.providers.flatMap((p) => p.models.map((m) => ({ id: m.id, label: `${p.code} / ${m.model_code}${p.status === "enabled" ? "" : " (provider nonaktif)"}` }))))).catch(() => undefined);
  }, []);
  useEffect(() => { load(); }, [load]);
  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-4">Alat & Prompt</h1>
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      {tools.map((t) => (
        <Card key={t.id} title={t.name} right={<div className="flex items-center gap-2">{t.ready ? <Badge tone="ok">siap</Badge> : <Badge tone="warn">belum siap</Badge>}
          <button className={btn2} onClick={() => adminApi.patchTool(t.id, { is_active: !t.is_active }).then(load)}>{t.is_active ? "Nonaktifkan" : "Aktifkan"}</button></div>}>
          {t.problems.length > 0 && <ul className="text-sm text-amber-900 bg-amber-50 rounded-lg p-2 mb-3 list-disc pl-6">{t.problems.map((p) => <li key={p}>{PROBLEMS[p] ?? p}</li>)}</ul>}
          <h3 className="text-sm font-medium mb-1">Model</h3><Assign key={t.models.map((m) => m.id).join()} t={t} models={models} onChange={load} />
          <button className="text-sm text-navy underline mt-3" onClick={() => setOpen(open === t.id ? null : t.id)}>{open === t.id ? "Tutup pengaturan" : "Aturan harga & prompt"}</button>
          {open === t.id && (
            <div className="mt-3 space-y-6">
              <div><h3 className="text-sm font-medium mb-1">Aturan harga kredit</h3><Rule key={String(t.pricing_rule?.version)} t={t} onChange={load} /></div>
              <div><h3 className="text-sm font-medium mb-1">Prompt</h3><Prompts t={t} onChange={load} /></div>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}
