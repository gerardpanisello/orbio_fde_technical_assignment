# Spec 005 + 006 — Candidate chat + Recruiter dashboard (compact: spec + plan + tasks)

**Status:** Approved (lightweight format, 2026-10-12)
**Related:** ADR 0003, spec 004 (API contract), spec 001 §7 (tone, quick replies).

## 1. Why
This is what Grupo Sazón (and the Orbio evaluator) actually sees. Two users, one app:
- **Candidate:** a WhatsApp-like chat on the phone. Replaces the phone call 60% never answer.
- **Recruiter:** a work tool to see who to call first, why, and act. Replaces the 80% of time spent on unqualified candidates.

## 2. Requirements

### 005 — Candidate chat (`/chat`)
- FR-1 Mobile-first chat that looks like a messaging app: Sofi header with avatar and "en línea", bubbles (agent left, candidate right), timestamps, ticks, typing indicator while waiting.
- FR-2 Quick replies rendered as tappable chips under the last agent message; tapping sends the chip text.
- FR-3 Start screen: language (ES/EN) and country (España/México) selector to simulate the phone prefix, then the greeting.
- FR-4 Conversation id kept in `sessionStorage`, so a reload restores the transcript (`GET /api/conversations/{id}`); "Nueva conversación" resets.
- FR-5 When the conversation reaches a final status, show a small banner (e.g. "Entrevista agendada: martes 13/10, 10:00").
- FR-6 Errors (network down, 500) show an inline "No se pudo enviar · Reintentar" on the bubble; never a blank screen.
- FR-7 On desktop the chat is shown inside a phone frame, with a side panel (demo only, toggleable) showing the live extracted record for the presenter.

### 006 — Recruiter dashboard (`/recruiter`)
- FR-8 **Candidates view:** KPI tiles (total, interviews booked, needs review, completion rate) + filter bar (status, country, city, priority bucket, recruiter status, search by name) + table sorted by priority/score by default. Columns: name, city/zone, status badge, priority (bucket + score), availability, experience, start date, interview slot, language, updated.
- FR-9 **Candidate detail** (side panel or page): summary (ES/EN toggle, FR-19b), key data, **score with factors** (explainability), disqualification / review reasons, flags, transcript, raw JSON (collapsible), per-turn traces (model, latency, cost, fallback) collapsed by default.
- FR-10 **Actions:** shortlist, reject, hire, override (only when disqualified / needs review), add note; history of actions shown.
- FR-11 **Export CSV** with the current filters.
- FR-12 **Interviews view:** upcoming booked interviews grouped by day.
- FR-13 **Analytics view:** funnel (started → consented → knock-outs passed → qualified → booked), drop-off by stage, disqualification reasons, by country, completion rate, median duration, fallback rate, avg cost per screening.
- FR-14 Dev helper: "Generar datos demo" button calling `POST /api/dev/seed` when the API is in dev mode.

### Cross-cutting
- NFR-1 UI copy for recruiters in **Spanish** (users are recruiters in Spain/Mexico); code in English.
- NFR-2 Loading, empty and error states everywhere.
- NFR-3 Responsive: chat works at 360 px; dashboard usable at 1280 px and readable on a tablet.
- NFR-4 Accessible basics: semantic HTML, focus states, contrast, `aria-live` for new chat messages.

## 3. Plan
- **Stack:** React 18 + Vite + TypeScript (strict), **Tailwind CSS** (fast, consistent styling without a component library to explain), `react-router`, **TanStack Query** (server state, caching, refetch after actions), **Recharts** for the analytics charts.
- **API types generated from FastAPI's OpenAPI** with `openapi-typescript` (`npm run gen:api` → `src/api/schema.d.ts`). One thin `src/api/client.ts`. Trade-off: one more dev step, but frontend and backend can't drift silently.
- **Dev proxy:** Vite proxies `/api` → `http://localhost:8000`, so no CORS issues and the same paths work in production behind one origin.
- **Layout:** `src/pages/Home.tsx` (two cards: "Soy candidato" / "Soy recruiter"), `src/chat/*`, `src/recruiter/*` (`CandidatesPage`, `CandidateDetail`, `InterviewsPage`, `AnalyticsPage`), `src/components/*` (Badge, Kpi, EmptyState…).
- **Visual identity:** Grupo Sazón = warm restaurant brand. Primary terracotta/orange, neutral greys, WhatsApp-like greens only inside the chat. Status colours consistent across table, badges and charts.
- **Tests:** a few Vitest + Testing Library tests for the pieces with logic (quick replies, status badge mapping, filters → query string). No exhaustive UI testing (agreed: lighter process).

## 4. Acceptance criteria
- AC-1 With the API in fake mode, a full happy-path conversation can be completed in the chat by tapping quick replies and typing, ending with the interview banner.
- AC-2 Reloading the page restores the conversation.
- AC-3 With the API stopped, sending shows a retry affordance and no crash.
- AC-4 After seeding, the candidates table shows rows, filters and search narrow them, and the default order puts high priority first.
- AC-5 Opening a candidate shows summary, score factors, transcript and JSON; switching summary language to EN loads the English version.
- AC-6 Shortlist / reject / override / note update the row and the action history without a page reload.
- AC-7 Export downloads a CSV respecting the filters.
- AC-8 Analytics page renders all charts from `/api/analytics` with seeded data, and an empty state with no data.
- AC-9 `npm run build` and `npm run lint` pass; `npm test` passes.

## 5. Tasks
- [x] T1 Scaffold Vite React-TS in `frontend/`, Tailwind, router, TanStack Query, ESLint, Vitest; Vite proxy; `gen:api` script.
- [x] T2 Home + layout + design tokens (colours, status badge map).
- [x] T3 Chat: start screen, bubbles, quick replies, typing indicator, session restore, error/retry, final banner (AC-1..AC-3).
- [x] T4 Chat demo side panel with the live record.
- [x] T5 Recruiter: candidates page with KPIs, filters, table (AC-4).
- [x] T6 Candidate detail + actions + summary language toggle (AC-5, AC-6).
- [x] T7 Export + interviews view (AC-7).
- [x] T8 Analytics page (AC-8).
- [ ] T9 Polish pass (empty/loading/error states, responsive), README section, CLAUDE.md commands (AC-9).
