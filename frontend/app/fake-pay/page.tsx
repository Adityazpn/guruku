"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Notice } from "@/components/ui/AuthCard";
import { billing, errorMessage } from "@/services/api";

/** Development-only stand-in for the payment provider's page. The backend refuses this outside development. */
function Fake() {
  const order = useSearchParams().get("order") ?? ""; const router = useRouter(); const [err, setErr] = useState<string | null>(null);
  const go = async (outcome: string) => { try { await billing.devFakePay(order, outcome); router.push(`/app/payments/status?order=${order}`); } catch (e) { setErr(errorMessage(e)); } };
  return (
    <main className="max-w-md mx-auto p-6"><h1 className="text-xl font-semibold text-navy">Simulasi pembayaran (hanya pengembangan)</h1>
      <p className="text-sm text-slate-600 mt-2">Pesanan {order}</p>{err && <div className="mt-3"><Notice kind="error">{err}</Notice></div>}
      <div className="mt-4 flex gap-2"><button className="rounded-lg bg-navy text-white px-4 py-2 text-sm" onClick={() => go("paid")}>Bayar berhasil</button>
        <button className="rounded-lg border px-4 py-2 text-sm" onClick={() => go("failed")}>Gagal</button></div></main>
  );
}
export default function Page() { return <Suspense><Fake /></Suspense>; }
