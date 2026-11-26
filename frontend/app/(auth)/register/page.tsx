"use client";
import Link from "next/link";
import { useState } from "react";
import { AuthCard, Field, Notice, Submit } from "@/components/ui/AuthCard";
import { validateEmail, validatePassword } from "@/lib/validation";
import { api, errorMessage } from "@/services/api";

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errs, setErrs] = useState<{ email?: string | null; password?: string | null }>({});
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const fe = { email: validateEmail(email), password: validatePassword(password) };
    setErrs(fe);
    if (fe.email || fe.password) return;
    setBusy(true); setErr(null);
    try { await api.register(email, password, name); setDone(true); }
    catch (x) { setErr(errorMessage(x)); }
    finally { setBusy(false); }
  }

  if (done)
    return (
      <AuthCard title="Cek email Anda">
        <Notice kind="ok">Kami mengirim tautan verifikasi ke {email}.</Notice>
        <Link href="/login" className="text-navy text-sm">Lanjut ke halaman masuk</Link>
      </AuthCard>
    );

  return (
    <AuthCard title="Buat akun" subtitle="Gratis untuk dicoba.">
      <form onSubmit={onSubmit} noValidate>
        {err && <Notice kind="error">{err}</Notice>}
        <Field label="Nama lengkap" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
        <Field label="Email" type="email" value={email} error={errs.email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        <Field label="Kata sandi (min. 10 karakter)" type="password" value={password} error={errs.password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        <Submit busy={busy}>Daftar</Submit>
      </form>
      <p className="mt-4 text-sm">Sudah punya akun? <Link href="/login" className="text-navy">Masuk</Link></p>
    </AuthCard>
  );
}
