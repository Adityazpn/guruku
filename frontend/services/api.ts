import type { User } from "@/types/api";

export class ApiError extends Error {
  constructor(public status: number, public code: string) {
    super(code);
  }
}

const MESSAGES: Record<string, string> = {
  invalid_credentials: "Email atau kata sandi salah.",
  account_locked: "Akun dikunci sementara karena terlalu banyak percobaan. Coba lagi dalam 15 menit.",
  account_disabled: "Akun tidak aktif.",
  email_taken: "Email sudah terdaftar.",
  invalid_token: "Tautan tidak valid atau sudah kedaluwarsa.",
  rate_limited: "Terlalu banyak permintaan. Coba lagi sebentar lagi.",
};

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return MESSAGES[e.code] ?? "Terjadi kesalahan. Coba lagi.";
  return "Tidak dapat terhubung ke server.";
}

// Access token lives in memory only (never localStorage); the refresh token is an HttpOnly cookie.
let accessToken: string | null = null;
export const setAccessToken = (t: string | null) => { accessToken = t; };

async function raw(path: string, init: RequestInit = {}, auth = false): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (auth && accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  return fetch(`/api/v1${path}`, { ...init, headers, credentials: "same-origin" });
}

async function parse<T>(r: Response): Promise<T> {
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const code = typeof data.detail === "string" ? data.detail : r.status === 422 ? "validation" : "error";
    throw new ApiError(r.status, code);
  }
  return data as T;
}

export async function refreshSession(): Promise<boolean> {
  const r = await raw("/auth/refresh", { method: "POST" });
  if (!r.ok) { setAccessToken(null); return false; }
  setAccessToken((await r.json()).access_token);
  return true;
}

/** Authenticated request; retries once after a silent refresh on 401. */
export async function authed<T>(path: string, init: RequestInit = {}): Promise<T> {
  let r = await raw(path, init, true);
  if (r.status === 401 && (await refreshSession())) r = await raw(path, init, true);
  return parse<T>(r);
}

const post = (path: string, body: unknown) => raw(path, { method: "POST", body: JSON.stringify(body) }).then(parse);

export const api = {
  async login(email: string, password: string) {
    const t = await post("/auth/login", { email, password }) as { access_token: string };
    setAccessToken(t.access_token);
  },
  register: (email: string, password: string, full_name: string) => post("/auth/register", { email, password, full_name }),
  forgot: (email: string) => post("/auth/forgot-password", { email }),
  reset: (token: string, new_password: string) => post("/auth/reset-password", { token, new_password }),
  verify: (token: string) => post("/auth/verify-email", { token }),
  async logout() {
    await raw("/auth/logout", { method: "POST" });
    setAccessToken(null);
  },
  me: () => authed<User>("/me"),
  resendVerification: () => authed<void>("/auth/resend-verification", { method: "POST" }),
};
