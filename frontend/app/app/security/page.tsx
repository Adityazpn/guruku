"use client";
import { useState } from "react";
import { Notice } from "@/components/ui/AuthCard";
import { useAuth } from "@/hooks/useAuth";
import { api, errorMessage, privacy } from "@/services/api";

export default function SecurityPage() {
  const { user, reload } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState(""); const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  if (!user) return null;
  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-semibold text-navy">Keamanan akun</h1>
      <section className="mt-4 rounded-xl border border-slate-200 p-4">
        <h2 className="font-semibold">Autentikasi dua langkah (TOTP)</h2>
        <p className="text-sm text-slate-600 mt-1">Wajib untuk akun admin. Gunakan aplikasi autentikator (Google Authenticator, Authy, 1Password, dll.).</p>
        {user.mfa_enabled ? <p className="mt-3 text-sm text-green-700">Aktif.</p> : !setup ? (
          <button className="mt-3 rounded-lg bg-navy text-white px-4 py-2 text-sm" onClick={() => api.mfaSetup().then(setSetup).catch((e) => setMsg({ kind: "error", text: errorMessage(e) }))}>Aktifkan</button>
        ) : (
          <div className="mt-3 text-sm space-y-2">
            <p>Tambahkan akun ke aplikasi autentikator dengan <b>memasukkan kunci ini secara manual</b> (jenis: berbasis waktu):</p>
            <code className="block break-all rounded bg-slate-100 p-2" data-testid="mfa-secret">{setup.secret}</code>
            <p className="text-xs text-slate-500">Atau buka tautan <a className="underline" href={setup.otpauth_uri}>otpauth</a> di perangkat yang memiliki aplikasi autentikator. Kunci ini hanya ditampilkan sekali.</p>
            <input className="rounded-lg border border-slate-300 px-3 py-2 w-40" inputMode="numeric" placeholder="Kode 6 digit" aria-label="Kode" value={code} onChange={(e) => setCode(e.target.value)} />
            <button className="ml-2 rounded-lg bg-navy text-white px-4 py-2" onClick={() => api.mfaConfirm(code).then(async () => { setMsg({ kind: "ok", text: "Aktif. Keluar dan masuk lagi dengan kode." }); setSetup(null); await reload(); }).catch((e) => setMsg({ kind: "error", text: errorMessage(e) }))}>Konfirmasi</button>
          </div>
        )}
        {msg && <div className="mt-3"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
      </section>
      <section className="mt-4 rounded-xl border border-slate-200 p-4">
        <h2 className="font-semibold">Data siswa</h2>
        <p className="text-sm text-slate-600 mt-1">Cabut persetujuan pemrosesan data siswa, atau hapus semua dokumen dan data permintaan dari alat analisis siswa.</p>
        <div className="mt-3 flex flex-wrap gap-2 text-sm">
          <button className="rounded-lg border border-navy text-navy px-3 py-1.5" onClick={() => privacy.revoke().then(() => setMsg({ kind: "ok", text: "Persetujuan dicabut." })).catch((e) => setMsg({ kind: "error", text: errorMessage(e) }))}>Cabut persetujuan</button>
          <button className="rounded-lg border border-red-600 text-red-600 px-3 py-1.5" onClick={() => { if (confirm("Hapus permanen semua dokumen & data dari alat analisis siswa? Tindakan ini tidak dapat dibatalkan.")) void privacy.erase().then((r) => setMsg({ kind: "ok", text: `Dihapus: ${r.documents} dokumen, ${r.requests} data permintaan.` })).catch((e) => setMsg({ kind: "error", text: errorMessage(e) })); }}>Hapus semua data siswa</button>
        </div>
      </section>
    </div>
  );
}
