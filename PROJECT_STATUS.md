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
- [ ] Alembic + base models (users, roles, sessions)
- [ ] Auth (Argon2id, JWT + refresh rotation), RBAC
- [ ] Frontend (Next.js) shell, CI, Celery worker

## Pending
Phases 3–10; remaining Phase 2 items above.

## Known bugs
None (no code).

## Architecture decisions
See SPEC_02 §8 (AD-1…AD-11).

## Database migration status
None created.

## Testing status
Backend: 1 test (health) passes locally. Docker Compose NOT yet run. Nothing else is claimed to work.

## Deployment status
Not deployed. No credentials configured (OpenAI, Midtrans, Xendit, cloud, domain all pending owner).

## Next development task
After approval + answers to the unresolved decisions list (SPEC_03, end): Alembic + user/role/session models, then auth/RBAC with tests.
