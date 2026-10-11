# ADR 0003 — Stack: FastAPI + React/Vite + SQLite

**Status:** Accepted

## Context
Python is mandatory. The product must be usable by recruiters, and the evaluator must be able to run it easily.

## Decision
- **Backend:** FastAPI + Pydantic v2 (typed contracts shared with LLM I/O), SQLAlchemy 2.
- **DB:** SQLite for zero-setup; schema written to be Postgres-compatible (switch via `DATABASE_URL`).
- **Frontend:** React + Vite + TypeScript, two apps in one: WhatsApp-style candidate chat and recruiter dashboard.
- **Channel:** web chat simulating WhatsApp; real WhatsApp integration documented, not built.
- **Tooling:** uv, ruff, pytest, mypy.

## Alternatives considered
- Streamlit / HTMX: faster but reads as prototype.
- Postgres in Docker: more production-like but adds setup friction for the evaluator.
- Real WhatsApp (Twilio): impressive but fragile for a live demo (webhooks, template approval).

## Consequences
- Requires Node.js for the frontend build.
- SQLite limits concurrency → documented migration path in the deployment design.
