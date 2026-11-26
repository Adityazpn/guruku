# SPEC 01 — Product, Brand, Modules, Journeys, UI Inventory

Status: **DRAFT for approval** · Covers deliverables 1–8 of Part 23.
Legend: **[A]** assumption · **[U]** unresolved decision · **[E]** external dependency.

---

## 1. Brand proposals (10 original names)

None of these names have been checked for trademark (PDKI Indonesia / WIPO) or domain availability. **Domains listed are candidates only.** [E] Availability checks must be done by the owner before choosing.

| # | Name | Meaning | Positioning | Tagline (ID) | Personality | Visual idea | Candidate domains |
|---|------|---------|-------------|--------------|-------------|-------------|-------------------|
| 1 | **Gurunesia** | Guru + Indonesia | National AI work-suite for teachers | "Mengajar lebih cerdas, lebih ringan." | Warm, local, dependable | Navy wordmark, light-blue dot over "i" like a spark | gurunesia.id / .com |
| 2 | **Pustaka Guru AI** | Library of the teacher | Resources + AI under one roof | "Semua kebutuhan guru, satu tempat." | Scholarly, calm | Open-book mark formed by two navy planes | pustakaguru.ai / .id |
| 3 | **Kelasku Pintar** | "My smart class" | Friendly classroom copilot | "Asisten kelas yang paham guru." | Approachable, practical | Rounded chalk-bubble in light blue | kelaskupintar.id |
| 4 | **Nalar Edu** | *Nalar* = reasoning | Credible, intelligence-first | "Nalar cerdas untuk pendidik." | Serious, modern | Minimal "N" built from a graduation-cap angle | nalaredu.id / .ai |
| 5 | **Cakra Guru** | *Cakra* = wheel/cycle of work | Productivity engine for admin | "Administrasi selesai, fokus mengajar." | Efficient, confident | Circular arrow monogram | cakraguru.id |
| 6 | **Ruang Ajar** | "Teaching room" | Workspace metaphor | "Ruang kerja digital para guru." | Calm, professional | Window/door glyph, navy + white | ruangajar.id |
| 7 | **Mitra Pendidik** | Educator partner | Trust, institutional sales | "Mitra cerdas setiap pendidik." | Trustworthy, formal | Two overlapping circles | mitrapendidik.id |
| 8 | **Asisten Guru** | Teacher's assistant | Descriptive, SEO-friendly | "Asisten AI di balik guru hebat." | Plain, clear | Speech-bubble + pencil | asistenguru.ai [descriptive → weak trademark] |
| 9 | **Akademika AI** | Academic | Credibility for schools/madrasah | "Produktivitas akademik berbasis AI." | Authoritative | Serif-free geometric "A" arch | akademika.ai |
| 10 | **Lentera Ajar** | Lantern of teaching | Guidance, inclusive of madrasah | "Menerangi cara kita mengajar." | Gentle, inspiring | Lantern outline, light-blue glow | lenteraajar.id |

**Recommended top 3:** (1) **Nalar Edu** – short, distinctive, trademarkable, intelligence + trust; (2) **Gurunesia** – strongest local recall, easy to say; (3) **Ruang Ajar** – clear workspace metaphor, works for schools. #8 is rejected as primary (descriptive ⇒ hard to protect).
**[U]** Final brand choice by owner. The spec below uses the working name **"the Platform"**.

### Identity tokens
- Navy `#0B1F4B` (primary) · White `#FFFFFF` · Light blue `#4DA3FF` (accent) · surfaces `#F5F8FC`, border `#E2E8F0`, text `#0F172A`/`#475569`; status: success `#16A34A`, warn `#D97706`, error `#DC2626`.
- Font Inter (400/500/600/700). 4-px spacing scale; radius 8/12; no decorative gradients; dark mode **[U]** (not in MVP).
- Tone of voice: formal-friendly Bahasa Indonesia ("Anda"), no hype claims.

---

## 2. Positioning
"AI Education Productivity Platform": one account → many specialized tools → one credit wallet. Differentiators: structured outputs (not chat), editable + exportable documents, transparent credits, privacy-by-design for student data, curriculum references that admins can update. **Non-claims:** outputs are *drafts requiring teacher review*; never labelled "official/compliant" (see Part 21 rule 9). Every generated document carries a configurable footer disclaimer.

---

## 3. Feature inventory (summary)

| Area | Features |
|------|----------|
| Accounts | Register/login (email+password, Google OAuth **[U]**), email verification, password reset, profile (school, level, subjects), preferences, sessions list/revoke, MFA for admins |
| AI tools | 7 modules, ~65 tools (see §4), each: form → estimate → generate → structured preview → edit → save → regenerate → export |
| Documents | Versioned documents, duplicate, share link (signed), DOCX/PDF/XLSX/PPTX/TXT exports, download log |
| Credits | 3 buckets (subscription/bonus/purchased), ledger, reservation, dynamic/fixed/hybrid pricing, expiry, limits |
| Billing | Plans (monthly/annual), upgrade/downgrade, renewal, cancel, grace, invoices, refunds, credit packages, promo codes |
| Payments | Midtrans + Xendit via abstraction, verified webhooks only |
| Library | Search, filters, tags, preview, premium gating, download history, admin upload, file versions |
| Assistant | Chat with history, context window mgmt, doc generation from chat, credits |
| Institutions | School accounts, member licences, shared credit pool, usage reports |
| Admin | Users, tools, providers, prompts, credits, subscriptions, payments, library, finance, system, audit |
| Privacy | Student-data anonymizer, consent, retention, deletion, advisory-only labelling |
| Ops | Queue, retries, monitoring, backups, alerts |

---

## 4. Module descriptions and tool catalogue

Each tool = one row in `ai_tools` with its own input schema, output schema, prompt template (versioned), default credit cost, access plan, model assignment. **Initial credit costs are seed placeholders [U], editable in Admin.**

**Common input fields (Module A, B, E where relevant):** `education_level` (SD/MI, SMP/MTs, SMA/MA, SMK, Other), `curriculum` (Kurikulum Merdeka / K13 / custom – from `curriculum_references`), `subject`, `grade`/`phase` (Fase A–F for Merdeka), `semester`, `topic`, `learning_objectives`, `extra_instructions`, `language` (default id), `output_length`.

### A. Teaching Planning (12) — doc outputs DOCX/PDF
RPP, Modul Ajar, ATP, TP, PROTA, PROMES, Silabus, KOSP, LKPD, Bahan Ajar, Tujuan Pembelajaran, Alur Pembelajaran.
Output schema per tool is section-based JSON (e.g. Modul Ajar: identitas, kompetensi awal, profil pelajar Pancasila, sarana, target peserta didik, model pembelajaran, komponen inti [tujuan, pemahaman bermakna, pertanyaan pemantik, kegiatan pembuka/inti/penutup, asesmen, pengayaan & remedial], refleksi, lampiran). PROTA/PROMES output tables (also XLSX). **Section names derive from an admin-editable `document_templates` definition; spec does not assert that these match any current Kemendikbudristek/Kemenag regulation. [U]/[E] Domain expert (curriculum reviewer) must validate templates and curriculum reference data.**

### B. Assessment & Evaluation (12)
MCQ, Essay, HOTS, Blueprint (kisi-kisi), Answer key, Rubric, Student Score Analyzer (XLSX upload/paste → stats: mean, median, SD, KKM/ KKTP pass rate, distribution), Exam Result Analyzer (item analysis: difficulty, discrimination, distractor — computed **deterministically in code**, AI only writes narrative), UTS/UAS/PAS/PAT generator, Question Bank (CRUD, tags, reuse, export), Remedial, Enrichment.
Params: number of questions (1–100 bound by plan), difficulty (mudah/sedang/sukar mix), Bloom C1–C6, indicators, option count, explanations, rubrics.

### C. Teacher Administration (11)
Teaching journal, Attendance admin (register class roster, record/export — **non-AI CRUD, 0 credits**), Student notes, Class agenda, Program kerja guru, Homeroom admin, School letters, Activity report, Supervision docs, Portfolio, PMM/PKG templates (**templates only; no claim of integration with the government PMM platform**).

### D. Student Analysis & Assistance (10)
Character analysis, Learning-difficulty analysis, AI counseling assistant, Learning recommendations, Class management assistant, Development analysis, Attendance analysis (stats in code, narrative AI), Remedial recommendations, Homeroom assistant, Daily assistant.
**Hard rules:** advisory banner on every output; prompts forbid diagnosis/medical/psychological labels; flagged-risk phrases (self-harm, abuse) trigger a fixed safety response advising referral to a qualified counselor / school BK and local authorities instead of AI advice; anonymization pipeline (§ SPEC_03 §22) mandatory before provider call; consent checkbox per class roster.

### E. Learning Media (10)
Presentation content, Slide generator (PPTX), Material summarizer (accepts pasted text / uploaded DOCX/PDF/TXT; size-capped), Digital module, Infographic content (text blocks + layout spec; **no image generation in MVP [U]**), Mind map (hierarchical JSON → rendered SVG/PNG in frontend and exported in DOCX/PPTX), Video script, Interactive activity, Project ideas, Game concept.

### F. Digital Library
Categories per Part 4. Items have: title, description, type, level, subject, tags, access (free/plan-tier), files (versioned), preview (first-page image or HTML), download count. **All seed content is flagged `is_sample=true` and visibly labelled "Contoh / Sample"** until real resources are supplied and reviewed [E].

### G. Central AI Teacher Assistant
Streaming chat (SSE), conversation list/new/rename/delete (soft-delete + hard purge job), context = last N messages + rolling summary (summary refreshed when > token threshold), per-message credit charge (dynamic by token usage, with minimum), "Turn into document" action routes to the relevant tool with prefilled inputs, system prompt restricts scope to education.

---

## 5. User journey (teacher)

1. Landing → pricing → Register → verify email → onboarding (level, subjects, school; privacy notice + consent).
2. Free trial: **[U]** e.g. 10 one-time trial credits (bonus bucket, 14-day expiry) — configurable.
3. Dashboard: sees credits, recent items, recommended tools; global search (Ctrl+K).
4. Open tool → form (with saved presets) → sees **estimated credits** + balance → Generate.
5. Job runs in background; UI shows progress (SSE/polling); on success → structured preview.
6. Edit inline (rich-section editor), Save (new version), Regenerate (confirms extra credits), Export DOCX/PDF.
7. Find in My Documents / AI History; use Library; ask Assistant.
8. Low credits → buy package or upgrade → checkout → webhook-verified activation → notification + invoice.
9. Manage subscription (upgrade/downgrade/cancel), view payment history, profile, delete account/data.

Failure paths: insufficient credits (CTA to buy), provider error (auto-refund + retry), invalid output (auto-repair retry once, else refund), plan lacks tool (upgrade prompt).

## 6. Admin journey

1. Login (MFA) → overview (revenue, API cost, margin, errors, queue health).
2. Configure providers → add credentials (write-only) → register models → set pricing record → assign models to tools → test call.
3. Configure tools & prompts → draft new prompt version → test with sample inputs → compare outputs → publish / rollback.
4. Configure credits: tool costs, plan allocations, packages, limits, consumption priority, rounding/margin.
5. Configure plans & promotions; review subscriptions, cancellations.
6. Monitor payments → webhook inspector → reconcile → refund.
7. Manage library uploads and versions.
8. Review finance dashboard (estimated vs verified labels), spending-limit alerts, anomaly list.
9. Users: search, suspend, adjust credits (reason mandatory ⇒ compensating ledger entry), view audit log.

---

## 7. UI/UX page inventory

**Public:** Landing, Features, Tools catalogue, Pricing, Library preview, Contact/Support, Privacy Policy, Terms, Register, Login, Forgot/Reset password, Verify email.

**User app (`/app`):** Overview · AI Generator hub (global tool grid + search) · AI Assistant (chat) · Teaching Planning · Assessment · Teacher Administration · Student Analysis · Learning Media (category pages) · each Tool page (`/app/tools/[slug]`: form, estimate, result, editor) · Digital Library (list, detail/preview) · My Documents (list, detail, version history, share) · AI History · AI Credits (buckets, ledger, usage by tool, packages) · Subscription (plan, change, cancel) · Checkout/Status · Payment History + Invoices · Account Profile (profile, security, sessions, privacy/consent, data deletion) · Class Roster (anonymization aliases) · Help Center · Notifications.

**Institution admin:** members, licences, shared credits, usage report, billing.

**Admin (`/admin`):** Overview · Users (list/detail) · Tools (list/editor) · Prompts (versions/test/compare) · Providers (providers, credentials, models, pricing, assignments, usage, errors) · Credits (dashboard, tool costs, allocations, packages, grants, ledger inspector, expiry) · Plans & Promotions · Subscriptions · Payments (orders, payments, webhooks, reconciliation, refunds) · Library (items, upload, versions) · Finance analytics · Announcements · Support tickets · Feature flags · Settings · Audit logs · Error logs/monitoring · Curriculum references · Institutions.

UX rules: responsive ≥360 px, sidebar → bottom sheet on mobile, WCAG AA contrast, skeleton loading, optimistic UI only for non-financial actions, every destructive action confirmed, empty/error states designed, all strings in i18n catalogue (id default; en optional **[U]**).
