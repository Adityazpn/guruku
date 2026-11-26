"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";

const NAV: [string, string, boolean][] = [["Ringkasan", "/admin", false], ["Provider AI", "/admin/providers", false],
  ["Alat & Prompt", "/admin/tools", false], ["Pustaka", "/admin/library", false], ["Pengguna & Kredit", "/admin/users", true], ["Audit", "/admin/audit", true]];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const roles = user?.roles ?? [];
  const allowed = roles.includes("super_admin") || roles.includes("ai_admin") || roles.includes("content_admin");
  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login"); else if (!allowed) router.replace("/app");
  }, [loading, user, allowed, router]);
  if (loading || !user || !allowed) return <p className="p-6 text-sm text-slate-600">Memuat…</p>;
  const root = roles.includes("super_admin");
  return (
    <div className="min-h-screen">
      <header className="bg-navy text-white px-4 h-14 flex items-center gap-4 overflow-x-auto">
        <span className="font-bold">Admin</span>
        <nav className="flex gap-1 text-sm">
          {NAV.filter(([, h, rootOnly]) => (root || !rootOnly) && (roles.includes("super_admin") || roles.includes("ai_admin") || h === "/admin/library")).map(([l, h]) => (
            <Link key={h} href={h} className={`px-3 py-1.5 rounded-lg whitespace-nowrap ${path === h ? "bg-white/15" : "hover:bg-white/10"}`}>{l}</Link>
          ))}
        </nav>
        <Link href="/app" className="ml-auto text-sm text-white/80 whitespace-nowrap">← Aplikasi</Link>
      </header>
      <div className="p-4 sm:p-6 max-w-5xl mx-auto">{children}</div>
    </div>
  );
}
