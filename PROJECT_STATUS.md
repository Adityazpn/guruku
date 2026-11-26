# PROJECT STATUS

_Last updated: 2026-11-26_

## Current phase
Phase 1 — Product specification: **approved (all defaults) 2026-11-26**.
Phase 2 — Foundation: **started** (backend skeleton only).

## Completed
- docs/SPEC_01_PRODUCT.md — brand options, positioning, features, modules/tools, journeys, UI inventory
- docs/SPEC_02_ARCHITECTURE_DATA_API.md — architecture, folder structure, ERD, schema, indexes, integrity rules, API
- docs/SPEC_03_ENGINE_CREDITS_PAYMENTS_OPS.md — AI engine, providers, cost vs credits, credit math/examples, reservation, subscriptions, payments, documents, security, testing, deployment, roadmap, infra, risks, assumptions

## Approved decisions (all recommended defaults)
Brand Nalar Edu (pending TM/domain check) · managed Postgres, ID/SG region · invoice-based renewal first · no subscription rollover, purchased credits valid 12 months (legal review) · trial 10 bonus credits/14 days · 0.5-credit steps · single credit_value_idr · email+password auth (Google later) · no image generation in MVP · PPN via accountant · annual plans drip monthly · English UI later · prices/credit costs finalized with beta data.

## Phase 2 progress
- [x] backend skeleton: module dirs, config (env-only secrets), /api/v1/health, pytest (1 passing), Dockerfile
- [x] docker-compose (db, redis, minio, backend), .env.example, .gitignore
- [x] Alembic + models (users, roles, user_roles, user_sessions); migration 0001 verified up/down on SQLite only
- [x] Auth: register/login/refresh/logout/me, Argon2id, 15-min JWT, rotating refresh cookie with reuse detection, lockout (5 fails/15 min), DB-checked RBAC dependency
- [x] Email verification + password reset (hashed single-use tokens, resets revoke sessions, no account enumeration), SMTP sender (console outbox when SMTP_HOST unset), in-process rate limiting, user profile GET/PUT; migration 0002
- [x] Frontend (Next.js 14, TS, Tailwind, Inter): landing, register, login, forgot/reset password, verify email, dashboard shell with auth guard, silent refresh, /api proxy to backend. `tsc`, `next build`, 2 vitest tests pass; browser walkthrough (Playwright, 390px, real backend on SQLite) passed: validation, bad login, login, reload via refresh cookie, no horizontal overflow, logout + route guard
- [x] CI workflow (.github/workflows/ci.yml): ruff, Alembic up/down/up on PostgreSQL, pytest, tsc, vitest, build — **not yet run on GitHub; first run will be the first Postgres check**
- [x] **Phase 4 (part): credit ledger** (backend/app/credits): wallets, typed buckets (no balance column), append-only ledger (PG trigger), overdraft trigger, idempotent grants (unique source per billing event), atomic reserve/settle/release with canonical-order row locks, configurable consumption priority + earliest-expiry-first, reservation sweeper, expiry job, auditable admin adjust + compensating reversal, trial credits on signup (10 / 14 days, from credit_settings), user endpoints GET /credits/summary + /credits/ledger; migration 0003
- [ ] Celery worker (to run sweeper/expiry jobs and AI tasks)

## Pending
Phases 3–10; remaining Phase 2 items above.

## Known bugs / gaps
- No CSRF token yet (cookie is SameSite=Lax, path-scoped to /auth); no MFA yet; rate limiter is in-process (move to Redis before multi-instance); email not tested against a real SMTP server; verification is not yet enforced for AI tool use.
- Not built yet in credits: pricing rules (fixed/dynamic/hybrid), usage limits, packages, admin endpoints, scheduled jobs (no worker yet), subscription allocation wiring (needs payments).

## Architecture decisions
See SPEC_02 §8 (AD-1…AD-11).

## Database migration status
None created.

## Testing status
Backend: 35 backend tests pass locally with PostgreSQL 16 (set TEST_DATABASE_URL; 19 pass + 16 PG tests skipped without it): auth, email flows, credits ledger, 4 concurrency tests (40 parallel reserves never overspend; duplicate idempotency key; duplicate settle/release; duplicate grant). Verified the concurrency tests fail when the row lock is removed. CI run #1 (auth+frontend) passed on GitHub incl. Alembic on PostgreSQL; ledger CI run pending. Docker Compose NOT yet run. Nothing else is claimed to work.

## Deployment status
Not deployed. Plan: frontend on Vercel (subdomain guruku.peluangruang.id via DNS CNAME), backend + Postgres + Redis on a VPS or managed services; the owner's Hostinger Premium shared hosting cannot run the backend. No credentials configured (OpenAI, Midtrans, Xendit, cloud, domain all pending owner).

## Next development task
After approval + answers to the unresolved decisions list (SPEC_03, end): Verify CI on GitHub; then credit pricing rules + estimate endpoint, then Phase 3 AI provider layer (adapters, model registry, pricing, cost tracking) and AI request pipeline wired to reserve/settle.
