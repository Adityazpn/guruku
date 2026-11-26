"use client";
import { useAuth } from "@/hooks/useAuth";
import { api, errorMessage } from "@/services/api";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { CreditSummary } from "@/types/api";

export default function Overview() {
  const { user } = useAuth();
  const [msg, setMsg] = useState<string | null>(null);
  const [credits, setCredits] = useState<CreditSummary | null>(null);
  useEffect(() => { api.credits().then(setCredits).catch(() => setCredits(null)); }, []);
  if (!user) return null;
  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-navy">Halo, {user.full_name || user.email}</h1>
      {!user.email_verified && (
        <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 text-amber-900 text-sm p-3">
          Email Anda belum terverifikasi.{" "}
          <button className="underline" onClick={() => api.resendVerification().then(() => setMsg("Tautan dikirim ulang.")).catch((e) => setMsg(errorMessage(e)))}>
            Kirim ulang tautan
          </button>
          {msg && <span className="ml-2">{msg}</span>}
        </div>
      )}
      <section className="mt-6 grid gap-3 sm:grid-cols-4" aria-label="Kredit">
        {([["Total kredit", credits?.total], ["Langganan", credits?.subscription], ["Bonus", credits?.bonus], ["Dibeli", credits?.purchased]] as const).map(([l, v]) => (
          <div key={l} className="rounded-xl border border-slate-200 p-4">
            <div className="text-xs text-slate-500">{l}</div>
            <div className="text-2xl font-semibold text-navy">{v ?? "–"}</div>
          </div>
        ))}
      </section>
      <Link href="/app/tools" className="inline-block mt-6 rounded-lg bg-navy text-white px-5 py-2.5 text-sm font-medium">Buka Generator AI</Link>
      <p className="mt-6 text-sm text-slate-600">Menu abu-abu belum tersedia (segera hadir).</p>
    </div>
  );
}
