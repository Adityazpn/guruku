"use client";
import { useEffect, useState } from "react";
import { btn, btn2, Card, inputCls, Msg, useAction } from "@/components/ui/Admin";
import { adminApi, errorMessage } from "@/services/api";
import type { AdminUser } from "@/types/api";

function Row({ u, onChange }: { u: AdminUser; onChange: () => void }) {
  const [amt, setAmt] = useState(""); const [why, setWhy] = useState("");
  const a = useAction();
  return (
    <div className="border-t border-slate-100 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-x-3"><b>{u.email}</b><span className="text-slate-600">kredit: {u.credits}</span><span className="text-xs text-slate-500">{u.roles.join(", ")}</span></div>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <input className={`${inputCls} w-24`} inputMode="decimal" placeholder="jumlah" aria-label={`Jumlah kredit ${u.email}`} value={amt} onChange={(e) => setAmt(e.target.value)} />
        <input className={`${inputCls} w-64`} placeholder="alasan (wajib, tercatat di audit)" aria-label={`Alasan ${u.email}`} value={why} onChange={(e) => setWhy(e.target.value)} />
        <button className={btn2} disabled={a.busy || !amt || why.trim().length < 3} onClick={() => a.run(() => adminApi.grant(u.id, Number(amt), why, 30), "Kredit bonus ditambahkan (berlaku 30 hari)", () => { setAmt(""); setWhy(""); onChange(); })}>Beri kredit</button><Msg m={a.msg} />
      </div>
    </div>
  );
}

export default function UsersAdmin() {
  const [q, setQ] = useState(""); const [rows, setRows] = useState<AdminUser[]>([]); const [err, setErr] = useState<string | null>(null);
  const search = () => adminApi.users(q).then((r) => { setRows(r); setErr(null); }).catch((e) => setErr(errorMessage(e)));
  useEffect(() => { void search(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy mb-4">Pengguna & Kredit</h1>
      <Card title="Cari pengguna">
        <div className="flex gap-2"><input className={`${inputCls} flex-1`} placeholder="email…" aria-label="Cari email" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} />
          <button className={btn} onClick={search}>Cari</button></div>
        {err && <p role="alert" className="text-sm text-red-600 mt-2">{err}</p>}
        {rows.map((u) => <Row key={u.id} u={u} onChange={search} />)}
      </Card>
    </div>
  );
}
