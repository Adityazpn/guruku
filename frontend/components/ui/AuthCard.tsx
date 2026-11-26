import Link from "next/link";

export function AuthCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-navy-50 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <Link href="/" className="block text-center text-xl font-bold text-navy mb-6">Guruku</Link>
        <div className="bg-white rounded-xl border border-slate-200 p-6 sm:p-8 shadow-sm">
          <h1 className="text-xl font-semibold text-navy">{title}</h1>
          {subtitle && <p className="text-sm text-slate-600 mt-1">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </main>
  );
}

export function Field({ label, error, ...props }: { label: string; error?: string | null } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block mb-4">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <input
        {...props}
        aria-invalid={!!error}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
      />
      {error && <span role="alert" className="text-xs text-red-600">{error}</span>}
    </label>
  );
}

export function Submit({ busy, children }: { busy: boolean; children: React.ReactNode }) {
  return (
    <button type="submit" disabled={busy}
      className="w-full rounded-lg bg-navy text-white py-2.5 text-sm font-medium hover:bg-navy-700 disabled:opacity-60">
      {busy ? "Memproses…" : children}
    </button>
  );
}

export function Notice({ kind, children }: { kind: "error" | "ok"; children: React.ReactNode }) {
  const c = kind === "error" ? "bg-red-50 text-red-700 border-red-200" : "bg-accent-100 text-navy border-accent";
  return <div role={kind === "error" ? "alert" : "status"} className={`mb-4 rounded-lg border px-3 py-2 text-sm ${c}`}>{children}</div>;
}
