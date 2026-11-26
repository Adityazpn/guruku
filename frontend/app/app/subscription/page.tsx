"use client";
import { useEffect, useState } from "react";
import { Notice } from "@/components/ui/AuthCard";
import { billing, errorMessage, rp } from "@/services/api";
import type { Plan, Sub } from "@/types/api";

const STATUS: Record<string, string> = { active: "Aktif", past_due: "Menunggu pembayaran (masa tenggang)" };

export default function SubscriptionPage() {
  const [sub, setSub] = useState<Sub | null>(null); const [plans, setPlans] = useState<Plan[]>([]); const [cycle, setCycle] = useState<"monthly" | "annual">("monthly");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);
  const load = () => { billing.subscription().then(setSub).catch((e) => setErr(errorMessage(e))); billing.plans().then(setPlans).catch(() => undefined); };
  useEffect(load, []);

  async function buy(code: string) {
    setBusy(true); setErr(null);
    try { const o = await billing.buyPlan(code, cycle, crypto.randomUUID()); if (o.checkout_url) window.location.href = o.checkout_url; else setErr("Tautan pembayaran tidak tersedia."); }
    catch (e) { setErr(errorMessage(e)); setBusy(false); }
  }
  const act = (fn: () => Promise<void>) => { setBusy(true); fn().then(load).catch((e) => setErr(errorMessage(e))).finally(() => setBusy(false)); };

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-navy">Langganan</h1>
      {err && <div className="mt-3"><Notice kind="error">{err}</Notice></div>}
      <section className="mt-4 rounded-xl border border-slate-200 p-4" aria-label="Langganan saat ini">
        {sub === null ? <p className="text-sm text-slate-600">Memuat…</p> : !sub.active ? <p className="text-sm">Anda belum berlangganan. Pilih paket di bawah.</p> : (
          <div className="text-sm space-y-1">
            <div><b>{sub.plan_name}</b> ({sub.cycle === "annual" ? "tahunan" : "bulanan"}) · {STATUS[sub.status ?? ""] ?? sub.status}</div>
            <div>Berlaku sampai {new Date(sub.period_end!).toLocaleDateString("id-ID")} · {Number(sub.credits_monthly)} kredit/bulan</div>
            {sub.status === "past_due" && <div className="text-amber-800">Perpanjang sebelum {new Date(sub.grace_until!).toLocaleDateString("id-ID")} agar akses tidak berhenti.</div>}
            {sub.cancel_at_period_end ? <div className="text-amber-800">Tidak diperpanjang otomatis; berakhir di akhir periode. <button className="underline" disabled={busy} onClick={() => act(billing.resume)}>Batalkan pembatalan</button></div>
              : <button className="underline text-navy" disabled={busy} onClick={() => confirm("Hentikan perpanjangan? Akses tetap sampai akhir periode.") && act(billing.cancel)}>Hentikan perpanjangan</button>}
          </div>
        )}
      </section>
      <div className="mt-6 flex gap-2 text-sm" role="group" aria-label="Siklus">
        {(["monthly", "annual"] as const).map((c) => <button key={c} onClick={() => setCycle(c)} aria-pressed={cycle === c} className={`rounded-lg border px-3 py-1.5 ${cycle === c ? "bg-navy text-white border-navy" : "border-slate-300"}`}>{c === "monthly" ? "Bulanan" : "Tahunan"}</button>)}
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {plans.map((p) => (
          <section key={p.code} className="rounded-xl border border-slate-200 p-4">
            <h2 className="font-semibold text-navy">{p.name}</h2>
            <div className="text-xl font-bold mt-1">{p.prices[cycle] ? rp(p.prices[cycle]!) : "–"}</div>
            <div className="text-sm mt-1">{Number(p.credits_monthly)} kredit / bulan</div>
            <ul className="text-xs text-slate-600 list-disc pl-5 mt-2 space-y-0.5">{p.features.map((f) => <li key={f}>{f}</li>)}</ul>
            <button disabled={busy || !p.prices[cycle]} onClick={() => buy(p.code)} className="mt-4 w-full rounded-lg bg-navy text-white py-2 text-sm disabled:opacity-50">
              {sub?.active && sub.plan_code === p.code ? "Perpanjang" : sub?.active ? "Ganti ke paket ini" : "Berlangganan"}
            </button>
          </section>
        ))}
      </div>
      <p className="mt-4 text-xs text-slate-500">Akses dan kredit baru aktif setelah pembayaran terverifikasi oleh penyedia pembayaran, bukan saat Anda kembali dari halaman bayar. Mengganti paket berlaku segera tanpa pengembalian sisa masa berlangganan.</p>
    </div>
  );
}
