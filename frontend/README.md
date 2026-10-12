# Frontend

Candidate chat and recruiter dashboard for the Grupo Sazón screening agent
(spec [005-006](../docs/specs/005-006-frontend/spec.md)). React + Vite + TypeScript
(strict), Tailwind CSS v4, react-router, TanStack Query, Recharts.

## Run the demo

Two terminals. The API runs in fake-LLM mode by default (no key, fast, deterministic).

```bash
# 1. API (from backend/)
uv run uvicorn sazon_screening.api.app:create_app --factory --port 8000

# 2. Frontend (from frontend/)
npm install
npm run dev            # http://localhost:5173
```

Vite proxies `/api` to `http://127.0.0.1:8000`, so there is no CORS setup and the
same relative paths work in production behind one origin.

Demo data: the **Generar datos demo** button in the dashboard sidebar (or
`curl -X POST "http://127.0.0.1:8000/api/dev/seed?n=40"`). Only available with `APP_ENV=dev`,
the API default.

| URL | What |
|---|---|
| `/` | Entry: "Soy candidato" / "Soy recruiter" |
| `/chat` | WhatsApp-style chat with Sofi. Desktop: phone frame + toggleable "Registro en vivo" demo panel |
| `/recruiter` | Candidates: KPIs, filters (kept in the URL), priority-sorted table, detail drawer (`?id=`) |
| `/recruiter/entrevistas` | Booked interviews grouped by day |
| `/recruiter/analitica` | Funnel, drop-off, disqualification reasons, status per country, agent KPIs |

## Scripts

```bash
npm run dev        # dev server with the /api proxy
npm run build      # type-check (tsc -b) + production build
npm run lint       # oxlint, warnings fail
npm test           # vitest (jsdom + Testing Library)
npm run gen:api    # regenerate src/api/schema.d.ts from the running API's OpenAPI
```

Run `npm run gen:api` (API running) whenever a backend response model changes, and commit
the generated file: the frontend's types then match the Pydantic models, and a breaking
change shows up as a type error in `npm run build`.

## Layout

```
src/
  api/        client.ts (the only module that calls the API), queries.ts (TanStack Query keys/hooks),
              schema.d.ts (generated)
  chat/       ChatPage, StartScreen, ChatWindow, MessageBubble, QuickReplies, TypingIndicator,
              LiveRecordPanel, useChat (state: start/send/retry/restore), i18n (ES/EN UI strings)
  recruiter/  RecruiterLayout, CandidatesPage, FilterBar, CandidateTable, CandidateDrawer,
              detail/ (summary, actions, transcript, traces + JSON), InterviewsPage, AnalyticsPage
  components/ Badges (status, priority, recruiter tag), Kpi, ScoreBreakdown, RecordFields, Reasons,
              States (loading/empty/error), Icon, Logo
  lib/        status.ts (status colours, one source for badges, table and charts), labels.ts
              (Spanish labels), format.ts, record.ts, filters.ts, funnel.ts, interviews.ts
```

## Design notes

- **Status colours** live in `src/lib/status.ts` and are used by badges, table and charts alike.
  The chromatic steps were checked with a palette validator for colour-blind separation;
  colour is never the only cue (badges and charts always carry the label).
- **Explainability:** the drawer shows the score as a sum of factors (value and points per
  factor), disqualification and review reasons, flags, each extracted field with its validation
  status, the transcript, per-turn traces (model, latency, cost, fallback) and the raw record JSON.
- **Chat state** is in `useChat`: the conversation id is kept in `sessionStorage`, so a reload
  restores the transcript; a failed send marks the bubble "No se pudo enviar · Reintentar".
- **City and zone names** come from `GET /api/meta/areas` (read from `config/service_areas.yaml`),
  so the frontend never duplicates the config.
- Recruiter UI copy is Spanish; candidate UI strings are ES/EN (`chat/i18n.ts`); the agent's own
  messages come from the backend.
