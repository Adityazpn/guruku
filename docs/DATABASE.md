# Database schema (generated)

Generated from the SQLAlchemy models by `scripts/gen_docs.py`. See docs/SPEC_02 for design intent.

Conventions: UUID primary keys, `timestamptz` UTC, append-only tables (`credit_transactions`, `audit_logs`) are protected by PostgreSQL triggers (migrations 0003, 0005).


## `ai_providers`

| column | type | null | key / constraint |
|---|---|---|---|
| code | VARCHAR(30) | no | unique |
| name | VARCHAR(100) | no |  |
| status | VARCHAR(10) | no |  |
| base_url | VARCHAR(300) | yes |  |
| daily_spend_limit_usd | NUMERIC(14, 4) | yes |  |
| monthly_spend_limit_usd | NUMERIC(14, 4) | yes |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(code)

## `ai_tools`

| column | type | null | key / constraint |
|---|---|---|---|
| slug | VARCHAR(80) | no | unique |
| name | VARCHAR(150) | no |  |
| category | VARCHAR(40) | no |  |
| description | VARCHAR(500) | no |  |
| input_schema | JSON | no |  |
| output_schema | JSON | no |  |
| is_active | BOOLEAN | no |  |
| est_input_tokens | INTEGER | no |  |
| est_output_tokens | INTEGER | no |  |
| max_output_tokens | INTEGER | no |  |
| sort | INTEGER | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(slug)

## `audit_logs`

| column | type | null | key / constraint |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| actor_id | CHAR(32) | yes |  |
| action | VARCHAR(60) | no |  |
| entity_type | VARCHAR(40) | no |  |
| entity_id | VARCHAR(80) | no |  |
| before | JSON | yes |  |
| after | JSON | yes |  |
| ip | VARCHAR(64) | yes |  |
| created_at | DATETIME | no |  |

## `credit_packages`

| column | type | null | key / constraint |
|---|---|---|---|
| name | VARCHAR(100) | no |  |
| credits | NUMERIC(12, 2) | no |  |
| price_idr | INTEGER | no |  |
| bonus_credits | NUMERIC(12, 2) | no |  |
| bonus_expiry_days | INTEGER | no |  |
| purchased_expiry_days | INTEGER | yes |  |
| active | BOOLEAN | no |  |
| sort | INTEGER | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `credit_pricing_rules`

| column | type | null | key / constraint |
|---|---|---|---|
| tool_slug | VARCHAR(80) | yes |  |
| version | INTEGER | no |  |
| active | BOOLEAN | no |  |
| mode | VARCHAR(10) | no |  |
| fixed_credits | NUMERIC(12, 2) | no |  |
| base_credits | NUMERIC(12, 2) | no |  |
| margin_pct | NUMERIC(8, 2) | no |  |
| processing_fee_idr | NUMERIC(12, 2) | no |  |
| credit_value_idr | NUMERIC(12, 2) | no |  |
| rounding_step | NUMERIC(6, 2) | no |  |
| min_credits | NUMERIC(12, 2) | no |  |
| max_credits | NUMERIC(12, 2) | no |  |
| reserve_safety_factor | NUMERIC(6, 2) | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `credit_settings`

| column | type | null | key / constraint |
|---|---|---|---|
| key | VARCHAR(60) | no | unique |
| value | JSON | yes |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(key)

## `fx_rates`

| column | type | null | key / constraint |
|---|---|---|---|
| base | VARCHAR(3) | no |  |
| quote | VARCHAR(3) | no |  |
| rate | NUMERIC(14, 4) | no |  |
| effective_from | DATETIME | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `payment_webhooks`

| column | type | null | key / constraint |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| gateway | VARCHAR(20) | no |  |
| event_id | VARCHAR(200) | no |  |
| signature_valid | BOOLEAN | no |  |
| payload | JSON | yes |  |
| process_status | VARCHAR(30) | no |  |
| received_at | DATETIME | no |  |

Constraints/indexes: unique(gateway, event_id)

## `plans`

| column | type | null | key / constraint |
|---|---|---|---|
| code | VARCHAR(40) | no | unique |
| name | VARCHAR(100) | no |  |
| description | VARCHAR(500) | no |  |
| credits_monthly | NUMERIC(12, 2) | no |  |
| features | JSON | no |  |
| active | BOOLEAN | no |  |
| sort | INTEGER | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(code)

## `roles`

| column | type | null | key / constraint |
|---|---|---|---|
| code | VARCHAR(50) | no | unique |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(code)

## `users`

| column | type | null | key / constraint |
|---|---|---|---|
| email | VARCHAR(320) | no | unique |
| password_hash | VARCHAR(255) | no |  |
| full_name | VARCHAR(200) | no |  |
| status | VARCHAR(20) | no |  |
| email_verified_at | DATETIME | yes |  |
| last_login_at | DATETIME | yes |  |
| mfa_secret_enc | VARCHAR(300) | yes |  |
| mfa_enabled | BOOLEAN | no |  |
| failed_login_count | INTEGER | no |  |
| locked_until | DATETIME | yes |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `ai_models`

| column | type | null | key / constraint |
|---|---|---|---|
| provider_id | CHAR(32) | no | FK → ai_providers.id |
| model_code | VARCHAR(100) | no |  |
| display_name | VARCHAR(100) | no |  |
| status | VARCHAR(10) | no |  |
| max_output_tokens | INTEGER | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(provider_id, model_code)

## `ai_prompt_versions`

| column | type | null | key / constraint |
|---|---|---|---|
| tool_id | CHAR(32) | no | FK → ai_tools.id |
| version | INTEGER | no |  |
| system_prompt | TEXT | no |  |
| user_template | TEXT | no |  |
| temperature | NUMERIC(3, 2) | no |  |
| status | VARCHAR(10) | no |  |
| change_note | VARCHAR(300) | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(tool_id, version)

## `ai_provider_credentials`

| column | type | null | key / constraint |
|---|---|---|---|
| provider_id | CHAR(32) | no | FK → ai_providers.id |
| label | VARCHAR(100) | no |  |
| secret_ciphertext | VARCHAR(1000) | no |  |
| key_id | VARCHAR(10) | no |  |
| last4 | VARCHAR(4) | no |  |
| status | VARCHAR(10) | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `credit_wallets`

| column | type | null | key / constraint |
|---|---|---|---|
| user_id | CHAR(32) | no | FK → users.id, unique |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(user_id)

## `email_tokens`

| column | type | null | key / constraint |
|---|---|---|---|
| user_id | CHAR(32) | no | FK → users.id |
| purpose | VARCHAR(20) | no |  |
| token_hash | VARCHAR(64) | no | unique |
| expires_at | DATETIME | no |  |
| used_at | DATETIME | yes |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(token_hash)

## `payment_orders`

| column | type | null | key / constraint |
|---|---|---|---|
| user_id | CHAR(32) | no | FK → users.id |
| order_no | VARCHAR(40) | no | unique |
| kind | VARCHAR(20) | no |  |
| item_id | CHAR(32) | no |  |
| amount_idr | INTEGER | no |  |
| status | VARCHAR(12) | no |  |
| gateway | VARCHAR(20) | no |  |
| gateway_ref | VARCHAR(120) | yes |  |
| checkout_url | VARCHAR(500) | yes |  |
| idempotency_key | VARCHAR(120) | no |  |
| fulfilled_at | DATETIME | yes |  |
| expires_at | DATETIME | yes |  |
| meta | JSON | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(order_no); unique(user_id, idempotency_key)

## `plan_prices`

| column | type | null | key / constraint |
|---|---|---|---|
| plan_id | CHAR(32) | no | FK → plans.id |
| cycle | VARCHAR(10) | no |  |
| amount_idr | INTEGER | no |  |
| active | BOOLEAN | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `subscriptions`

| column | type | null | key / constraint |
|---|---|---|---|
| user_id | CHAR(32) | no | FK → users.id |
| plan_id | CHAR(32) | no | FK → plans.id |
| cycle | VARCHAR(10) | no |  |
| status | VARCHAR(12) | no |  |
| period_start | DATETIME | no |  |
| period_end | DATETIME | no |  |
| months_paid | INTEGER | no |  |
| cancel_at_period_end | BOOLEAN | no |  |
| grace_until | DATETIME | yes |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: index `uq_one_live_subscription` (user_id) unique

## `user_profiles`

| column | type | null | key / constraint |
|---|---|---|---|
| user_id | CHAR(32) | no | FK → users.id, unique |
| school_name | VARCHAR(200) | no |  |
| phone | VARCHAR(30) | no |  |
| province | VARCHAR(100) | no |  |
| education_levels | JSON | no |  |
| subjects | JSON | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(user_id)

## `user_roles`

| column | type | null | key / constraint |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| user_id | CHAR(32) | no | FK → users.id |
| role_id | CHAR(32) | no | FK → roles.id |

Constraints/indexes: unique(user_id, role_id)

## `user_sessions`

| column | type | null | key / constraint |
|---|---|---|---|
| user_id | CHAR(32) | no | FK → users.id |
| refresh_token_hash | VARCHAR(64) | no | unique |
| ip | VARCHAR(64) | yes |  |
| user_agent | VARCHAR(300) | yes |  |
| expires_at | DATETIME | no |  |
| revoked_at | DATETIME | yes |  |
| mfa_verified | BOOLEAN | no |  |
| rotated_from | CHAR(32) | yes |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(refresh_token_hash)

## `ai_model_pricing`

| column | type | null | key / constraint |
|---|---|---|---|
| model_id | CHAR(32) | no | FK → ai_models.id |
| version | INTEGER | no |  |
| input_per_1m | NUMERIC(14, 6) | no |  |
| output_per_1m | NUMERIC(14, 6) | no |  |
| cached_input_per_1m | NUMERIC(14, 6) | yes |  |
| currency | VARCHAR(3) | no |  |
| effective_from | DATETIME | no |  |
| effective_to | DATETIME | yes |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `ai_tool_model_assignments`

| column | type | null | key / constraint |
|---|---|---|---|
| tool_id | CHAR(32) | no | FK → ai_tools.id |
| model_id | CHAR(32) | no | FK → ai_models.id |
| priority | INTEGER | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(tool_id, model_id)

## `credit_buckets`

| column | type | null | key / constraint |
|---|---|---|---|
| wallet_id | CHAR(32) | no | FK → credit_wallets.id |
| type | VARCHAR(20) | no |  |
| source_ref | VARCHAR(100) | no |  |
| initial_amount | NUMERIC(12, 2) | no |  |
| expires_at | DATETIME | yes |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `credit_reservations`

| column | type | null | key / constraint |
|---|---|---|---|
| wallet_id | CHAR(32) | no | FK → credit_wallets.id |
| reference_id | VARCHAR(100) | no |  |
| amount_reserved | NUMERIC(12, 2) | no |  |
| amount_final | NUMERIC(12, 2) | yes |  |
| status | VARCHAR(20) | no |  |
| expires_at | DATETIME | no |  |
| idempotency_key | VARCHAR(200) | no | unique |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(idempotency_key)

## `invoices`

| column | type | null | key / constraint |
|---|---|---|---|
| number | VARCHAR(40) | no | unique |
| user_id | CHAR(32) | no | FK → users.id |
| order_id | CHAR(32) | no | FK → payment_orders.id, unique |
| description | VARCHAR(200) | no |  |
| amount_idr | INTEGER | no |  |
| status | VARCHAR(10) | no |  |
| issued_at | DATETIME | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(order_id); unique(number)

## `payments`

| column | type | null | key / constraint |
|---|---|---|---|
| order_id | CHAR(32) | no | FK → payment_orders.id |
| gateway | VARCHAR(20) | no |  |
| gateway_txn_id | VARCHAR(120) | yes |  |
| status | VARCHAR(12) | no |  |
| amount_idr | INTEGER | no |  |
| method | VARCHAR(40) | no |  |
| paid_at | DATETIME | yes |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(gateway, gateway_txn_id)

## `ai_requests`

| column | type | null | key / constraint |
|---|---|---|---|
| user_id | CHAR(32) | no | FK → users.id |
| tool_id | CHAR(32) | no | FK → ai_tools.id |
| prompt_version_id | CHAR(32) | yes | FK → ai_prompt_versions.id |
| model_id | CHAR(32) | yes | FK → ai_models.id |
| status | VARCHAR(15) | no |  |
| idempotency_key | VARCHAR(200) | no |  |
| input | JSON | no |  |
| output | JSON | yes |  |
| error_code | VARCHAR(50) | yes |  |
| reservation_id | CHAR(32) | yes | FK → credit_reservations.id |
| credits_reserved | NUMERIC(12, 2) | no |  |
| credits_charged | NUMERIC(12, 2) | yes |  |
| attempts | INTEGER | no |  |
| target_document_id | CHAR(32) | yes |  |
| started_at | DATETIME | yes |  |
| finished_at | DATETIME | yes |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(user_id, idempotency_key)

## `credit_allocations`

| column | type | null | key / constraint |
|---|---|---|---|
| source_type | VARCHAR(30) | no |  |
| source_id | VARCHAR(100) | no |  |
| bucket_id | CHAR(32) | no | FK → credit_buckets.id |
| amount | NUMERIC(12, 2) | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(source_type, source_id)

## `credit_reservation_items`

| column | type | null | key / constraint |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| reservation_id | CHAR(32) | no | FK → credit_reservations.id |
| bucket_id | CHAR(32) | no | FK → credit_buckets.id |
| amount | NUMERIC(12, 2) | no |  |
| seq | INTEGER | no |  |

## `credit_transactions`

| column | type | null | key / constraint |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| wallet_id | CHAR(32) | no | FK → credit_wallets.id |
| bucket_id | CHAR(32) | no | FK → credit_buckets.id |
| type | VARCHAR(30) | no |  |
| amount | NUMERIC(12, 2) | no |  |
| reference_type | VARCHAR(30) | no |  |
| reference_id | VARCHAR(100) | no |  |
| idempotency_key | VARCHAR(200) | no | unique |
| description | VARCHAR(300) | no |  |
| expires_at | DATETIME | yes |  |
| actor_id | CHAR(32) | yes |  |
| reverses_transaction_id | CHAR(32) | yes | FK → credit_transactions.id |
| created_at | DATETIME | no |  |

Constraints/indexes: unique(idempotency_key)

## `ai_cost_tracking`

| column | type | null | key / constraint |
|---|---|---|---|
| request_id | CHAR(32) | no | FK → ai_requests.id, unique |
| pricing_id | CHAR(32) | yes | FK → ai_model_pricing.id |
| fx_rate_id | CHAR(32) | yes | FK → fx_rates.id |
| cost_usd | NUMERIC(18, 8) | yes |  |
| cost_idr | NUMERIC(18, 4) | yes |  |
| is_estimate | BOOLEAN | no |  |
| credits_charged | NUMERIC(12, 2) | yes |  |
| charge_mode | VARCHAR(10) | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(request_id)

## `ai_usage`

| column | type | null | key / constraint |
|---|---|---|---|
| request_id | CHAR(32) | no | FK → ai_requests.id, unique |
| provider_id | CHAR(32) | yes | FK → ai_providers.id |
| model_id | CHAR(32) | yes | FK → ai_models.id |
| input_tokens | INTEGER | no |  |
| output_tokens | INTEGER | no |  |
| cached_tokens | INTEGER | no |  |
| provider_request_id | VARCHAR(100) | no |  |
| latency_ms | INTEGER | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Constraints/indexes: unique(request_id)

## `documents`

| column | type | null | key / constraint |
|---|---|---|---|
| user_id | CHAR(32) | no | FK → users.id |
| tool_slug | VARCHAR(80) | no |  |
| title | VARCHAR(200) | no |  |
| input | JSON | no |  |
| request_id | CHAR(32) | yes | FK → ai_requests.id |
| source_document_id | CHAR(32) | yes | FK → documents.id |
| is_deleted | BOOLEAN | no |  |
| id | CHAR(32) | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `document_download_logs`

| column | type | null | key / constraint |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| document_id | CHAR(32) | no | FK → documents.id |
| version_no | INTEGER | no |  |
| user_id | CHAR(32) | no | FK → users.id |
| format | VARCHAR(10) | no |  |
| created_at | DATETIME | no |  |

## `document_versions`

| column | type | null | key / constraint |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| document_id | CHAR(32) | no | FK → documents.id |
| version_no | INTEGER | no |  |
| content | JSON | no |  |
| note | VARCHAR(300) | no |  |
| source | VARCHAR(20) | no |  |
| created_at | DATETIME | no |  |

Constraints/indexes: unique(document_id, version_no)
