# Spec 004 — Persistence + HTTP API (compact: spec + plan + tasks)

**Status:** Approved (lightweight format agreed with Gerard, 2026-10-12)
**Related:** ADR 0003 (FastAPI + SQLite), ADR 0007 (async I/O around a sync engine), specs 002/003.

## 1. Why
The engine and LLM layer only run in a terminal. The candidate chat (005) and the recruiter dashboard (006) need an HTTP API, and the brief requires conversations + extracted data to be **stored**. Goal: the smallest API that makes the product usable and demoable, built so it could go to Postgres by changing `DATABASE_URL`.

## 2. Requirements
**Candidate side**
- FR-1 `POST /api/conversations` `{language?, country_hint?}` → creates a conversation and returns Sofi's greeting (`id`, `status`, `messages`).
- FR-2 `POST /api/conversations/{id}/messages` `{text}` → runs one turn (`ScreeningAgent.handle_message`), stores the candidate message, the agent reply and the turn trace, returns `{reply: {text, quick_replies} | null, status}`. A quick-reply tap is sent as its text.
- FR-3 `GET /api/conversations/{id}` → transcript + status (chat reload).
- FR-4 Messages to the same conversation are processed **one at a time** (per-conversation lock); a closed conversation still answers (engine handles it).
- FR-5 Interview slots offered by the API come from a simple slot provider (next 3 working days, fixed hours, configurable), replacing the demo's hard-coded slots. Real calendars are 010.

**Recruiter side**
- FR-6 `GET /api/candidates?status=&country=&city=&bucket=&recruiter_status=&q=&sort=` → list rows: id, name, city/zone, status, bucket, score, availability, experience, start date, language, interview slot, created/updated, recruiter status.
- FR-7 `GET /api/candidates/{id}` → record JSON (002 schema), summary (default language), transcript, per-turn traces (model, latency, cost, fallback), recruiter actions.
- FR-8 `GET /api/candidates/{id}/summary?lang=es|en` → stored summary in that language; generated on demand and stored if missing (003 FR-19b).
- FR-9 `POST /api/candidates/{id}/actions` `{action: shortlist|reject|hire|override|note, note?}` → stored in an audit table; updates `recruiter_status` (`new` → `shortlisted` | `rejected` | `hired`). `override` on a disqualified/needs_review candidate sets `recruiter_status=shortlisted` and flag `recruiter_override` (the agent outcome is kept for audit; reopening the chat is out of scope).
- FR-10 `GET /api/candidates/export.csv` (same filters as FR-6).
- FR-11 `GET /api/analytics` → totals by status, completion rate, drop-off by stage, median duration, disqualification reasons, fallback rate, avg cost per screening, by country (feeds 006/011).

**Demo / dev**
- FR-12 `POST /api/dev/seed?n=40` (only when `APP_ENV=dev`) → creates N simulated conversations with the **fake** LLM (varied personas: qualified, each disqualifier, abandoned at different stages, needs_review, EN speakers), spread over the last 14 days, so the dashboard has data. Deterministic with a seed.
- FR-13 `POST /api/dev/conversations/{id}/silence` (dev) → sends `silence_expired` (until 008 adds timers).

**Cross-cutting**
- FR-14 The summary is generated **after** replying when `summary_due` (FastAPI BackgroundTasks), so the candidate is never slowed down.
- FR-15 Errors: unknown id → 404; invalid body → 422; any unexpected error → 500 JSON without stack trace, logged with conversation id. The LLM layer already never raises on LLM failures.
- FR-16 CORS for the Vite dev server; `GET /api/health`.
- NFR-1 Fake mode by default (`LLM_MODE`), so the API and its tests run with no key.
- NFR-2 Tests use an in-memory/temp SQLite and the fake LLM; no network.

## 3. Plan
- **Stack:** FastAPI, SQLAlchemy 2 async + `aiosqlite`, Pydantic response models. Package `backend/src/sazon_screening/api/`:
  - `app.py` (factory `create_app(settings)`, lifespan builds the agent + DB), `deps.py`
  - `db.py` (engine/session), `models.py` (tables), `repo.py` (queries, the only place with SQL)
  - `routes/conversations.py`, `routes/candidates.py`, `routes/analytics.py`, `routes/dev.py`
  - `schemas.py` (request/response models), `service.py` (turn orchestration: load state → agent → save, lock, summary task), `slots.py`, `seed.py`
- **Tables** (JSON columns for engine objects; denormalised columns only for filtering/sorting):
  - `conversations`: id (uuid str), created_at, updated_at, status, stage, language, country, city, zone, full_name, score, bucket, recruiter_status, interview_slot, state_json, record_json, flags_json
  - `messages`: id, conversation_id, role (`candidate`|`agent`), text, quick_replies_json, created_at, trace_json (agent turns)
  - `summaries`: conversation_id, language, json, created_at (PK conversation_id+language)
  - `recruiter_actions`: id, conversation_id, action, note, created_at
  - `create_all` at startup (no Alembic: noted as an improvement).
- **Why denormalise:** the dashboard filters by status/city/bucket; reading JSON for every row doesn't scale past demo size.
- **Trade-offs:** sync SQLAlchemy would be simpler but blocks the event loop (ADR 0007); a per-process lock is enough for one instance (multi-instance needs a DB row lock or a queue: deployment design, 014).

## 4. Acceptance criteria (fake LLM)
- AC-1 Create conversation → 201 with greeting and quick replies `Sí/No`; row stored with status `in_progress`.
- AC-2 A scripted happy path through the API ends `interview_scheduled`; transcript has every message in order; record JSON validates against the 002 schema; a summary in `es` exists after the background task.
- AC-3 Two concurrent posts to the same conversation are processed sequentially (no lost update).
- AC-4 Unknown id → 404; empty body → 422; a message to a closed conversation → 200 with a `closed_ack`-style reply.
- AC-5 List filters (status, city, bucket, q by name) and sort by score/updated work; export CSV has a header and one row per candidate.
- AC-6 `GET summary?lang=en` generates and stores an English version once (second call does not call the LLM).
- AC-7 Actions: shortlist/reject/hire/override/note are stored in order; override on a disqualified candidate sets `recruiter_status=shortlisted` + flag.
- AC-8 Analytics on seeded data: counts add up to the total; drop-off stages only for abandoned; completion rate = finished / total.
- AC-9 Seed is deterministic for a given seed and refuses to run unless `APP_ENV=dev`.
- AC-10 Opted-out conversations expose no PII in list/detail/export (002 FR-11).

## 5. Tasks
- [x] T1 deps (`fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `aiosqlite`, `httpx` for tests), settings (`DATABASE_URL`, `APP_ENV`, CORS origins), app factory + health. 
- [x] T2 DB models + repo + test fixtures (temp SQLite, fake agent).
- [x] T3 Slot provider + `service.py` turn orchestration with lock + background summary (AC-1..AC-4).
- [x] T4 Conversation routes (AC-1..AC-4).
- [x] T5 Candidate list/detail/summary/actions/export (AC-5..AC-7, AC-10).
- [x] T6 Analytics (AC-8).
- [x] T7 Seed + dev routes (AC-9).
- [ ] T8 README (how to run the API: `uv run fastapi dev src/sazon_screening/api/app.py`), CLAUDE.md commands, ROADMAP.
