"use client";
import { useAuth } from "@/hooks/useAuth";
import { api, errorMessage } from "@/services/api";
import { useState } from "react";

export default function Overview() {
  const { user } = useAuth();
  const [msg, setMsg] = useState<string | null>(null);
  if (!user) return null;
  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-navy">Halo, {user.full_name || user.email}</h1>
      {!user.email_verified && (
        <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 text-amber-900 text-sm p-3">
          Email Anda belum terverifikasi.{" "}
          <button className="underline" onClick={() => api.resendVerification().then(() => setMsg("Tautan dikirim ulang.")).catch((e) => setMsg(errorMessage(e)))}>
            Kirim ulang tautan
          </button>
          {msg && <span className="ml-2">{msg}</span>}
        </div>
      )}
      <p className="mt-6 text-sm text-slate-600">
        Alat AI, kredit, dan langganan akan tersedia pada tahap berikutnya. Menu yang belum aktif ditandai abu-abu.
      </p>
    </div>
  );
}
