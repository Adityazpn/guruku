# Security overview (what exists, what does not)

**Implemented and tested**
- Passwords: Argon2id; lockout after 5 failures (15 min); identical errors for unknown email vs wrong password; reset/verify tokens are single-use, hashed, short-lived; password reset revokes all sessions.
- Sessions: 15-minute access token (memory only in the browser); rotating refresh token in an HttpOnly, SameSite=Lax, path-scoped cookie with reuse detection (a replayed old token revokes every session); CSRF guard on cookie endpoints (custom header + Origin allowlist).
- Authorization: role checks read the database (revocation is immediate); object-level ownership checks return 404 for other users' data (documents, orders, requests, conversations); admin routes need an **MFA-verified token** (TOTP, secret encrypted at rest).
- Secrets: provider API keys and MFA secrets encrypted with `PROVIDER_KEY_MASTER`; write-only in the API (only last 4 shown); verified absent from responses, audit log and UI; log formatter never records bodies/headers/query strings.
- Money: server-side prices; verified + re-checked webhooks; exactly-once fulfilment; append-only credit ledger and audit log (DB triggers); no negative balances (service lock + DB trigger); idempotency keys on money/AI endpoints.
- Web: security headers on API and frontend (CSP, nosniff, frame deny, HSTS in production), rate limits (app + nginx), input validation (Pydantic + JSON Schema), parameterized SQL only, React output escaping, sandboxed prompt templates.
- Privacy: student-data tools use an anonymizer before any text reaches an AI provider, require recorded consent, and are advisory-only (see below).
- Backups: nightly encrypted dumps; `verify_backup.sh` proves restorability and trigger survival.

**Known gaps / owner decisions**
- Rate limiter is in-process (per API worker); nginx adds IP-level limits. Move to Redis if you scale out.
- No automated malware scan on uploaded library files; uploads are restricted by type/size and served with `Content-Disposition: attachment`.
- Admin MFA has no recovery codes: lose the authenticator ⇒ an operator must reset `mfa_enabled` in the database.
- No WAF, no DDoS protection beyond nginx limits (consider Cloudflare in front).
- Indonesian personal-data-protection (UU PDP) compliance needs legal review; the engineering controls here are not legal advice.
- Dependency/vulnerability scanning is not automated in CI yet (run `pip-audit` / `npm audit` before launch).
- Penetration test: not performed.
