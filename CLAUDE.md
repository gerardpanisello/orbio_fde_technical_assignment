# CLAUDE.md — Grupo Sazón Screening Agent

Project context for Claude Code. Read this first in every session.

## What we are building
An AI candidate-screening agent for **Grupo Sazón** (fictional restaurant chain, 45 locations in Spain + Mexico, ~1000 delivery-driver applications/week), plus a **recruiter dashboard**. This is a technical assignment for Orbio (FDE role). Full brief: [docs/assignment.md](docs/assignment.md).

## Working method: Spec-Driven Development (SDD)
**No code without a spec.** Every feature lives in `docs/specs/NNN-name/`:
1. `spec.md` — what & why: user stories, requirements, acceptance criteria, edge cases. No implementation details.
2. `plan.md` — how: modules, data models, interfaces, trade-offs, test strategy.
3. `tasks.md` — ordered, small, checkable tasks (each ends in green tests).

Flow: spec → (human review) → plan → (human review) → tasks → implement → verify against acceptance criteria → update docs.
Templates: [docs/specs/_templates/](docs/specs/_templates/). Roadmap: [docs/ROADMAP.md](docs/ROADMAP.md).
Architectural decisions go to `docs/adr/NNNN-title.md` (see [docs/adr/README.md](docs/adr/README.md)).

## Key decisions (see ADRs)
- **LLM:** Claude (Anthropic API). Stronger model for conversation, smaller/faster model for extraction, classification and summaries. Model IDs live in config, never hard-coded.
- **Hybrid architecture:** a deterministic **state machine** (Python) owns the flow, validation and qualification; the LLM only (a) extracts structured data from free text and (b) phrases replies. The LLM never decides whether a candidate is qualified.
- **Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 + SQLite (Postgres-ready).
- **Frontend:** React + Vite + TypeScript: WhatsApp-style candidate chat + recruiter dashboard.
- **Voice:** last phase, provider TBD.

## Conventions
- Code, docs, commits: **English**. Agent talks to candidates in ES (Spain/Mexico register) or EN.
- Tooling: `uv` (deps/venv), `ruff` (lint+format), `pytest`, `mypy --strict` on `backend/src`.
- Type hints everywhere; Pydantic models at every boundary (API, LLM I/O, storage).
- Business rules (zones, disqualifiers, scoring weights) live in `config/` YAML, not in code or prompts.
- Prompts live in `backend/src/.../prompts/` as versioned files, not inline strings.
- Never let an LLM exception crash a conversation: retry → fallback message → mark for human review.
- Small commits, Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- No secrets in the repo; `.env` (gitignored) + `.env.example`.

## Commands
Backend (run inside `backend/`):
- Install: `uv sync`
- Tests: `uv run pytest` · Lint: `uv run ruff check . && uv run ruff format --check .` · Types: `uv run mypy`
- All checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q`
- API (from phase 4): `uv run fastapi dev`

Frontend (from phase 5, inside `frontend/`): `npm run dev`

Layout: `backend/src/sazon_screening/` (package), `backend/tests/`, `config/` (client-editable YAML at repo root), `docs/`.

## Subagents (`.claude/agents/`)
- `spec-writer` — writes/updates spec.md, plan.md, tasks.md.
- `backend-implementer` — implements Python tasks from tasks.md with tests.
- `frontend-implementer` — implements React tasks.
- `test-engineer` — unit tests, conversation simulations, evals.
- `conversation-designer` — prompts, tone, personality, sample conversations.
- `reviewer` — reviews a finished feature against its spec (read-only).
