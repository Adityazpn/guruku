"use client";
import Link from "next/link";
import { useState } from "react";
import { AuthCard, Field, Notice, Submit } from "@/components/ui/AuthCard";
import { validateEmail } from "@/lib/validation";
import { api, errorMessage } from "@/services/api";

export default function ForgotPage() {
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const v = validateEmail(email);
    if (v) return setErr(v);
    setBusy(true); setErr(null);
    try { await api.forgot(email); setDone(true); }
    catch (x) { setErr(errorMessage(x)); }
    finally { setBusy(false); }
  }

  return (
    <AuthCard title="Lupa kata sandi">
      {done ? (
        <Notice kind="ok">Jika email terdaftar, tautan pengaturan ulang telah dikirim.</Notice>
      ) : (
        <form onSubmit={onSubmit} noValidate>
          {err && <Notice kind="error">{err}</Notice>}
          <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <Submit busy={busy}>Kirim tautan</Submit>
        </form>
      )}
      <p className="mt-4 text-sm"><Link href="/login" className="text-navy">Kembali ke masuk</Link></p>
    </AuthCard>
  );
}
