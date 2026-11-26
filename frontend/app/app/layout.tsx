"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";

const NAV = [
  ["Ringkasan", "/app"], ["Generator AI", "/app/tools"], ["Asisten AI", "#"], ["Perencanaan", "#"], ["Asesmen", "#"],
  ["Administrasi", "#"], ["Analisis Siswa", "#"], ["Media Belajar", "#"], ["Pustaka", "#"],
  ["Dokumen Saya", "#"], ["Kredit AI", "#"], ["Langganan", "#"], ["Profil", "#"],
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => { if (!loading && !user) router.replace("/login"); }, [loading, user, router]);
  if (loading || !user) return <p className="p-6 text-sm text-slate-600">Memuat…</p>;

  return (
    <div className="min-h-screen md:flex">
      <aside className={`${open ? "block" : "hidden"} md:block md:w-60 bg-navy text-white p-4 shrink-0`}>
        <div className="font-bold text-lg mb-6">Guruku</div>
        <nav className="space-y-1 text-sm">
          {NAV.map(([label, href]) => (
            href === "#"
              ? <span key={label} className="block px-3 py-2 rounded-lg text-white/50 cursor-not-allowed" title="Segera hadir">{label}</span>
              : <Link key={label} href={href} className={`block px-3 py-2 rounded-lg ${pathname === href || (href !== "/app" && pathname.startsWith(href)) ? "bg-white/15" : "hover:bg-white/10"}`}>{label}</Link>
          ))}
        </nav>
      </aside>
      <div className="flex-1 min-w-0">
        <header className="h-14 border-b border-slate-200 flex items-center justify-between px-4">
          <button className="md:hidden text-navy text-sm" onClick={() => setOpen(!open)} aria-label="Menu">Menu</button>
          <span className="text-sm text-slate-600 ml-auto mr-4 truncate">{user.email}</span>
          <button onClick={async () => { await logout(); router.push("/login"); }} className="text-sm text-navy">Keluar</button>
        </header>
        <div className="p-4 sm:p-6">{children}</div>
      </div>
    </div>
  );
}
