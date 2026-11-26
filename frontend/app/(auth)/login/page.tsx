"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthCard, Field, Notice, Submit } from "@/components/ui/AuthCard";
import { useAuth } from "@/hooks/useAuth";
import { validateEmail } from "@/lib/validation";
import { api, errorMessage } from "@/services/api";

export default function LoginPage() {
  const router = useRouter();
  const { reload } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const v = validateEmail(email);
    if (v || !password) return setErr(v ?? "Kata sandi wajib diisi");
    setBusy(true); setErr(null);
    try { await api.login(email, password); await reload(); router.push("/app"); }
    catch (x) { setErr(errorMessage(x)); }
    finally { setBusy(false); }
  }

  return (
    <AuthCard title="Masuk" subtitle="Selamat datang kembali.">
      <form onSubmit={onSubmit} noValidate>
        {err && <Notice kind="error">{err}</Notice>}
        <Field label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field label="Kata sandi" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <Submit busy={busy}>Masuk</Submit>
      </form>
      <div className="mt-4 text-sm flex justify-between">
        <Link href="/forgot-password" className="text-navy">Lupa kata sandi?</Link>
        <Link href="/register" className="text-navy">Buat akun</Link>
      </div>
    </AuthCard>
  );
}
