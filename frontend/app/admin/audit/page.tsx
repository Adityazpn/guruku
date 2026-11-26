"use client";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Admin";
import { adminApi, errorMessage } from "@/services/api";
import type { AuditItem } from "@/types/api";

export default function AuditPage() {
  const [items, setItems] = useState<AuditItem[]>([]); const [total, setTotal] = useState(0); const [err, setErr] = useState<string | null>(null);
  useEffect(() => { adminApi.audit(1).then((r) => { setItems(r.items); setTotal(r.total); }).catch((e) => setErr(errorMessage(e))); }, []);
  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-4">Log audit</h1>
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      <Card title={`${total} catatan (terbaru dulu)`}>
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-xs text-slate-500"><th className="py-1 pr-3">Waktu</th><th className="pr-3">Aksi</th><th className="pr-3">Objek</th><th>Detail</th></tr></thead>
          <tbody>{items.map((a) => (
            <tr key={a.id} className="border-t border-slate-100 align-top"><td className="py-1 pr-3 whitespace-nowrap">{new Date(a.created_at).toLocaleString("id-ID")}</td><td className="pr-3 font-mono text-xs">{a.action}</td>
              <td className="pr-3 text-xs">{a.entity_type}</td><td className="text-xs break-all">{a.after ? JSON.stringify(a.after) : ""}</td></tr>))}</tbody></table></div>
      </Card>
    </div>
  );
}
