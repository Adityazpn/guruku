"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { billing, errorMessage, rp } from "@/services/api";
import type { Invoice, Order } from "@/types/api";

const ST: Record<string, string> = { created: "Dibuat", pending: "Menunggu pembayaran", paid: "Lunas", failed: "Gagal", expired: "Kedaluwarsa" };

export default function PaymentsPage() {
  const [orders, setOrders] = useState<Order[] | null>(null); const [inv, setInv] = useState<Invoice[]>([]); const [err, setErr] = useState<string | null>(null);
  useEffect(() => { billing.orders().then(setOrders).catch((e) => setErr(errorMessage(e))); billing.invoices().then(setInv).catch(() => undefined); }, []);
  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-navy">Riwayat Pembayaran</h1>
      {err && <p role="alert" className="text-sm text-red-600 mt-2">{err}</p>}
      <ul className="mt-4 divide-y divide-slate-100 text-sm">
        {orders?.map((o) => (
          <li key={o.order_no} className="py-3 flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="font-medium">{o.description}</span><span>{rp(o.amount_idr)}</span><span className="text-xs rounded-full bg-slate-100 px-2 py-0.5">{ST[o.status] ?? o.status}</span>
            <span className="text-xs text-slate-500">{o.order_no} · {new Date(o.created_at).toLocaleDateString("id-ID")}</span>
            {o.status === "pending" && o.checkout_url && <a className="text-navy underline text-xs" href={o.checkout_url}>Lanjutkan pembayaran</a>}
            {o.status === "pending" && <Link className="text-navy underline text-xs" href={`/app/payments/status?order=${o.order_no}`}>Cek status</Link>}
          </li>
        ))}
        {orders?.length === 0 && <li className="py-3 text-slate-600">Belum ada transaksi.</li>}
      </ul>
      {inv.length > 0 && <><h2 className="mt-8 font-semibold text-navy">Faktur</h2>
        <ul className="mt-2 text-sm divide-y divide-slate-100">{inv.map((i) => <li key={i.number} className="py-2">{i.number} · {i.description} · {rp(i.amount_idr)} · {new Date(i.issued_at).toLocaleDateString("id-ID")}</li>)}</ul></>}
    </div>
  );
}
