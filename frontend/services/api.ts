import type { DocFull, DocSummary, DocVersion, AdminProvider, AdminProviders, AdminTool, AdminUser, AuditItem, PromptVersion, UsageReport, AiRequest, CreditSummary, Estimate, ToolDetail, ToolSummary, User } from "@/types/api";

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
  no_credential: "Provider belum punya API key. Simpan key terlebih dahulu.",
  unsupported_provider: "Provider ini belum didukung.",
  provider_exists: "Provider sudah ada.",
  model_exists: "Model sudah ada.",
  validation: "Isian tidak valid. Periksa angka dan batasnya.",
  forbidden: "Anda tidak memiliki akses.",
  version_conflict: "Dokumen ini sudah diubah di tempat lain. Muat ulang halaman sebelum menyimpan.",
  not_found: "Dokumen tidak ditemukan.",
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

const send = <T,>(method: string, path: string, body?: unknown) =>
  authed<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

export const adminApi = {
  providers: () => authed<AdminProviders>("/admin/providers"),
  createProvider: (code: string, name: string) => send<AdminProvider>("POST", "/admin/providers", { code, name }),
  patchProvider: (id: string, body: Record<string, unknown>) => send<AdminProvider>("PATCH", `/admin/providers/${id}`, body),
  setKey: (id: string, api_key: string, label: string) => send<AdminProvider>("PUT", `/admin/providers/${id}/credential`, { api_key, label }),
  testProvider: (id: string, model_id: string) => send<{ ok: boolean; error?: string }>("POST", `/admin/providers/${id}/test`, { model_id }),
  addModel: (id: string, model_code: string) => send<AdminProvider>("POST", `/admin/providers/${id}/models`, { model_code }),
  patchModel: (id: string, body: Record<string, unknown>) => send<AdminProvider>("PATCH", `/admin/models/${id}`, body),
  setPrice: (id: string, input_per_1m: number, output_per_1m: number, cached?: number) =>
    send<AdminProvider>("POST", `/admin/models/${id}/pricing`, { input_per_1m, output_per_1m, cached_input_per_1m: cached }),
  setFx: (rate: number) => send<{ rate: number }>("POST", "/admin/fx-rates", { rate }),
  tools: () => authed<AdminTool[]>("/admin/tools"),
  patchTool: (id: string, body: Record<string, unknown>) => send<AdminTool>("PATCH", `/admin/tools/${id}`, body),
  assign: (id: string, model_ids: string[]) => send<AdminTool>("PUT", `/admin/tools/${id}/assignments`, { model_ids }),
  setRule: (id: string, body: Record<string, unknown>) => send<AdminTool>("PUT", `/admin/tools/${id}/pricing-rule`, body),
  prompts: (id: string) => authed<PromptVersion[]>(`/admin/tools/${id}/prompts`),
  createPrompt: (id: string, body: Record<string, unknown>) => send<PromptVersion>("POST", `/admin/tools/${id}/prompts`, body),
  publishPrompt: (vid: string) => send<PromptVersion>("POST", `/admin/prompts/${vid}/publish`),
  rollback: (id: string, version: number) => send<PromptVersion>("POST", `/admin/tools/${id}/prompts/rollback`, { version }),
  usage: (days = 30) => authed<UsageReport>(`/admin/ai/usage?days=${days}`),
  users: (q: string) => authed<AdminUser[]>(`/admin/users?q=${encodeURIComponent(q)}`),
  grant: (id: string, amount: number, reason: string, expires_in_days: number) =>
    send<{ total: string }>("POST", `/admin/users/${id}/credits/grant`, { amount, reason, expires_in_days, kind: "bonus" }),
  audit: (page = 1) => authed<{ total: number; items: AuditItem[] }>(`/admin/audit-logs?page=${page}`),
};

export const docsApi = {
  list: (page = 1, q = "") => authed<{ total: number; items: DocSummary[] }>(`/documents?page=${page}&q=${encodeURIComponent(q)}`),
  get: (id: string) => authed<DocFull>(`/documents/${id}`),
  save: (id: string, body: { title?: string; content?: Record<string, unknown>; note?: string; base_version: number }) => send<DocFull>("PATCH", `/documents/${id}`, body),
  remove: (id: string) => authed<void>(`/documents/${id}`, { method: "DELETE" }),
  duplicate: (id: string) => send<DocFull>("POST", `/documents/${id}/duplicate`),
  versions: (id: string) => authed<DocVersion[]>(`/documents/${id}/versions`),
  restore: (id: string, version: number) => send<DocFull>("POST", `/documents/${id}/restore`, { version }),
  export: (id: string, format: "docx" | "pdf", version?: number) => authedBlob(`/documents/${id}/export?format=${format}${version ? `&version=${version}` : ""}`),
  regenerate: (id: string, key: string) => authed<{ id: string; status: string }>(`/documents/${id}/regenerate`, { method: "POST", headers: { "Idempotency-Key": key } }),
};

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
