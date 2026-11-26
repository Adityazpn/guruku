# First-time setup: getting a real AI model working

Nothing here uses real credentials from the repository. You supply them; they are stored encrypted in the database.

## 0. Prerequisites you must obtain yourself
- An **OpenAI developer platform account with API billing enabled** (separate from any ChatGPT subscription) and an API key.
- Set `PROVIDER_KEY_MASTER` (a long random string) and `SECRET_KEY` in the server environment **before** saving any key. If you
  lose or change `PROVIDER_KEY_MASTER`, stored keys can no longer be decrypted and must be entered again.

## 1. Create the first admin
From `backend/` with `DATABASE_URL` pointing at your database, after `alembic upgrade head`:
```bash
python ../scripts/create_admin.py you@example.com super_admin
```
Log in, then open **Panel admin** in the sidebar (`/admin`). Roles: `super_admin` (everything) and `ai_admin` (providers, tools, prompts,
pricing; cannot grant credits or read the audit log). No MFA yet: use a strong, unique password.

## 2. Seed the first tool (once)
Tools are data. The first one (`tp-generator`) is created by `app.ai_engine.seed.seed_tp_tool`; run it from a shell, or use `scripts/seed_dev.py`
**only in development** (it adds a fake provider and illustrative prices).

## 3. In Admin → Provider AI
1. **Kurs USD → IDR**: enter today's rate (accepted range 1,000–100,000).
2. **Tambah provider** → `openai`.
3. Paste the **API key** → Simpan key. It is write-only; only the last 4 characters are ever shown again.
4. **Tambah model**: type the model id *exactly as shown in OpenAI's current documentation/model list* (this project does not hardcode model ids).
5. **Simpan harga**: enter that model's input and output price per 1M tokens in USD from OpenAI's **current official pricing page**.
   Prices are versioned; entering new ones never rewrites history.
6. **Tes koneksi** (one tiny real call). If it fails, the error code tells you why (`provider_auth`, `provider_quota`, `provider_bad_request`...).
   `provider_bad_request` usually means the model id or a request parameter is not accepted: see "Known risk" below.
7. **Aktifkan provider**. Optionally set daily/monthly USD spend limits: when reached, the provider is skipped and the request is refunded.

## 4. In Admin → Alat & Prompt
1. Pick the model (and optionally a fallback) for each tool.
2. Set the **aturan harga kredit** (fixed / dynamic / hybrid). Users are never charged above "Maks kredit".
3. The tool shows **siap** when nothing is missing; otherwise the card lists exactly what is.
4. Prompts: edit → *Simpan sebagai draf* → *Publikasikan*. Published versions are immutable; "Kembalikan ke versi ini" republishes old text as a new version.

## Known risk (read before going live)
The OpenAI adapter has only been tested against a simulated HTTP server, never the live API. Parameter names (`max_completion_tokens`,
`response_format`) and model compatibility must be confirmed with the connection test and one real generation before opening to users.
Costs shown in the admin are **estimates** (provider-reported tokens × the prices you entered), not provider invoices.
