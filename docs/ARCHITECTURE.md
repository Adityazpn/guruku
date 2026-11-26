# Architecture (as built)

Modular monolith. Details of intent in docs/SPEC_02; this file records what exists.

```
Browser ── nginx(TLS) ──┬─ /api/* ─► FastAPI (uvicorn) ──► PostgreSQL (source of truth: users, credits ledger, orders, documents)
                        └─ /*     ─► Next.js                 ▲
FastAPI ─ enqueue ─► Redis ─► Celery worker ─► AI provider (OpenAI adapter) ─► credits settle ─► document version
Celery beat: reservation sweeper, bucket expiry, stuck-request recovery, subscription tick, retention purge
Payment gateway ─ signed webhook ─► FastAPI ─ re-fetch status from gateway API ─► exactly-once fulfilment
```
Backend modules (`backend/app/`): `auth`, `users`, `credits` (ledger, reservation, pricing), `ai_providers` (adapters, keys, prices), `ai_engine` (tools catalogue, prompts, pipeline), `tools` (HTTP), `documents` (versions, renderers), `payments`, `subscriptions`, `library`, `assistant`, `privacy`, `admin`, `core`.
Key decisions: AI work is always asynchronous; the ledger (append-only) is the only truth for balances; provider cost and customer credits are separate domains; tools/prompts/prices/pricing rules are data edited by admins; every sensitive admin write is audited in the same transaction.
