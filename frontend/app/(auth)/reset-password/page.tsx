"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthCard, Field, Notice, Submit } from "@/components/ui/AuthCard";
import { validatePassword } from "@/lib/validation";
import { api, errorMessage } from "@/services/api";

function Form() {
  const token = useSearchParams().get("token") ?? "";
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const v = validatePassword(pw);
    if (v) return setErr(v);
    setBusy(true); setErr(null);
    try { await api.reset(token, pw); setDone(true); }
    catch (x) { setErr(errorMessage(x)); }
    finally { setBusy(false); }
  }

  if (done) return <><Notice kind="ok">Kata sandi diperbarui.</Notice><Link href="/login" className="text-navy text-sm">Masuk</Link></>;
  return (
    <form onSubmit={onSubmit} noValidate>
      {err && <Notice kind="error">{err}</Notice>}
      <Field label="Kata sandi baru" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" />
      <Submit busy={busy}>Simpan</Submit>
    </form>
  );
}

export default function ResetPage() {
  return <AuthCard title="Atur ulang kata sandi"><Suspense><Form /></Suspense></AuthCard>;
}
