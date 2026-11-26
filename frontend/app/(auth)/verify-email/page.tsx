"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AuthCard, Notice } from "@/components/ui/AuthCard";
import { api, errorMessage } from "@/services/api";

function Verify() {
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<"loading" | "ok" | string>("loading");

  useEffect(() => {
    api.verify(token).then(() => setState("ok")).catch((e) => setState(errorMessage(e)));
  }, [token]);

  if (state === "loading") return <p className="text-sm text-slate-600">Memverifikasi…</p>;
  return (
    <>
      {state === "ok" ? <Notice kind="ok">Email berhasil diverifikasi.</Notice> : <Notice kind="error">{state}</Notice>}
      <Link href="/app" className="text-navy text-sm">Ke dasbor</Link>
    </>
  );
}

export default function VerifyPage() {
  return <AuthCard title="Verifikasi email"><Suspense><Verify /></Suspense></AuthCard>;
}
