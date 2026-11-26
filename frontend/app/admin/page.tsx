"use client";
import { useEffect, useState } from "react";
import { Badge, Card, PROBLEMS } from "@/components/ui/Admin";
import { adminApi, errorMessage } from "@/services/api";
import type { AdminTool, UsageReport } from "@/types/api";

export default function AdminHome() {
  const [u, setU] = useState<UsageReport | null>(null);
  const [tools, setTools] = useState<AdminTool[]>([]);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    adminApi.usage(30).then(setU).catch((e) => setErr(errorMessage(e)));
    adminApi.tools().then(setTools).catch(() => undefined);
  }, []);
  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-4">Ringkasan</h1>
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      <Card title="Biaya API 30 hari terakhir (estimasi)">
        {u && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {([["Permintaan", u.totals.requests], ["Gagal", u.totals.failed], ["Biaya API (USD)", u.totals.api_cost_usd.toFixed(4)],
                 ["Kredit ditagih", u.totals.credits_charged]] as const).map(([l, v]) => (
                <div key={l} className="rounded-lg bg-navy-50 p-3"><div className="text-xs text-slate-500">{l}</div><div className="text-xl font-semibold text-navy">{v}</div></div>
              ))}
            </div>
            <p className="text-xs text-slate-500 mt-2">Dihitung dari token yang dilaporkan penyedia × harga yang Anda isi. Ini estimasi, bukan tagihan resmi penyedia.</p>
          </>
        )}
      </Card>
      <Card title="Kesiapan alat">
        {tools.map((t) => (
          <div key={t.id} className="flex flex-wrap items-center gap-2 py-1 text-sm">
            <span className="font-medium">{t.name}</span>
            {t.ready ? <Badge tone="ok">siap</Badge> : <Badge tone="warn">belum siap</Badge>}
            {!t.is_active && <Badge tone="idle">nonaktif</Badge>}
            <span className="text-xs text-slate-600">{t.problems.map((p) => PROBLEMS[p] ?? p).join(" · ")}</span>
          </div>
        ))}
      </Card>
    </div>
  );
}
