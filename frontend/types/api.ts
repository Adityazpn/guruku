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
