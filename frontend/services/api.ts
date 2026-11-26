import type { LibItem, Invoice, LedgerRow, Order, Pack, Plan, Sub, DocFull, DocSummary, DocVersion, AdminProvider, AdminProviders, AdminTool, AdminUser, AuditItem, PromptVersion, UsageReport, AiRequest, CreditSummary, Estimate, ToolDetail, ToolSummary, User } from "@/types/api";

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
  plan_not_available: "Paket ini tidak tersedia.",
  package_not_available: "Paket kredit ini tidak tersedia.",
  gateway_unavailable: "Layanan pembayaran sedang bermasalah. Anda belum ditagih; coba lagi nanti.",
  idempotency_key_required: "Permintaan tidak valid. Muat ulang halaman.",
  mfa_required: "Masukkan kode 6 digit dari aplikasi autentikator.",
  csrf_blocked: "Permintaan diblokir demi keamanan. Muat ulang halaman.",
  invalid_code: "Kode salah. Periksa jam perangkat Anda dan coba lagi.",
  premium_required: "Materi ini khusus pelanggan. Berlangganan untuk mengunduh.",
  no_file: "Berkas belum tersedia.",
  file_type_not_allowed: "Jenis berkas tidak diizinkan (pdf, docx, pptx, xlsx, txt).",
  file_content_mismatch: "Isi berkas tidak sesuai dengan ekstensinya.",
  file_size_invalid: "Ukuran berkas tidak valid (maks. 25 MB).",
  upload_a_file_before_publishing: "Unggah berkas sebelum mempublikasikan.",
  unknown_category: "Kategori tidak dikenal.",
  consent_required: "Alat ini memproses data siswa. Setujui persyaratan penggunaan data siswa terlebih dahulu.",
  subscription_required: "Alat ini khusus pelanggan. Berlangganan untuk menggunakannya.",
  server_misconfigured: "Layanan belum dikonfigurasi dengan benar. Hubungi admin.",
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
  headers.set("X-Requested-With", "fetch"); // CSRF guard for cookie endpoints: a cross-site form cannot set this
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
  export: (id: string, format: "docx" | "pdf" | "pptx", version?: number) => authedBlob(`/documents/${id}/export?format=${format}${version ? `&version=${version}` : ""}`),
  regenerate: (id: string, key: string) => authed<{ id: string; status: string }>(`/documents/${id}/regenerate`, { method: "POST", headers: { "Idempotency-Key": key } }),
};

export const lib = {
  categories: () => authed<{ slug: string; name: string }[]>("/library/categories"),
  items: (p: { q?: string; category?: string; page?: number }) => {
    const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]));
    return authed<{ total: number; items: LibItem[] }>(`/library/items?${qs}`);
  },
  download: (id: string) => authed<{ url: string; filename: string }>(`/library/items/${id}/download`, { method: "POST" }),
  adminItems: () => authed<LibItem[]>("/admin/library/items"),
  adminCreate: (b: Record<string, unknown>) => send<LibItem>("POST", "/admin/library/items", b),
  adminPatch: (id: string, b: Record<string, unknown>) => send<LibItem>("PATCH", `/admin/library/items/${id}`, b),
  adminUpload: async (id: string, file: File) => {
    const fd = new FormData(); fd.append("file", file);
    const go = () => { const h = new Headers({ "X-Requested-With": "fetch" }); if (accessToken) h.set("Authorization", `Bearer ${accessToken}`); return fetch(`/api/v1/admin/library/items/${id}/files`, { method: "POST", body: fd, headers: h }); };
    let r = await go();
    if (r.status === 401 && (await refreshSession())) r = await go();
    return parse<LibItem>(r);
  },
};

export const assistantApi = {
  list: () => authed<{ id: string; title: string }[]>("/assistant/conversations"),
  create: () => send<{ id: string; title: string }>("POST", "/assistant/conversations"),
  get: (id: string) => authed<{ id: string; title: string; messages: { id: string; role: "user" | "assistant"; content: string; request_id: string | null }[] }>(`/assistant/conversations/${id}`),
  rename: (id: string, title: string) => send("PATCH", `/assistant/conversations/${id}`, { title }),
  remove: (id: string) => authed<void>(`/assistant/conversations/${id}`, { method: "DELETE" }),
  send: (id: string, content: string, key: string) =>
    authed<{ request_id: string; status: string }>(`/assistant/conversations/${id}/messages`, { method: "POST", body: JSON.stringify({ content }), headers: { "Idempotency-Key": key } }),
};

export const privacy = {
  consent: () => authed<{ student_data: boolean; text: string }>("/me/consents"),
  give: () => send("POST", "/me/consents", { type: "student_data" }),
  revoke: () => authed<void>("/me/consents/student_data", { method: "DELETE" }),
  erase: () => send<{ documents: number; requests: number }>("POST", "/me/student-data/delete"),
};

export const billing = {
  plans: () => authedOrPublic<Plan[]>("/plans"),
  packages: () => authedOrPublic<Pack[]>("/credit-packages"),
  buyPlan: (plan_code: string, cycle: string, key: string) =>
    authed<Order>("/checkout/subscription", { method: "POST", body: JSON.stringify({ plan_code, cycle }), headers: { "Idempotency-Key": key } }),
  buyPack: (package_id: string, key: string) =>
    authed<Order>("/checkout/credits", { method: "POST", body: JSON.stringify({ package_id }), headers: { "Idempotency-Key": key } }),
  orders: () => authed<Order[]>("/orders"),
  order: (no: string) => authed<Order>(`/orders/${encodeURIComponent(no)}`),
  invoices: () => authed<Invoice[]>("/invoices"),
  subscription: () => authed<Sub>("/subscription"),
  cancel: () => authed<void>("/subscription/cancel", { method: "POST" }),
  resume: () => authed<void>("/subscription/resume", { method: "POST" }),
  ledger: (page = 1) => authed<{ items: LedgerRow[]; total: number }>(`/credits/ledger?page=${page}&page_size=25`),
  devFakePay: (no: string, outcome: string) => authed<{ status: number }>(`/dev/fake-pay/${encodeURIComponent(no)}?outcome=${outcome}`, { method: "POST" }),
};

async function authedOrPublic<T>(path: string): Promise<T> {
  return parse<T>(await raw(path));
}

export const rp = (n: number) => "Rp" + n.toLocaleString("id-ID");

export const api = {
  async login(email: string, password: string, totp?: string) {
    const t = await post("/auth/login", { email, password, ...(totp ? { totp } : {}) }) as { access_token: string };
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
  mfaSetup: () => authed<{ secret: string; otpauth_uri: string }>("/auth/mfa/setup", { method: "POST" }),
  mfaConfirm: (code: string) => authed<void>("/auth/mfa/confirm", { method: "POST", body: JSON.stringify({ code }) }),
  resendVerification: () => authed<void>("/auth/resend-verification", { method: "POST" }),
};
