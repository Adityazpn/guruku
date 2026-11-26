"use client";
import { useCallback, useEffect, useState } from "react";
import { Badge, btn, btn2, Card, inputCls, Msg, useAction } from "@/components/ui/Admin";
import { adminApi, errorMessage } from "@/services/api";
import type { AdminModel, AdminProvider, AdminProviders } from "@/types/api";

function ModelRow({ m, p, onChange }: { m: AdminModel; p: AdminProvider; onChange: () => void }) {
  const [inp, setInp] = useState(""); const [out, setOut] = useState("");
  const price = useAction(); const test = useAction();
  const [testRes, setTestRes] = useState<string | null>(null);
  return (
    <div className="border-t border-slate-100 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono">{m.model_code}</span>
        <Badge tone={m.status === "active" ? "ok" : "idle"}>{m.status}</Badge>
        {m.pricing ? <span className="text-xs text-slate-600">USD/1M token: masuk {m.pricing.input_per_1m} · keluar {m.pricing.output_per_1m} (v{m.pricing.version})</span>
          : <Badge tone="warn">harga belum diisi</Badge>}
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <input className={`${inputCls} w-28`} inputMode="decimal" placeholder="masuk /1M" aria-label={`Harga input ${m.model_code}`} value={inp} onChange={(e) => setInp(e.target.value)} />
        <input className={`${inputCls} w-28`} inputMode="decimal" placeholder="keluar /1M" aria-label={`Harga output ${m.model_code}`} value={out} onChange={(e) => setOut(e.target.value)} />
        <button className={btn2} disabled={price.busy || !inp || !out} onClick={() => price.run(() => adminApi.setPrice(m.id, Number(inp), Number(out)), "Harga baru tersimpan", () => { setInp(""); setOut(""); onChange(); })}>Simpan harga</button>
        <button className={btn2} disabled={test.busy} onClick={() => test.run(() => adminApi.testProvider(p.id, m.id), "Selesai", (r) => setTestRes(r.ok ? "Koneksi OK" : `Gagal: ${r.error}`))}>Tes koneksi</button>
        <button className={btn2} onClick={() => adminApi.patchModel(m.id, { status: m.status === "active" ? "disabled" : "active" }).then(onChange)}>{m.status === "active" ? "Nonaktifkan" : "Aktifkan"}</button>
        <Msg m={price.msg} />{testRes && <span className="text-xs">{testRes}</span>}
      </div>
    </div>
  );
}

function ProviderCard({ p, onChange }: { p: AdminProvider; onChange: () => void }) {
  const [key, setKey] = useState(""); const [label, setLabel] = useState("");
  const [model, setModel] = useState(""); const [daily, setDaily] = useState(""); const [monthly, setMonthly] = useState("");
  const k = useAction(); const m = useAction(); const s = useAction(); const l = useAction();
  return (
    <Card title={`${p.name} (${p.code})`} right={<Badge tone={p.status === "enabled" ? "ok" : "idle"}>{p.status === "enabled" ? "aktif" : "nonaktif"}</Badge>}>
      <div className="text-sm space-y-1">
        <div>API key: {p.credential ? <>tersimpan •••• {p.credential.last4} <Badge tone={p.credential.status === "active" ? "ok" : "bad"}>{p.credential.status}</Badge></>
          : p.env_key_present ? "dari environment server" : <Badge tone="warn">belum ada</Badge>}</div>
        <div className="text-xs text-slate-600">Pengeluaran estimasi: hari ini ${p.spend_today_usd.toFixed(4)} · bulan ini ${p.spend_month_usd.toFixed(4)}
          {p.daily_spend_limit_usd ? ` · batas harian $${p.daily_spend_limit_usd}` : ""}{p.monthly_spend_limit_usd ? ` · batas bulanan $${p.monthly_spend_limit_usd}` : ""}</div>
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <input className={`${inputCls} w-64`} type="password" autoComplete="off" placeholder="Tempel API key baru" aria-label="API key" value={key} onChange={(e) => setKey(e.target.value)} />
        <input className={`${inputCls} w-28`} placeholder="label" aria-label="Label key" value={label} onChange={(e) => setLabel(e.target.value)} />
        <button className={btn} disabled={k.busy || key.length < 8} onClick={() => k.run(() => adminApi.setKey(p.id, key, label), "Key tersimpan (terenkripsi)", () => { setKey(""); onChange(); })}>Simpan key</button>
        <Msg m={k.msg} />
      </div>
      <p className="text-xs text-slate-500 mt-1">Key bersifat tulis-saja: setelah disimpan tidak dapat dilihat lagi, hanya 4 karakter terakhir.</p>
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <button className={btn2} disabled={s.busy} onClick={() => s.run(() => adminApi.patchProvider(p.id, { status: p.status === "enabled" ? "disabled" : "enabled" }), "Status diubah", onChange)}>{p.status === "enabled" ? "Nonaktifkan provider" : "Aktifkan provider"}</button>
        <input className={`${inputCls} w-32`} inputMode="decimal" placeholder="batas/hari USD" aria-label="Batas harian" value={daily} onChange={(e) => setDaily(e.target.value)} />
        <input className={`${inputCls} w-36`} inputMode="decimal" placeholder="batas/bulan USD" aria-label="Batas bulanan" value={monthly} onChange={(e) => setMonthly(e.target.value)} />
        <button className={btn2} disabled={l.busy || (!daily && !monthly)} onClick={() => l.run(() => adminApi.patchProvider(p.id, { ...(daily && { daily_spend_limit_usd: Number(daily) }), ...(monthly && { monthly_spend_limit_usd: Number(monthly) }) }), "Batas tersimpan", onChange)}>Simpan batas</button>
        <Msg m={s.msg} /><Msg m={l.msg} />
      </div>
      <div className="mt-4"><h3 className="text-sm font-medium text-slate-700">Model</h3>
        {p.models.map((mm) => <ModelRow key={mm.id} m={mm} p={p} onChange={onChange} />)}
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
          <input className={`${inputCls} w-56`} placeholder="ID model persis dari penyedia" aria-label="ID model" value={model} onChange={(e) => setModel(e.target.value)} />
          <button className={btn2} disabled={m.busy || !model} onClick={() => m.run(() => adminApi.addModel(p.id, model), "Model ditambahkan", () => { setModel(""); onChange(); })}>Tambah model</button><Msg m={m.msg} />
        </div>
      </div>
    </Card>
  );
}

export default function ProvidersPage() {
  const [d, setD] = useState<AdminProviders | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [code, setCode] = useState(""); const [fx, setFx] = useState("");
  const add = useAction(); const fxa = useAction();
  const load = useCallback(() => adminApi.providers().then(setD).catch((e) => setErr(errorMessage(e))), []);
  useEffect(() => { void load(); }, [load]);
  const free = d?.supported_codes.filter((c) => !d.providers.some((p) => p.code === c)) ?? [];
  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-4">Provider AI</h1>
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      <Card title="Kurs USD → IDR">
        <p className="text-sm">Saat ini: {d?.fx ? <b>Rp{d.fx.rate.toLocaleString("id-ID")}</b> : <Badge tone="warn">belum diisi</Badge>}</p>
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <input className={`${inputCls} w-32`} inputMode="decimal" placeholder="mis. 16500" aria-label="Kurs" value={fx} onChange={(e) => setFx(e.target.value)} />
          <button className={btn2} disabled={fxa.busy || !fx} onClick={() => fxa.run(() => adminApi.setFx(Number(fx)), "Kurs tersimpan", () => { setFx(""); void load(); })}>Simpan kurs</button><Msg m={fxa.msg} />
        </div>
      </Card>
      {d?.providers.map((p) => <ProviderCard key={p.id} p={p} onChange={load} />)}
      <Card title="Tambah provider">
        {free.length === 0 ? <p className="text-sm text-slate-600">Semua provider yang didukung sudah ditambahkan.</p> : (
          <div className="flex flex-wrap items-center gap-2">
            <select className={inputCls} aria-label="Provider" value={code} onChange={(e) => setCode(e.target.value)}><option value="">Pilih…</option>{free.map((c) => <option key={c}>{c}</option>)}</select>
            <button className={btn} disabled={add.busy || !code} onClick={() => add.run(() => adminApi.createProvider(code, code === "openai" ? "OpenAI" : code), "Provider ditambahkan", () => { setCode(""); void load(); })}>Tambah</button><Msg m={add.msg} />
          </div>
        )}
      </Card>
    </div>
  );
}
