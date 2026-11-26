"use client";
import { useEffect, useState } from "react";
import { Notice } from "@/components/ui/AuthCard";
import { api, billing, errorMessage, rp } from "@/services/api";
import type { CreditSummary, LedgerRow, Pack } from "@/types/api";

const TYPE: Record<string, string> = { subscription_allocation: "Kredit langganan", usage_reservation: "Penahanan (generate)", refund: "Pengembalian sisa", reservation_release: "Pengembalian (gagal)",
  bonus: "Bonus", promotional: "Promo", purchase: "Pembelian", admin_adjustment: "Penyesuaian admin", expiration: "Kedaluwarsa" };

export default function CreditsPage() {
  const [s, setS] = useState<CreditSummary | null>(null); const [packs, setPacks] = useState<Pack[]>([]);
  const [rows, setRows] = useState<LedgerRow[]>([]); const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  useEffect(() => { api.credits().then(setS).catch((e) => setErr(errorMessage(e))); billing.packages().then(setPacks).catch(() => undefined); billing.ledger().then((r) => setRows(r.items)).catch(() => undefined); }, []);
  async function buy(id: string) {
    setBusy(true); setErr(null);
    try { const o = await billing.buyPack(id, crypto.randomUUID()); if (o.checkout_url) window.location.href = o.checkout_url; }
    catch (e) { setErr(errorMessage(e)); setBusy(false); }
  }
  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-navy">Kredit AI</h1>
      {err && <div className="mt-3"><Notice kind="error">{err}</Notice></div>}
      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        {([["Total tersedia", s?.total], ["Langganan", s?.subscription], ["Bonus", s?.bonus], ["Dibeli", s?.purchased]] as const).map(([l, v]) => (
          <div key={l} className="rounded-xl border border-slate-200 p-4"><div className="text-xs text-slate-500">{l}</div><div className="text-2xl font-semibold text-navy">{v ?? "–"}</div></div>))}
      </div>
      {s?.next_expiry && <p className="text-xs text-slate-500 mt-2">Kredit terdekat kedaluwarsa: {new Date(s.next_expiry).toLocaleDateString("id-ID")}. Kredit terpakai berurutan: langganan, bonus, lalu dibeli.</p>}
      <h2 className="mt-8 font-semibold text-navy">Tambah kredit</h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {packs.map((k) => (
          <div key={k.id} className="rounded-xl border border-slate-200 p-4"><div className="font-medium">{k.name}</div><div className="text-lg font-bold">{rp(k.price_idr)}</div>
            {Number(k.bonus_credits) > 0 && <div className="text-xs text-green-700">+ bonus {Number(k.bonus_credits)} kredit ({k.bonus_expiry_days} hari)</div>}
            <div className="text-xs text-slate-500">{k.purchased_expiry_days ? `Berlaku ${k.purchased_expiry_days} hari` : "Tidak kedaluwarsa"}</div>
            <button disabled={busy} onClick={() => buy(k.id)} className="mt-3 w-full rounded-lg bg-navy text-white py-1.5 text-sm disabled:opacity-50">Beli</button></div>))}
        {packs.length === 0 && <p className="text-sm text-slate-600">Belum ada paket kredit.</p>}
      </div>
      <h2 className="mt-8 font-semibold text-navy">Riwayat kredit</h2>
      <div className="overflow-x-auto mt-2"><table className="w-full text-sm"><thead><tr className="text-left text-xs text-slate-500"><th className="py-1 pr-3">Waktu</th><th className="pr-3">Jenis</th><th className="pr-3 text-right">Jumlah</th><th>Keterangan</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id} className="border-t border-slate-100"><td className="py-1 pr-3 whitespace-nowrap">{new Date(r.created_at).toLocaleString("id-ID")}</td><td className="pr-3">{TYPE[r.type] ?? r.type}</td>
          <td className={`pr-3 text-right ${Number(r.amount) < 0 ? "text-red-700" : "text-green-700"}`}>{Number(r.amount) > 0 ? "+" : ""}{r.amount}</td><td className="text-xs text-slate-600">{r.description}</td></tr>)}</tbody></table></div>
    </div>
  );
}
