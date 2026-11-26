"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, refreshSession } from "@/services/api";
import type { User } from "@/types/api";

interface AuthState {
  user: User | null;
  loading: boolean;
  reload: () => Promise<void>;
  logout: () => Promise<void>;
}
const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      if (await refreshSession()) setUser(await api.me());
      else setUser(null);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  const logout = useCallback(async () => { await api.logout(); setUser(null); }, []);
  return <Ctx.Provider value={{ user, loading, reload, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
