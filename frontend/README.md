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
| `/voz` | The same screening by voice (spec 013): Chrome/Edge speech-to-text, Sofi's reply spoken (ElevenLabs via `/api/voice/tts`, browser voice fallback) |
| `/recruiter` | Candidates: KPIs, filters (kept in the URL), priority-sorted table, detail drawer (`?id=`) |
| `/recruiter/entrevistas` | Week view per city (slots, booked/capacity, attendance) and a **Disponibilidad** tab to edit interview availability (spec 010; `?city=&week=&tab=`) |
| `/recruiter/zonas` | Staffing per zone (spec 015): occupancy bars, inline target/current edits, pipeline and waitlist per zone |
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
  voice/      VoicePage, MicButton, useSpeechRecognition (Web Speech API), useSpeaker (ElevenLabs or
              speechSynthesis), speakable.ts (what Sofi says aloud), voiceLogic.ts (pure turn rules)
  recruiter/  RecruiterLayout, CandidatesPage, FilterBar, CandidateTable, CandidateDrawer,
              detail/ (summary, actions, transcript, traces + JSON), InterviewsPage, ZonesPage, AnalyticsPage
  components/ Badges (status, priority, recruiter tag), Kpi, ScoreBreakdown, RecordFields, Reasons,
              States (loading/empty/error), Icon, Logo
  lib/        status.ts (status colours, one source for badges, table and charts), labels.ts
              (Spanish labels), format.ts, record.ts, filters.ts, funnel.ts, interviews.ts, zones.ts
              (occupancy bands, optimistic zone edits)
```

## Design notes

- **Status colours** live in `src/lib/status.ts` and are used by badges, table and charts alike.
  The chromatic steps were checked with a palette validator for colour-blind separation;
  colour is never the only cue (badges and charts always carry the label).
- **Explainability:** the drawer shows the score as a sum of factors (value and points per
  factor), disqualification and review reasons, flags, each extracted field with its validation
  status, the transcript, per-turn traces (model, latency, cost, fallback) and the raw record JSON.
- **Re-engagement (spec 008):** the open chat polls its conversation every 4 s (only while visible,
  idle and in progress; `lib/reengagement.ts#shouldPoll`), so reminders arrive on their own; the demo
  panel's **Avanzar tiempo ⏩** runs the next step via `POST /api/dev/conversations/{id}/advance`.
- **Voice (spec 013):** the rules are pure and unit-tested (`voiceLogic.ts`: the mic never opens while
  Sofi speaks or while waiting for the API; `speakable.ts`: no emoji/URLs, privacy link "en pantalla",
  quick replies read as "Puedes decir: Sí o No", dates as "lunes 19 de octubre"); the hooks are thin.
  Page tests render under StrictMode with a fake `SpeechRecognition` and `speechSynthesis`.
- **Chat state** is in `useChat`: the conversation id is kept in `sessionStorage`, so a reload
  restores the transcript; a failed send marks the bubble "No se pudo enviar · Reintentar".
- **City and zone names** come from `GET /api/meta/areas` (read from `config/service_areas.yaml`),
  so the frontend never duplicates the config.
- Recruiter UI copy is Spanish; candidate UI strings are ES/EN (`chat/i18n.ts`); the agent's own
  messages come from the backend.
