"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { billing, errorMessage, rp } from "@/services/api";
import type { Pack, Plan } from "@/types/api";

export default function Pricing() {
  const [plans, setPlans] = useState<Plan[] | null>(null); const [packs, setPacks] = useState<Pack[]>([]); const [err, setErr] = useState<string | null>(null);
  useEffect(() => { billing.plans().then(setPlans).catch((e) => setErr(errorMessage(e))); billing.packages().then(setPacks).catch(() => undefined); }, []);
  return (
    <main className="max-w-6xl mx-auto px-4 py-12">
      <Link href="/" className="font-bold text-navy">Guruku</Link>
      <h1 className="text-3xl font-bold text-navy mt-6">Harga</h1>
      <p className="text-slate-600 mt-2">Satu akun, kredit AI bulanan. Anda juga bisa menambah kredit kapan saja.</p>
      {err && <p role="alert" className="mt-4 text-red-600 text-sm">{err}</p>}
      {plans && plans.length === 0 && <p className="mt-6 text-sm text-slate-600">Paket langganan belum tersedia.</p>}
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {plans?.map((p) => (
          <section key={p.code} className="rounded-xl border border-slate-200 p-5">
            <h2 className="font-semibold text-navy text-lg">{p.name}</h2>
            <div className="mt-2 text-2xl font-bold">{p.prices.monthly ? rp(p.prices.monthly) : "–"}<span className="text-sm font-normal text-slate-500"> /bulan</span></div>
            {p.prices.annual && <div className="text-sm text-slate-600">atau {rp(p.prices.annual)} /tahun</div>}
            <div className="mt-3 text-sm"><b>{Number(p.credits_monthly)}</b> kredit AI / bulan</div>
            <ul className="mt-3 text-sm text-slate-700 list-disc pl-5 space-y-1">{p.features.map((f) => <li key={f}>{f}</li>)}</ul>
            <Link href="/register" className="mt-5 block text-center rounded-lg bg-navy text-white py-2 text-sm font-medium">Mulai</Link>
          </section>
        ))}
      </div>
      {packs.length > 0 && (
        <section className="mt-12"><h2 className="text-xl font-semibold text-navy">Tambah kredit</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {packs.map((k) => <div key={k.id} className="rounded-xl border border-slate-200 p-4"><div className="font-medium">{k.name}</div>
              <div className="text-lg font-bold">{rp(k.price_idr)}</div>{Number(k.bonus_credits) > 0 && <div className="text-xs text-green-700">+ bonus {Number(k.bonus_credits)} kredit</div>}</div>)}
          </div></section>
      )}
      <p className="mt-10 text-xs text-slate-500">Kredit AI adalah kredit internal platform, bukan kredit penyedia AI. Hasil AI berupa draf yang perlu ditinjau guru.</p>
    </main>
  );
}
