# SPEC 02 — System Architecture, Database, API

Covers deliverables 8–11, 23 of Part 23.

---

## 8. System architecture

```
                    Internet
                       │  HTTPS (TLS, HSTS)
                 ┌─────▼─────┐
                 │   Nginx   │  rate-limit, gzip, static cache, webhook allow-path
                 └──┬─────┬──┘
        /           │     │  /api
   ┌────▼─────┐      │  ┌──▼──────────────────────────────┐
   │ Next.js  │      │  │ FastAPI (modular monolith)      │
   │ (SSR/SPA)│      │  │ auth│users│institutions│subs    │
   └──────────┘      │  │ payments│credits│ai_engine      │
                     │  │ ai_providers│tools│documents    │
                     │  │ library│admin│analytics         │
                     │  └──┬────────┬────────┬────────────┘
                     │     │        │        │
              ┌──────▼──┐ ┌▼──────┐ ┌▼───────────────┐
              │Postgres │ │ Redis │ │ S3-compatible  │
              │ (PgBouncer)│ cache,│ │ object storage │
              └─────────┘ │ queue,│ └────────────────┘
                          │ locks │
                          └▲──────┘
                 ┌─────────┴───────────┐
                 │ Celery workers      │──► AI providers (OpenAI / Anthropic / Gemini)
                 │ (ai, docs, billing, │──► Midtrans / Xendit (outbound API)
                 │  default queues)    │──► SMTP / email API
                 │ Celery beat         │
                 └─────────────────────┘
   Monitoring: Prometheus + Grafana, Loki/Promtail logs, Sentry, uptime probe.
```

**Decisions**
- AD-1 Modular monolith; modules communicate via service interfaces (not each other's tables) so they can later be extracted. Cross-module imports only through `<module>/service.py` / `schemas.py`.
- AD-2 Sync API for fast reads; **AI generation and document export always via Celery**; client polls `GET /ai/requests/{id}` or subscribes to SSE `/ai/requests/{id}/events`.
- AD-3 PostgreSQL is the source of truth for money and credits. Redis is never authoritative for balances (cache + rate limit + locks only).
- AD-4 Credit balance = `SUM(ledger)` per bucket, computed in-transaction, with a **bucket row lock** (`SELECT … FOR UPDATE`) for writes. Optional materialized snapshot (`credit_buckets.snapshot_*`) is a cache that a nightly job verifies against the ledger; never edited manually.
- AD-5 Secrets: provider API keys encrypted at rest (envelope encryption, AES-256-GCM with a master key from env/secret manager, key id stored for rotation). Admin UI is write-only (shows last 4 chars).
- AD-6 Auth: short-lived JWT access token (15 min) in memory + rotating opaque refresh token in `HttpOnly; Secure; SameSite=Lax` cookie (hashed in `user_sessions`). CSRF double-submit token for cookie-authenticated mutating calls. **[U]** alternative: server sessions only.
- AD-7 Payments only activated by verified webhook (+ server-side status fetch from gateway before activation).
- AD-8 Time: all timestamps `timestamptz` UTC; money in integer minor units (IDR has no minor unit → integer Rupiah; USD costs stored as `numeric(18,8)`).
- AD-9 Credits are `numeric(12,2)` (supports 0.5-credit steps) — **[U]** or integers only.
- AD-10 Idempotency: `Idempotency-Key` header on all mutating money/credit/AI endpoints; stored in `idempotency_keys` (user, key, request hash, response).
- AD-11 Multi-tenancy: row-level scoping by `user_id` / `institution_id` in repository layer + Postgres RLS as defence-in-depth **[U]**.

### Backend layering (per module)
`router.py` (HTTP) → `service.py` (business rules, transactions) → `repository.py` (SQLAlchemy queries) ; `models.py`, `schemas.py` (Pydantic), `tasks.py` (Celery), `exceptions.py`.

### Folder structure (final)
```
ai-education-platform/
├─ frontend/ (Next.js 14+ App Router, TS, Tailwind)
│  ├─ app/ (public)/(auth)/app/admin
│  ├─ components/ (ui/, forms/, editor/, charts/, layout/)
│  ├─ hooks/  services/ (typed API client)  types/  styles/  lib/  tests/
├─ backend/
│  ├─ app/
│  │  ├─ core/ (config, db, security, crypto, logging, errors, deps, redis, rate_limit, idempotency)
│  │  ├─ auth/ users/ institutions/ subscriptions/ payments/ credits/
│  │  ├─ ai_engine/ ai_providers/ tools/ documents/ library/ admin/ analytics/
│  │  ├─ privacy/ (anonymizer, consent, retention)   notifications/  worker.py
│  ├─ migrations/ (Alembic)   tests/   main.py   pyproject.toml
├─ document_templates/ rpp/ modul_ajar/ soal/ administrasi/ laporan/
├─ infrastructure/ docker/ nginx/ monitoring/ backup/
├─ scripts/  docs/  tests/ (e2e, load, ai_eval)
├─ docker-compose.yml  docker-compose.prod.yml  .env.example  README.md  PROJECT_STATUS.md
```
Added vs. Part 18: `privacy/`, `notifications/` in backend; `tests/ai_eval` dataset; `docs/`. (Flagged as intentional additions.)

---

## 9. Database ERD (logical)

```
users 1─1 user_profiles          users 1─1 user_preferences
users 1─n user_roles n─1 roles   users 1─n user_sessions
users 1─1 credit_wallets 1─n credit_buckets 1─n credit_transactions
credit_reservations ─► credit_buckets(through reservation_items)
plans 1─n plan_features          plans 1─n subscriptions n─1 users|institutions
subscriptions 1─n subscription_invoices ─► payment_orders 1─n payments
payment_orders 1─n payment_webhooks(by gateway ref) ; payments 1─n refunds
ai_providers 1─n ai_provider_credentials ; ai_providers 1─n ai_models 1─n ai_model_pricing
ai_tools n─n ai_models via ai_tool_model_assignments
ai_tools 1─n ai_prompt_templates 1─n ai_prompt_versions
ai_requests ─► ai_tools, users, ai_models, ai_prompt_versions, credit_reservations, documents
ai_requests 1─n ai_request_logs ; 1─1 ai_usage ; 1─1 ai_cost_tracking
documents 1─n document_versions ; documents n─1 document_categories ; document_templates
documents 1─n document_download_logs ; document_shares
library_categories 1─n library_items 1─n library_files ; library_access_logs
institution_accounts 1─n institution_memberships n─1 users
ai_conversations 1─n ai_messages
audit_logs / admin_activity_logs ─► users(admin)
```
Full diagram to be exported as `docs/erd.mmd` (Mermaid) during Phase 2.

## 10. Detailed schema (key columns; every table also has `id uuid PK default gen_random_uuid()`, `created_at timestamptz`, `updated_at timestamptz` unless noted)

### Users
- **users**: email (citext, unique), password_hash (argon2id), email_verified_at, status (`active|suspended|deleted`), last_login_at, failed_login_count, locked_until, institution_id? , deleted_at.
- **user_profiles**: user_id (unique FK), full_name, phone, school_name, school_npsn?, education_levels[], subjects[], province, avatar_file_key.
- **user_preferences**: user_id unique, locale, default_curriculum, default_level, notification_prefs jsonb, anonymize_default bool.
- **roles**(code unique: `user|institution_admin|support|finance|content_admin|ai_admin|super_admin`), **user_roles**(user_id, role_id, unique pair), **permissions**(code), **role_permissions**.
- **user_sessions**: user_id, refresh_token_hash (unique), ip, user_agent, expires_at, revoked_at, rotated_from.
- **consents**: user_id, type (`terms|privacy|student_data`), version, granted_at, revoked_at.

### Subscriptions
- **plans**: code unique, name, description, is_public, sort, active; **plan_prices**: plan_id, billing_cycle (`monthly|annual`), amount_idr int, currency, active, effective_from.
- **plan_features**: plan_id, feature_key (e.g. `credits_monthly`, `tool_access:<category|slug>`, `export_formats`, `library_tier`, `storage_mb`, `priority_queue`, `max_questions`, `daily_request_limit`), value jsonb.
- **subscriptions**: owner_type (`user|institution`), owner_id, plan_id, plan_price_id, status (`pending|active|past_due|grace|canceled|expired`), current_period_start/end, cancel_at_period_end, canceled_at, grace_until, renewal_attempts, pending_change jsonb (scheduled downgrade). Partial unique index: one non-terminal subscription per owner.
- **subscription_invoices**: subscription_id, number (unique, sequential per year), order_id, amount, tax_amount **[U: PPN handling]**, status, period_start/end, issued_at, paid_at, pdf_file_key.
- **subscription_history**: subscription_id, event, from_plan, to_plan, actor, data jsonb (append-only).
- **promotions**: code unique, type (`percent|fixed|bonus_credits`), value, starts/ends, max_redemptions, applies_to; **promotion_redemptions**.

### Payments
- **payment_orders**: user_id, order_no (unique), kind (`subscription|credit_package`), item_ref, amount_idr, currency, status (`created|pending|paid|failed|expired|canceled|refunded`), gateway, gateway_order_ref, idempotency_key (unique per user), expires_at, metadata, fulfilled_at (set once ⇒ prevents double fulfilment).
- **payments**: order_id, gateway, gateway_txn_id (unique with gateway), method, status, amount, fee_amount, raw_status, paid_at, verified_at.
- **payment_webhooks**: gateway, event_id (unique with gateway), signature_valid bool, headers, payload jsonb, received_at, processed_at, process_status, error. (Append-only; raw body retained.)
- **refunds**: payment_id, amount, reason, status, gateway_refund_id, initiated_by, credits_clawback jsonb.
- **payment_reconciliation**: run_at, gateway, window, matched_count, mismatches jsonb, resolved_by.

### AI providers / engine
- **ai_providers**: code (`openai|anthropic|google`), name, adapter_class, status (`enabled|disabled`), base_url?, priority, monthly_spend_limit_usd, daily_spend_limit_usd, health.
- **ai_provider_credentials**: provider_id, label, secret_ciphertext, key_id, last4, status, rotated_at, created_by. *No read-back endpoint.*
- **ai_models**: provider_id, model_code, display_name, capabilities jsonb (json_mode, streaming, context_window, max_output), status, is_default, per_model_daily/monthly_limit_usd.
- **ai_model_pricing**: model_id, version, input_per_1m, output_per_1m, cached_input_per_1m null, extra_charges jsonb, currency (`USD`), effective_from, effective_to, created_by. Exclusion constraint: no overlapping ranges per model.
- **fx_rates**: base, quote, rate, effective_from (USD→IDR; source: manual/ API **[U]**).
- **ai_tool_model_assignments**: tool_id, model_id, role (`primary|fallback`), priority, plan_tier null (e.g. Ultimate → advanced model).
- **ai_tools**: slug unique, name, category, description, input_schema jsonb, output_schema jsonb, active_prompt_version_id, default_max_output_tokens, access (`min_plan` / plan list), credit_pricing_id, is_active, is_archived, sort, icon.
- **ai_prompt_templates**: tool_id, name; **ai_prompt_versions**: template_id, version int, system_prompt, user_prompt_template (Jinja sandbox), few_shot jsonb, params jsonb (temperature…), status (`draft|published|archived`), published_by/at, change_note. Immutable once published.
- **ai_requests**: user_id, tool_id, prompt_version_id, model_id, provider_id, status (`queued|reserved|running|validating|rendering|succeeded|failed|refunded|canceled`), idempotency_key (unique w/ user), input jsonb (**anonymized form stored; see privacy**), input_hash, output jsonb, error_code, attempts, queued_at/started_at/finished_at, reservation_id, document_id, parent_request_id (regeneration).
- **ai_request_logs**: request_id, level, step, message, data (no secrets, no raw student data).
- **ai_usage**: request_id (unique), provider_request_id, input_tokens, output_tokens, cached_tokens, reasoning_tokens, provider_reported jsonb, latency_ms.
- **ai_cost_tracking**: request_id (unique), pricing_id, fx_rate_id, cost_usd, cost_idr, is_estimate bool default true, reconciled bool, invoice_ref, credits_charged, charge_mode.

### Credits
- **credit_wallets**: user_id | institution_id (one of, check constraint), status, currency_unit.
- **credit_buckets**: wallet_id, type (`subscription|bonus|purchased`), source_ref (subscription period / promo / package purchase), initial_amount, expires_at, priority_class, created_at. **No editable balance column**; balance view `v_bucket_balance = SUM(credit_transactions.amount)`.
- **credit_transactions** (append-only; UPDATE/DELETE blocked by trigger): wallet_id, bucket_id, type enum {`subscription_allocation, usage_reservation, usage_deduction, reservation_settlement, refund, bonus, promotional, purchase, admin_adjustment, expiration, reservation_release`}, amount (signed numeric), reference_type, reference_id, idempotency_key (unique), description, expires_at, actor_id, created_at, reverses_transaction_id.
- **credit_reservations**: wallet_id, request_id, amount_reserved, amount_final null, status (`active|settled|released|expired`), expires_at (TTL sweeper), idempotency_key unique; **credit_reservation_items**: reservation_id, bucket_id, amount (for settlement/refund per bucket).
- **credit_packages**: name, credits, price_idr, bonus_credits, bonus_expiry_days, purchased_expiry_days null, active, sort.
- **credit_package_purchases**: user_id, package_id, order_id unique, status, allocated_at.
- **credit_allocations**: owner, source_type (`subscription_period|package|promo|admin|referral`), source_id **UNIQUE(source_type, source_id)** ← prevents double allocation per billing event, bucket_id, amount.
- **credit_pricing_rules**: tool_id (null=global), mode (`fixed|dynamic|hybrid`), fixed_credits, base_credits, margin_pct, processing_fee_idr, credit_value_idr, rounding_step, rounding_mode, min_credits, max_credits, model_multiplier jsonb, complexity_rules jsonb, effective_from, version.
- **credit_settings** (singleton row set): consumption_priority (ordered list), reservation_ttl_seconds, estimate_safety_factor, regen_discount_pct.
- **usage_limits**: scope (`global|plan|user|tool`), scope_id, period (`minute|day|month`), max_requests, max_credits, max_tokens.

### Documents / Library
- **documents**: user_id, tool_id?, request_id?, title, kind, status, current_version_id, category_id, is_deleted, source_document_id.
- **document_versions**: document_id, version_no, content jsonb (structured), content_hash, created_by, note, file_keys jsonb (exports cache).
- **document_templates**: kind, name, curriculum?, version, definition jsonb (sections), docx_template_key, active, reviewed_by/at (**reviewer sign-off field**).
- **document_categories**; **document_download_logs**(document_id, version_id, user_id, format, ip, at); **document_shares**(document_id, token_hash, expires_at, revoked_at, permission).
- **library_categories**(parent_id, slug); **library_items**(title, desc, type, level, subject, tags[], access_tier, is_sample, status, search_vector tsvector); **library_files**(item_id, version_no, storage_key, mime, size, checksum, is_current, preview_key); **library_access_logs**.
- **question_bank_items**: user_id, subject, level, topic, type, bloom, difficulty, body jsonb, tags[], source_request_id.
- **class_rosters**/**roster_students**: user_id, class_name, student alias, **no real names unless user opts in; alias↔name mapping stored encrypted client-side-key [U]**.
- **curriculum_references**: curriculum, level, phase, subject, element/CP text, source_citation, version, verified_by, verified_at, is_active (admin-managed; AI context built from here).

### Admin & misc
- **admin_users** (extends users: mfa_secret enc, last_mfa_at), **admin_activity_logs**, **audit_logs**(actor, action, entity_type, entity_id, before jsonb, after jsonb, ip, request_id; append-only), **system_settings**(key, value jsonb, is_secret), **announcements**, **support_tickets**/**support_messages**, **feature_flags**(key, enabled, rules jsonb), **notifications**(user_id, type, title, body, read_at, channel), **feedback**(user, request_id, rating, comment), **ai_conversations**(user_id, title, summary, token_count, deleted_at), **ai_messages**(conversation_id, role, content, tokens, request_id), **institution_accounts**(name, npsn?, status, seat_limit, wallet_id), **institution_memberships**(institution_id, user_id, role, status, seat), **idempotency_keys**, **provider_alerts**, **outbox_events** (transactional outbox for notifications/emails).

### Index strategy
- FK indexes on every FK. Unique: users.email, plan.code, ai_tools.slug, order_no, (gateway,event_id), (gateway,gateway_txn_id), credit_transactions.idempotency_key, credit_allocations(source_type,source_id).
- Hot paths: `credit_transactions(bucket_id, created_at)`, `(wallet_id, created_at desc)`, `ai_requests(user_id, created_at desc)`, `(status, queued_at)` partial for non-terminal, `ai_cost_tracking(created_at)` BRIN, `audit_logs(created_at)` BRIN + `(entity_type, entity_id)`.
- Search: GIN on `library_items.search_vector` + trigram on titles; tags GIN.
- Partitioning **[U]**: `ai_request_logs`, `credit_transactions`, `audit_logs` monthly when > ~50M rows.

### Data integrity rules
1. Ledger rows immutable (trigger `RAISE` on UPDATE/DELETE); corrections = compensating rows.
2. `CHECK (bucket balance >= 0)` enforced in service under row lock + deferred constraint trigger on insert of negative amounts.
3. One active reservation per `request_id`; settlement idempotent via `idempotency_key`.
4. `payment_orders.fulfilled_at` set with `UPDATE … WHERE fulfilled_at IS NULL RETURNING` ⇒ exactly-once fulfilment.
5. Pricing/period no-overlap exclusion constraints; published prompt versions immutable.
6. All user-owned queries filter `user_id`; admin access via explicit permission checks.
7. Soft delete for user content; hard-purge job per retention policy.

---

## 11. API specification (REST, prefix `/api/v1`, JSON, OpenAPI auto-generated; errors `{error:{code,message,details,request_id}}`; pagination `?page&page_size` or cursor)

### Auth / users
`POST /auth/register` · `POST /auth/verify-email` · `POST /auth/login` · `POST /auth/refresh` · `POST /auth/logout` · `POST /auth/forgot-password` · `POST /auth/reset-password` · `POST /auth/mfa/enroll|verify` (admin) · `GET/PATCH /me` · `GET/PATCH /me/preferences` · `GET /me/sessions` · `DELETE /me/sessions/{id}` · `POST /me/consents` · `POST /me/delete-request` · `GET /me/export`

### Tools & AI
`GET /tools` (filter category, search; includes access + credit cost) · `GET /tools/{slug}` (schema) · `POST /tools/{slug}/estimate` → `{estimated_credits, min, max, mode}` · `POST /tools/{slug}/generate` (Idempotency-Key) → `202 {request_id}` · `GET /ai/requests/{id}` · `GET /ai/requests/{id}/events` (SSE) · `POST /ai/requests/{id}/cancel` · `POST /ai/requests/{id}/regenerate` · `GET /ai/history`
Assistant: `GET/POST /assistant/conversations` · `GET/PATCH/DELETE /assistant/conversations/{id}` · `POST /assistant/conversations/{id}/messages` (SSE stream) · `POST /assistant/messages/{id}/to-document`

### Documents
`GET /documents` · `GET /documents/{id}` · `PATCH /documents/{id}` (save → new version) · `POST /documents/{id}/duplicate` · `DELETE /documents/{id}` · `GET /documents/{id}/versions` · `POST /documents/{id}/versions/{v}/restore` · `POST /documents/{id}/export {format}` → `202` job · `GET /documents/{id}/download?format&version` (signed URL) · `POST/DELETE /documents/{id}/share`
Question bank: `GET/POST/PATCH/DELETE /question-bank/items` · Rosters: `/rosters…`

### Library
`GET /library/items` (q, category, tags, level, subject, tier) · `GET /library/items/{id}` · `GET /library/items/{id}/preview` · `POST /library/items/{id}/download` (access check → signed URL) · `GET /library/downloads`

### Credits & billing
`GET /credits/summary` · `GET /credits/ledger` · `GET /credits/usage?group=tool|day` · `GET /credits/packages` · `POST /credits/packages/{id}/purchase` (Idempotency-Key) → order + checkout
`GET /plans` · `GET /subscription` · `POST /subscription/checkout` · `POST /subscription/change` · `POST /subscription/cancel` · `POST /subscription/resume` · `GET /invoices` · `GET /invoices/{id}/pdf` · `GET /payments` · `GET /payments/orders/{id}` (status poll — read-only, informational)
Webhooks (no auth, signature-verified): `POST /webhooks/midtrans` · `POST /webhooks/xendit`

### Institutions
`GET/PATCH /institution` · `GET/POST/DELETE /institution/members` · `GET /institution/usage` · `POST /institution/credits/allocate`

### Misc
`GET /notifications` · `POST /notifications/{id}/read` · `POST /feedback` · `GET /announcements` · `POST /support/tickets` · `GET /health` · `GET /ready`

### Admin (`/admin/…`, RBAC permission per route, all writes audit-logged)
- Users: `GET /users`, `GET/PATCH /users/{id}`, `POST /users/{id}/suspend|activate`, `PUT /users/{id}/roles`, `GET /users/{id}/activity`
- Tools: CRUD `/tools`, `POST /tools/{id}/archive`, `PUT /tools/{id}/assignments`, `PUT /tools/{id}/credit-rule`
- Prompts: `GET/POST /tools/{id}/prompts`, `POST /prompts/{versionId}/test`, `POST /prompts/compare`, `POST /prompts/{versionId}/publish`, `POST /tools/{id}/prompts/rollback`
- Providers: CRUD `/providers`, `PUT /providers/{id}/credentials` (write-only), `POST /providers/{id}/test`, CRUD `/models`, `POST /models/{id}/pricing`, `GET /providers/usage`, `GET /providers/errors`, `PUT /providers/{id}/limits`, `PUT/POST /fx-rates`
- Credits: `GET /credits/dashboard`, `GET/PUT /credits/settings`, CRUD `/credits/packages`, `PUT /plans/{id}/allocation`, `POST /credits/grant`, `POST /credits/adjust` (reason required), `GET /credits/ledger?user`, `GET /credits/expiring`, `PUT /usage-limits`
- Plans/Subs: CRUD `/plans`, `/plans/{id}/prices`, `/promotions`, `GET /subscriptions`, `POST /subscriptions/{id}/…`
- Payments: `GET /orders`, `GET /payments`, `GET /webhooks/events`, `POST /webhooks/events/{id}/replay`, `POST /payments/{id}/refund`, `POST /reconciliation/run`, `GET /reconciliation`
- Library: CRUD `/library/items`, `POST /library/items/{id}/files` (versioned), `POST /library/items/{id}/archive`
- Finance: `GET /finance/summary|by-tool|by-model|by-user|funnel|churn` (every figure tagged `verified|estimated`)
- System: `/settings`, `/announcements`, `/support/tickets`, `/feature-flags`, `/audit-logs`, `/errors`, `/queues`, `/curriculum-references`, `/institutions`

Contract notes: all money endpoints require Idempotency-Key; 402 for insufficient credits, 403 plan/permission, 409 duplicate, 422 validation, 429 rate limit, 503 provider unavailable (with auto-refund). OpenAPI exported into `API_DOCUMENTATION.md`.
