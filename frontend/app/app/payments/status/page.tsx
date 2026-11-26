"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Notice } from "@/components/ui/AuthCard";
import { billing, errorMessage } from "@/services/api";
import type { Order } from "@/types/api";

function Status() {
  const no = useSearchParams().get("order") ?? "";
  const [o, setO] = useState<Order | null>(null); const [err, setErr] = useState<string | null>(null); const [tries, setTries] = useState(0);
  useEffect(() => {
    if (!no) return;
    let stop = false;
    const tick = async (n: number) => {
      try { const r = await billing.order(no); if (stop) return; setO(r); setTries(n); if (r.status === "pending" && n < 60) setTimeout(() => void tick(n + 1), 3000); }
      catch (e) { if (!stop) setErr(errorMessage(e)); }
    };
    void tick(0);
    return () => { stop = true; };
  }, [no]);
  if (err) return <Notice kind="error">{err}</Notice>;
  if (!o) return <p className="text-sm text-slate-600">Memuat…</p>;
  // The page only REPORTS what our server knows. Access/credits are granted by the verified gateway notification, never by this page.
  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-semibold text-navy">Status pembayaran</h1>
      <p className="text-sm text-slate-600 mt-1">{o.description} · {o.order_no}</p>
      <div className="mt-4">
        {o.paid && <Notice kind="ok">Pembayaran terverifikasi. Terima kasih! Kredit/langganan Anda sudah aktif.</Notice>}
        {!o.paid && o.status === "pending" && <Notice kind="ok">Menunggu konfirmasi dari penyedia pembayaran{tries >= 60 ? " (memakan waktu lebih lama dari biasa; cek lagi nanti di Riwayat Pembayaran)" : "…"}. Jangan bayar dua kali.</Notice>}
        {(o.status === "failed" || o.status === "expired") && <Notice kind="error">Pembayaran {o.status === "failed" ? "gagal" : "kedaluwarsa"}. Anda tidak ditagih; silakan coba lagi.</Notice>}
      </div>
      <div className="mt-4 flex gap-3 text-sm"><Link href="/app/credits" className="text-navy underline">Kredit AI</Link><Link href="/app/subscription" className="text-navy underline">Langganan</Link><Link href="/app/payments" className="text-navy underline">Riwayat</Link></div>
    </div>
  );
}

export default function Page() { return <Suspense><Status /></Suspense>; }
