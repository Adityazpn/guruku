# SPEC 03 — AI Engine, Credits, Billing, Payments, Documents, Security, Delivery

Covers deliverables 12–28 of Part 23.

---

## 12. AI Engine architecture

```
Router ► ToolService.validate(input_schema) ► Entitlement (plan, tool access, limits)
      ► CreditService.reserve ► enqueue Celery(ai.run_request)
Worker: load request ► Privacy.anonymize ► PromptBuilder(tool, version, curriculum refs)
      ► ModelSelector(tool→assignment→provider health→spend limits)
      ► ProviderAdapter.generate() ► OutputValidator(JSON schema) ► [repair-retry ×1]
      ► Domain post-checks (e.g. question count, answer key present, no diagnosis terms)
      ► Privacy.deanonymize ► Document create (version 1) ► export job (optional)
      ► UsageRecorder(tokens, cost) ► CreditService.settle ► notify ► status=succeeded
```

**Provider adapter interface** (`ai_providers/base.py`)
```python
class LLMProvider(Protocol):
    code: str
    async def generate(self, req: LLMRequest) -> LLMResponse      # messages, json_schema, max_tokens, temperature, timeout
    async def stream(self, req) -> AsyncIterator[LLMChunk]
    async def health(self) -> ProviderHealth
@dataclass LLMResponse: text, parsed_json, usage(input,output,cached,reasoning), provider_request_id, finish_reason, raw_meta
```
Adapters: `OpenAIAdapter` (primary), `AnthropicAdapter`, `GeminiAdapter`; registry keyed by `ai_providers.code`. Normalized errors: `ProviderTimeout, ProviderRateLimited(retry_after), ProviderAuthError, ProviderQuotaExhausted, ProviderBadRequest, ProviderContentFiltered, ProviderUnavailable, MalformedOutput`.
**Exact model IDs, SDK parameters and structured-output mechanics are not hardcoded in this spec; they are loaded from `ai_models` and verified against each provider's current docs at implementation time.** [E]

**Failure handling matrix**

| Failure | Behaviour | Credits |
|---|---|---|
| Timeout / 5xx | retry ≤2 with exponential backoff + jitter, then fallback model/provider if assigned | release on final fail |
| 429 rate limit | honour retry_after; queue delay; circuit-breaker per provider | release on final fail |
| Auth invalid / billing exhausted | mark credential `invalid`, alert admins, fail over to fallback provider; request retried once on fallback | release if none |
| Malformed JSON | one repair prompt (counts to cost); then fail | release (or settle only if partial value delivered – never) |
| Schema valid but domain check fails | regenerate once | same |
| Document render fails | retry render ×2 (AI output kept in `ai_requests.output`; user can re-export free) | settle AI (value delivered), no double charge |
| Duplicate submit | idempotency key returns original request | none |
| Worker crash mid-run | request heartbeat; sweeper requeues once; reservation TTL sweeper releases stale | auto |
| Partial failure (multi-part tool) | per-part status; user charged only for completed parts (hybrid pricing) | proportional |

**Prompt assembly**: `system` (role, tone, safety, language, output JSON contract) + `curriculum_context` (from `curriculum_references`, with citations, version) + `user_task` (Jinja-sandboxed template rendering validated inputs; user free-text is delimited and treated as data → prompt-injection mitigation) + optional few-shot. Prompt versions immutable; each `ai_requests` stores `prompt_version_id`.

**Model selection order**: tool+plan assignment → provider enabled & healthy → per-model/provider spend limit not exceeded → priority. Admin kill-switch per tool/provider.

## 13. AI Provider Management architecture
Admin UI tabs: Providers · Credentials · Models · Pricing · Assignments · Limits · Usage & Cost · Errors · Health.
- Credentials: stored encrypted (`ai_provider_credentials`), decrypted only inside backend process memory at call time; env var fallback `OPENAI_API_KEY` etc. for bootstrap; never in API responses/logs (log redaction filter + secret scanner in CI).
- "Test connection" performs a minimal call, records result.
- Pricing records are versioned rows with effective dates; creating a new row closes the previous (`effective_to`). Cost calc picks the row effective at `request.started_at`.
- Limits: daily/monthly USD per provider and per model; at 80% alert, at 100% provider/model auto-disabled for non-priority tools (configurable), fallback engaged.
- Usage/Cost views: tokens and cost by provider, model, tool, user, day; error rates; latency percentiles.
- Seed data: provider rows with **no credentials and no prices** — pricing must be entered by admin from the provider's official pricing page. [E]

## 14. AI API billing architecture (provider cost vs customer credits)
Two separate domains that never share tables for balances:
1. **API cost domain** (`ai_usage`, `ai_cost_tracking`, `ai_model_pricing`, `fx_rates`): what the owner owes providers.
2. **Credit domain** (ledger): what customers consume.
Link only via `ai_cost_tracking.credits_charged` for margin analytics.

Cost per request: `cost_usd = (in_tokens − cached)·p_in/1e6 + cached·p_cached/1e6 + out_tokens·p_out/1e6 + extra_charges` using provider-reported usage; `cost_idr = cost_usd · fx(USD→IDR at request time)`. Stored with `is_estimate = true` until reconciled.
**Reconciliation** (daily job + manual import): admin uploads/pulls provider usage report (where API available) → compares per day/model → difference stored in `payment_reconciliation`-style table `provider_reconciliation`; variance > threshold alerts; finance dashboard shows "verified" only for reconciled periods. ChatGPT Plus / Claude Pro / Gemini consumer plans are explicitly **not** assumed to include API balance; docs/DEPLOYMENT.md will instruct creating separate developer-platform billing accounts and top-ups. [E]

## 15. Credit Management architecture
**Buckets**: `subscription` (expires at period end by default; no rollover by default — configurable `rollover_pct`), `bonus` (promo/referral/admin; expires N days), `purchased` (expires after N days or never — **[U]** legal/consumer review in Indonesia on credit expiry disclosure).
**Balance** of a bucket = Σ `credit_transactions.amount` for bucket (reservations are negative "hold" rows, settlements/releases positive rows ⇒ available balance always derivable).
**Consumption priority**: configurable ordered classes, default `[subscription, bonus, purchased]`; inside a class order by `expires_at ASC NULLS LAST`, then `created_at`. A request may span buckets; per-bucket amounts recorded in `credit_reservation_items`.
**Pricing rules (`credit_pricing_rules`)** per tool, versioned:
- Fixed: `credits = fixed_credits`.
- Dynamic: `credits = clamp( round_step( ((api_cost_idr + processing_fee_idr) × (1 + margin_pct)) / credit_value_idr ), min, max )` · `credit_value_idr` is the admin's internal nominal value of 1 credit (not a provider unit).
- Hybrid: `credits = base_credits + dynamic_variable`, then clamp.
- Model multiplier / complexity (e.g., #questions, #pages) adjust the *estimate* and may add a surcharge defined in rule JSON.
- **Customer-protection rule**: final charge ≤ reserved amount ≤ `max_credits` shown in the pre-generation estimate range; users are never charged above the max displayed.
**Limits**: per user/plan/tool per minute/day/month (requests, credits, tokens) in `usage_limits`.
**Expiry job** (hourly): for expired buckets, writes `expiration` transaction for the remaining balance (never edits history). Pre-expiry notifications at 7/1 days.
**Admin adjustments**: `admin_adjustment` ledger rows with mandatory reason + actor; reversal via compensating entry referencing `reverses_transaction_id`.

## 16. Credit calculation examples
**Illustrative inputs only — NOT real provider prices.** Assume model price $1.00 / 1M input, $4.00 / 1M output (admin-entered), FX Rp16,500/USD, processing fee Rp20, `credit_value_idr` = Rp250, rounding up to 0.5.

| Case | Calculation | Result |
|---|---|---|
| Fixed – RPP | rule fixed = 3 | **3.0 credits** |
| Dynamic – Soal HOTS (3,000 in / 4,000 out), margin 300%, min 2, max 20 | cost = 3,000×1/1e6 + 4,000×4/1e6 = $0.019 → Rp313.5; +20 = 333.5; ×(1+3.0)=1,334; ÷250 = 5.336 → round-up 0.5 | **5.5 credits** |
| Hybrid – Modul Ajar (6,000 in / 9,000 out), base 3, margin 150%, clamp 4–15 | cost = $0.006+$0.036 = $0.042 → Rp693; +20 = 713; ×2.5 = 1,782.5; ÷250 = 7.13 → 7.5; total 3+7.5 | **10.5 credits** |
| Clamp | dynamic result 1.2, min 2 | **2.0 credits** |

**Margin sanity (illustrative)** for the 5.5-credit case: API cost+processing Rp333.5. Revenue per credit if bought via Professional (Rp99,000/300) = Rp330 → Rp1,815 → gross margin ≈ **81.6%** before payment fees/infra; via Ultimate (Rp149,000/600 ≈ Rp248.3) → Rp1,366 → ≈ **75.6%**. Real margins depend on actual prices, FX, payment fees (**[E]** gateway fee schedule), PPN, unused-credit breakage. Admin dashboard recomputes with live data.
Note: example plan prices imply different realized Rp/credit per plan (Rp490 / 330 / 248) — **[U]** whether `credit_value_idr` should be a single value or per-plan.

**Multi-bucket reserve/settle example.** Balances: subscription 4.0 (expires in 5 days), bonus 10.0, purchased 20. Estimate 5.5, safety ×1.3 → reserve 7.15→**7.5**: take 4.0 subscription + 3.5 bonus. Actual charge 5.5: keep 4.0 subscription + 1.5 bonus; release 2.0 back to bonus. Ledger rows: `usage_reservation −4.0 (sub)`, `usage_reservation −3.5 (bonus)`, then `reservation_settlement` (links) + `refund +2.0 (bonus)`; final: sub 0, bonus 8.5, purchased 20.

## 17. Credit reservation workflow (atomic)
```
BEGIN
 1. idempotency check (credit_reservations.idempotency_key) → return existing if present
 2. SELECT wallet buckets WHERE usable (not expired, balance>0) ORDER BY priority FOR UPDATE   -- row locks
 3. balances = SUM(ledger) per bucket (inside lock)
 4. IF Σ available < amount → ROLLBACK, 402 InsufficientCredits
 5. allocate across buckets per priority; INSERT reservation(status=active, expires_at=now+ttl) + items
 6. INSERT ledger rows type=usage_reservation (negative)
COMMIT → enqueue job

Settle(final):  BEGIN; lock reservation FOR UPDATE; if status!=active → return (idempotent)
   final = min(final, reserved); per-bucket: keep first, release the rest (positive `refund` rows)
   write `usage_deduction` markers + `reservation_settlement`; status=settled; COMMIT
Release(fail): lock; if active → positive rows for all items; status=released
Sweeper (every min): reservations past TTL & request not running → Release; running but stale heartbeat → requeue/Release
```
Safeguards: unique idempotency keys per ledger row; status-guarded transitions (`UPDATE … WHERE status='active'`); DB trigger prevents negative bucket sums; concurrency test: N parallel reserves against small balance must never overspend (Part 19).

## 18. Subscription architecture
- State machine: `pending → active → (past_due → grace → expired) | canceled(at period end) → expired`. Transitions only from verified payment events or scheduled jobs.
- Plans / prices / features are rows; Admin changes create new `plan_prices` (existing subscribers keep price until renewal unless admin migrates — **[U]**).
- Allocation: on verified invoice payment ⇒ create `credit_allocations(source_type='subscription_period', source_id=invoice_id)` UNIQUE ⇒ exactly one allocation per billing event. Bucket expires `current_period_end` (+ optional rollover).
- Upgrade: immediate, prorated charge (**[U]** proration policy), delta credits allocated after payment. Downgrade: scheduled at period end (`pending_change`). Cancel: `cancel_at_period_end`. Resume before end allowed.
- Renewal: **[U]** gateways differ on recurring/tokenized charges (Midtrans subscription / card tokens; Xendit recurring). MVP default: **invoice-based renewal** — T-7/T-3/T-1 reminders with a payment link; unpaid → `past_due` → `grace` (configurable days) → `expired` (tool access reduced to free tier; library/premium locked; data retained). Auto-debit added when gateway capabilities verified [E].
- Annual plan: priced as admin sets; monthly credit allocation drip (12 monthly allocations) vs. upfront **[U]**.
- Invoices: sequential number, PDF to S3, history endpoint. Tax/PPN & e-Faktur requirements **[U/E]** need accountant input.
- Institutional: custom price, seat licences, shared wallet, member usage attribution, school admin console, invoice/bank-transfer manual-payment path with admin "mark as paid" (audited).

## 19. Payment workflow
1. `POST /subscription/checkout` or `/credits/packages/{id}/purchase` (Idempotency-Key) → create `payment_orders(status=created)` with server-computed amount (client never sends price).
2. Backend calls gateway adapter (`create_checkout`) → returns redirect/snap token; order → `pending`.
3. User pays on gateway.
4. Gateway → `POST /webhooks/{gateway}`.
5. Handler: store raw body in `payment_webhooks` (always) → verify signature (Midtrans: SHA-512 of order_id+status_code+gross_amount+server_key; Xendit: callback token header / signature — **exact verification per current official docs [E]**) → reject if invalid (401, flagged).
6. Dedupe on `(gateway,event_id)`; **re-fetch transaction status from gateway API** and compare amount/currency/order → only then proceed.
7. In one DB transaction: lock order; if `fulfilled_at` null → mark paid, create `payments`, fulfil (activate subscription + allocate credits / allocate purchased credits), create invoice, enqueue notification; set `fulfilled_at`.
8. Failures/expiry/denied → order `failed|expired`, subscription `past_due` if renewal.
9. Refund: admin initiates → gateway refund API → on confirmation: `refunds` row, credits clawback via negative `admin_adjustment`/`refund` entries (cannot go below 0; remainder flagged as debt to admin review), subscription adjusted.
10. Reconciliation job (daily): pull gateway settlement list, match orders/payments/amount/fees; mismatches → admin queue.
Frontend return URLs show *"Memverifikasi pembayaran…"* and poll order status; **never** grant access from redirect params.
No gateway credentials in repo: `.env.example` placeholders (`MIDTRANS_SERVER_KEY=`, `XENDIT_SECRET_KEY=`, …). Sandbox mode toggle. [E] Merchant accounts + KYB approval needed.

## 20. Additional credit purchase workflow
Select package (server-side price) → order(kind=`credit_package`) → checkout → verified webhook → `credit_package_purchases` paid → `credit_allocations(source_type='package', source_id=purchase_id)` UNIQUE → new `purchased` bucket (+ separate `bonus` bucket for promo bonus with its own expiry) → ledger rows `purchase` / `bonus` → invoice/receipt → notification. Purchased and subscription buckets are never merged.

## 21. Document generation architecture
- Source of truth: **structured JSON** (`document_versions.content`) validated by the tool's output schema; editor edits that JSON (section/field level), not raw DOCX.
- Renderers (`documents/renderers/`): `docx_renderer` (python-docx + template DOCX with styles, header/footer, page numbers via field codes, A4, margins 2.54 cm default / 3-cm-left variants per template), `pdf_renderer` (ReportLab Platypus; embedded Unicode TTF e.g. Inter/Noto Sans to ensure Indonesian characters), `xlsx_renderer` (OpenPyXL: PROTA/PROMES, score analysis, attendance), `pptx_renderer` (python-pptx slide masters), `txt_renderer`.
- Templates: `document_templates/<kind>/…` + DB definitions (versioned, with reviewer sign-off). Landscape sections supported for PROTA/PROMES tables; long tables repeat header rows, no row splitting where possible.
- "No truncated content" safeguards: output token cap vs. required section checklist; validator verifies every required section is non-empty; `finish_reason == length` ⇒ auto-continuation or fail+refund; render test asserts last section present in output.
- Export runs as Celery job (`docs` queue) → file to S3 → signed URL (5-min TTL). Exports cached by `(version_id, format, template_version)`.
- PDF from DOCX: native ReportLab render (not LibreOffice) in MVP; fidelity parity limited — **[U]** LibreOffice headless conversion if exact DOCX look is required.
- Preview in browser: HTML renderer from the same JSON (WYSIWYG-lite).
- Plan gating: Starter TXT/DOCX? **[U]** (spec examples: Pro adds DOCX+PDF, Ultimate all) enforced via `plan_features.export_formats`.

## 22. Security & privacy architecture
**AuthN/Z**: Argon2id (m=64MB,t=3,p=4 tunable), breached-password check **[U]**, lockout + exponential delay, email verification, MFA(TOTP) mandatory for admin roles, refresh rotation + reuse detection, RBAC (roles→permissions; checked via FastAPI dependencies; tests enumerate every route against role matrix), object-level checks on every `{id}`.
**Web**: strict CSP, HSTS, `X-Content-Type-Options`, frame-ancestors none, output escaping in React; user HTML never `dangerouslySetInnerHTML` (sanitize with allowlist if rich text), CSRF tokens for cookie-auth writes, CORS allowlist, SQLAlchemy parametrization only, Pydantic validation, upload validation (type sniffing, size caps, AV scan hook **[U]**), no path-based file access (S3 keys random UUID), signed URLs short TTL.
**Rate limiting**: Redis token bucket per IP/user/route (auth strict; AI per plan) + Nginx limit_req.
**Secrets**: envelope-encrypted provider keys; env-based master key; log redaction; pre-commit & CI secret scanning; separate sandbox/prod keys; key rotation runbook.
**Audit**: append-only `audit_logs` for all admin writes, credit adjustments, role changes, credential changes, login events; admin routes require reason for sensitive ops.
**Student data protection (UU PDP No. 27/2022; children's data)** — compliance must be confirmed by Indonesian legal counsel [E]; spec implements engineering controls:
1. *Minimization*: forms accept aliases/codes ("Siswa A", NIS-less); roster stores alias; real names optional and encrypted.
2. *Anonymizer*: before provider call, regex + dictionary (+ optional NER) replaces names, NIK/NISN/NIS, phone, email, address, parent names with tokens (`[SISWA_1]`); mapping kept only in the request context/encrypted in DB with short TTL; de-anonymized only in the response shown to the owner. Residual-risk warning in UI; provider calls use zero-retention/no-training API settings where available [E].
3. *Consent*: teacher confirms authority/consent basis for any student-related tool use (versioned `consents`); school-level consent for institutions.
4. *Retention*: configurable (default: student-analysis inputs purged after N days, outputs kept until user deletes); deletion requests executed ≤ [U] days; hard-purge job + S3 object deletion; export-my-data endpoint.
5. *Advisory-only*: every Module D output includes fixed disclaimer; prompts and output validators block diagnostic terms; crisis-keyword escalation message.
6. *Access*: student-related docs flagged `sensitive`; never in library/shares by default; shares disabled for sensitive docs.
7. Logs never contain raw prompts for sensitive tools (only hashes + sizes) unless admin enables debug with expiry.
**Backups & DR**: nightly `pg_dump`/WAL archiving (PITR) to off-site bucket, encrypted, 30-day retention, quarterly restore test; S3 versioning; RPO ≤ 24h (PITR ⇒ minutes), RTO ≤ 4h targets **[U]**.

## 23. Project folder structure
See SPEC_02 §8 "Folder structure (final)".

## 24. Testing strategy
| Layer | Tooling | Scope / gate |
|---|---|---|
| Unit | pytest | pricing math (golden cases above), anonymizer, schema validators, state machines |
| Integration | pytest + Testcontainers (Postgres, Redis, MinIO) | repos, Alembic up/down, ledger triggers, RBAC matrix |
| Concurrency | pytest + asyncio/threads | 50 parallel reserves on small balance ⇒ no negative; double settle/refund ⇒ single effect; duplicate webhook ⇒ single allocation |
| Provider | contract tests with recorded fixtures + fake provider; optional live smoke (needs real keys, opt-in) | error mapping, retries, fallback |
| Payments | signed sandbox-style fixtures; tampered signature, wrong amount, replay | webhook security |
| Documents | generate every tool's sample → open with python-docx/pdf text extraction; assert sections, Indonesian chars, page numbers, no truncation | per template |
| Frontend | Vitest + Testing Library; Playwright E2E (viewport 360/768/1280) | forms validation, nav, preview, download, subscription, credit display |
| Security | bandit, pip-audit, npm audit, OWASP ZAP baseline, authz fuzz (IDOR), secrets scan, header checks | CI blocking on high |
| Load | k6/Locust | 200 concurrent users, queue latency SLO |
| AI quality | eval dataset `tests/ai_eval/` : per tool × {SD, SMP, SMA, SMK, Madrasah} × {Merdeka, K13} × {complete, incomplete, odd, long} ; automatic checks (schema, completeness, language, forbidden claims, question counts) + rubric-based human review sheet (curriculum reviewer) + optional LLM-judge flagged as non-authoritative | Module "production-ready" only when critical tests + reviewer score threshold pass |
CI: GitHub Actions: lint (ruff, mypy, eslint, tsc) → tests → build images → scan. No claim of "working" without a passing run recorded in `PROJECT_STATUS.md`.
Note: live AI-quality runs need provider keys and cost real money — budget **[U]**.

## 25. Deployment strategy
- Images: `backend`, `worker`, `beat`, `frontend`, `nginx`; Compose profiles `dev` / `prod`. Alembic migration runs as one-off job before rollout. Health/readiness endpoints; blue/green or rolling via compose + Nginx upstream swap.
- Environments: local → staging (sandbox gateways, low spend limits) → production. Config via env/Secret store; `.env.example` with placeholders only.
- TLS via Let's Encrypt (certbot/Caddy alt.), HSTS. Domain/DNS [E].
- Observability: structured JSON logs → Loki; metrics (Prometheus: request latency, queue depth, AI latency/cost, credit anomalies); Grafana dashboards; Sentry; uptime alerts; alert on spend, error rate, queue lag, webhook failures, ledger-vs-snapshot drift.
- Managed Postgres preferred (backups/PITR); else self-managed with WAL-G. Object storage: S3/R2/MinIO-compatible. [U] cloud provider/region (Indonesian region for data-locality preference).
- Release: CI → staging → smoke/E2E → manual approve → prod; rollback = previous image + down-migration policy (expand/contract migrations).
- Beta: invite-only, spend caps on, feedback widget; commercial launch gate = Part 19 critical tests green + legal pages + backup restore drill + payment live-mode test with small real transaction [E].

## 26. Development roadmap (≈20 weeks; team-dependent)
| Wk | Phase | Exit criteria |
|---|---|---|
| 1–2 | P1 Spec sign-off, brand, UI wireframes, API/DB freeze v1 | approved docs |
| 3–5 | P2 Foundation: repo, CI, Docker, auth, RBAC, profiles, dashboard shell | auth/RBAC tests pass |
| 6–8 | P3 AI infra: adapters, registry, prompts, usage/cost, request pipeline (fake + 1 real provider) | provider contract tests |
| 7–9 | P4 Credits: ledger, reservation, settlement, allocation, packages, admin/user UI | concurrency tests pass |
| 9–12 | P5 Core tools (A first, then B, C, D, E) with eval dataset | per-module eval gate |
| 11–13 | P6 Document engine + editor + versions (parallel with P5) | export tests |
| 13–14 | P7 Library | access-control tests |
| 14–17 | P8 Subscriptions + Midtrans/Xendit + webhooks + renewals | sandbox E2E, webhook security tests |
| 16–18 | P9 Admin completion + analytics | RBAC audit |
| 18–20 | P10 QA, security, load, backup drill, beta → launch | launch checklist |
Critical path: prompt/content quality review (curriculum experts) and gateway merchant approval — start both in week 1.

## 27. Estimated infrastructure (rough, to be validated by load tests; no prices asserted)
| Stage | App/API | Workers | Postgres | Redis | Storage | Other |
|---|---|---|---|---|---|---|
| Dev/Staging | 1× 2 vCPU/4 GB all-in-one Compose | included | container | container | MinIO 20 GB | — |
| Beta (≤ ~500 users) | 1× 4 vCPU/8 GB (api+web+nginx) | 1× 2–4 vCPU/4–8 GB | managed 2 vCPU/4 GB, 50 GB | 1 GB | 100 GB | Sentry free/dev tier, uptime probe |
| Launch (~5k users) | 2× 4 vCPU/8 GB behind LB | 2–3× 4 vCPU/8 GB (AI I/O-bound; scale by queue depth) | 4 vCPU/16 GB + read replica, PITR | 2–4 GB (HA) | 500 GB–1 TB + CDN | Prometheus/Grafana/Loki node |
AI provider spend is usage-based and dominates variable cost; model it with the Admin finance dashboard during beta (cost per request × expected usage) rather than guessing now. [U]

## 28. Technical risks & mitigation
| Risk | Impact | Mitigation |
|---|---|---|
| AI hallucination / non-compliant curriculum content | Credibility, legal | Admin-managed curriculum references with citations, reviewer sign-off, disclaimers, eval gate, user review step |
| Provider cost spikes / price change | Margin loss | versioned pricing, dynamic pricing mode, spend limits, model fallback, daily reconciliation |
| Provider outage / key billing exhaustion | Downtime | multi-provider fallback, circuit breaker, alerts, auto-refund |
| Credit double-spend/refund bugs | Financial | ledger immutability, row locks, idempotency, concurrency tests, nightly ledger integrity audit |
| Webhook forgery / replay | Fraud | signature + server-side status re-fetch + dedupe + amount check |
| Student-data leakage to AI vendors | Legal/ethical | anonymizer, consent, minimization, vendor zero-retention settings, no-diagnosis guardrails |
| UU PDP non-compliance | Legal | counsel review, DPO role [U], data map, retention/deletion tooling |
| Prompt injection via uploaded text | Output integrity | delimiting, output schema validation, no tool/action execution from model output |
| Long-running generation timeouts | UX | async jobs + SSE, chunked generation for big docs, continuation logic |
| DOCX/PDF fidelity & Indonesian typography | Quality | embedded fonts, golden-file tests, templates reviewed by teachers |
| Gateway recurring billing limits | Revenue | invoice-based renewal MVP, add auto-debit when verified |
| Scope (65+ tools) | Schedule | Tools are data-driven (schema+prompt+template) on one engine; ship Module A/B first, rest incrementally behind feature flags |
| Library content/IP rights | Legal | only owner-created or licensed content; sample labelling |
| Tax/PPN and invoicing rules | Compliance | accountant input before launch |
| Abuse (free-trial farming, credential sharing) | Cost | email verification, device/IP limits, trial credit caps, anomaly detection |

---

## Assumptions, unresolved decisions, external dependencies

**Assumptions [A]:** Bahasa Indonesia primary; web-only (responsive) MVP; single currency IDR for customers, USD for provider costs; teacher-facing (no student logins); one wallet per user (or per institution).

**Unresolved [U] — decisions needed from owner (my recommended default in bold):**
1. Brand name → **Nalar Edu** (after TM/domain check).
2. Cloud/region & managed vs self-managed DB → **managed Postgres, Indonesian or Singapore region**.
3. Renewal model → **invoice-based first, auto-debit later**.
4. Credit rollover/expiry policy for subscription & purchased credits → **no rollover; purchased valid 12 months** (legal review).
5. Free trial → **10 bonus credits, 14 days**.
6. Credit unit: decimals (0.5) or integers → **0.5 steps**.
7. Single vs per-plan `credit_value_idr` → **single, admin-editable**.
8. Auth: email+password only vs +Google → **email+password; Google in Phase 2**.
9. Image generation in infographics/media → **out of MVP**.
10. PPN/tax handling and invoice format → **accountant**.
11. Annual plan credit drip vs upfront → **monthly drip**.
12. English UI → **later**.
13. Prices/credit costs/plan allocations (examples only) → finalize with beta cost data.

**External dependencies [E]:** OpenAI (and optionally Anthropic/Google) developer accounts with API billing; Midtrans/Xendit merchant accounts + sandbox/live keys; domain + DNS; cloud account; SMTP/email provider; curriculum subject-matter reviewers; legal review (UU PDP, ToS, privacy, refund/consumer rules); real library content; accountant; Sentry etc.

**Not done / not claimed:** no code written, nothing tested, no availability checks performed, no official regulation text quoted.
