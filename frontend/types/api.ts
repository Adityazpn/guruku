export interface User {
  id: string;
  email: string;
  full_name: string;
  roles: string[];
  email_verified: boolean;
}

export interface ToolSummary { slug: string; name: string; category: string; description: string }
export interface ToolDetail extends ToolSummary { input_schema: JsonSchema }
export interface JsonSchema {
  required?: string[];
  properties: Record<string, { type?: string; enum?: string[]; minLength?: number; maxLength?: number; minimum?: number; maximum?: number }>;
}
export interface Estimate { mode: string; expected: string; min: string; max: string; balance: string; sufficient: boolean }
export interface AiRequest {
  id: string; tool_slug: string; status: "queued" | "running" | "succeeded" | "failed";
  output: Record<string, unknown> | null; error_code: string | null;
  credits_reserved: string; credits_charged: string | null; created_at: string; finished_at: string | null;
}
export interface CreditSummary { subscription: string; bonus: string; purchased: string; total: string; next_expiry: string | null }

export interface AdminModel {
  id: string; model_code: string; display_name: string; status: string; max_output_tokens: number;
  pricing: { version: number; input_per_1m: number; output_per_1m: number; cached_input_per_1m: number | null; currency: string } | null;
}
export interface AdminProvider {
  id: string; code: string; name: string; status: string; base_url: string | null;
  daily_spend_limit_usd: number | null; monthly_spend_limit_usd: number | null;
  credential: { label: string; last4: string; status: string } | null; env_key_present: boolean;
  spend_today_usd: number; spend_month_usd: number; models: AdminModel[];
}
export interface AdminProviders { providers: AdminProvider[]; supported_codes: string[]; fx: { rate: number; effective_from: string } | null }
export interface AdminTool {
  id: string; slug: string; name: string; description: string; is_active: boolean; ready: boolean; problems: string[];
  models: { id: string; model_code: string; provider: string; status: string }[]; published_prompt_version: number | null;
  pricing_rule: Record<string, string | number> | null;
}
export interface PromptVersion { id: string; version: number; status: string; system_prompt: string; user_template: string; temperature: number; change_note: string }
export interface UsageReport {
  days: number; is_estimate: boolean;
  totals: { requests: number; failed: number; api_cost_usd: number; api_cost_idr: number; credits_charged: number };
  items: { tool: string; model: string | null; requests: number; succeeded: number; failed: number; api_cost_usd: number | null; credits_charged: number | null }[];
}
export interface AdminUser { id: string; email: string; full_name: string; status: string; roles: string[]; credits: string }
export interface AuditItem { id: string; actor_id: string | null; action: string; entity_type: string; entity_id: string; created_at: string; after: unknown }
