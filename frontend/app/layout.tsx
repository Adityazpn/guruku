import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "@/styles/globals.css";
import { AuthProvider } from "@/hooks/useAuth";

export const metadata: Metadata = {
  title: "Guruku — Asisten AI untuk Guru Indonesia",
  description: "Platform produktivitas pendidikan berbasis AI untuk guru.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body className="font-sans"><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}
