import type { AiRequest, CreditSummary, Estimate, ToolDetail, ToolSummary, User } from "@/types/api";

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
  insufficient_credits: "Kredit tidak cukup. Tambah kredit atau tunggu alokasi bulan depan.",
  invalid_input: "Isian belum lengkap atau tidak valid.",
  pricing_missing: "Alat ini belum dikonfigurasi. Hubungi admin.",
  no_model_available: "Layanan AI sedang tidak tersedia. Coba lagi nanti.",
  tool_not_ready: "Alat ini belum siap digunakan.",
  malformed_output: "AI tidak menghasilkan keluaran yang valid. Kredit Anda dikembalikan; silakan coba lagi.",
  provider_unavailable: "Layanan AI sedang bermasalah. Kredit Anda dikembalikan.",
  provider_timeout: "Layanan AI terlalu lama merespons. Kredit Anda dikembalikan.",
  spend_limit: "Layanan AI sementara dibatasi. Kredit Anda dikembalikan.",
  worker_lost: "Proses terhenti. Kredit Anda dikembalikan; silakan coba lagi.",
  invalid_token: "Tautan tidak valid atau sudah kedaluwarsa.",
  rate_limited: "Terlalu banyak permintaan. Coba lagi sebentar lagi.",
};

export function messageFor(code: string | null): string {
  return (code && MESSAGES[code]) || "Terjadi kesalahan. Coba lagi.";
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return messageFor(e.code);
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

export async function authedBlob(path: string): Promise<{ blob: Blob; filename: string }> {
  let r = await raw(path, {}, true);
  if (r.status === 401 && (await refreshSession())) r = await raw(path, {}, true);
  if (!r.ok) throw new ApiError(r.status, "download_failed");
  const m = /filename="([^"]+)"/.exec(r.headers.get("Content-Disposition") ?? "");
  return { blob: await r.blob(), filename: m?.[1] ?? "dokumen" };
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
  credits: () => authed<CreditSummary>("/credits/summary"),
  tools: () => authed<ToolSummary[]>("/tools"),
  tool: (slug: string) => authed<ToolDetail>(`/tools/${slug}`),
  estimate: (slug: string) => authed<Estimate>(`/tools/${slug}/estimate`, { method: "POST" }),
  generate: (slug: string, input: Record<string, unknown>, key: string) =>
    authed<AiRequest>(`/tools/${slug}/generate`, { method: "POST", body: JSON.stringify({ input }), headers: { "Idempotency-Key": key } }),
  request: (id: string) => authed<AiRequest>(`/ai/requests/${id}`),
  exportDoc: (id: string, format: "docx" | "pdf") => authedBlob(`/ai/requests/${id}/export?format=${format}`),
  resendVerification: () => authed<void>("/auth/resend-verification", { method: "POST" }),
};
