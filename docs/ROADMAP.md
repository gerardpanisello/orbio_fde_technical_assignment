# Roadmap

Status: ⬜ not started · 🟨 in progress · ✅ done

Target: ~1 week. Order matters: **core first, bonuses on top of a solid core**. Voice last.

| # | Phase / Spec | Deliverable | Status |
|---|---|---|---|
| 0 | Foundations | Repo, CLAUDE.md, ADRs, SDD templates, subagents, tooling | ✅ |
| 1 | `001-process-design` | **Phase 1 doc** (1–2 pages): stages, branching, personality, fields & validation, edge cases, outcomes, tone. Doc: [process-design.md](specs/001-process-design/process-design.md) | ✅ |
| 2 | `002-screening-engine` | Domain models, state machine, validators, zones config, scoring — pure Python, no LLM, fully tested | ✅ |
| 3 | `003-llm-layer` | Claude client, extraction (structured output), reply generation, language detection, summary, retries/fallbacks — live-tested | ✅ |
| 4 | `004-persistence-api` | SQLite models, conversation/candidate storage, FastAPI endpoints, demo seed — spec: [004](specs/004-persistence-api/spec.md) | ✅ |
| 5 | `005-candidate-chat-ui` | WhatsApp-style web chat — spec: [005-006-frontend](specs/005-006-frontend/spec.md) | ✅ |
| 6 | `006-recruiter-dashboard` | Pipeline, candidate detail (summary/transcript/JSON), actions, CSV export, interviews, analytics | ✅ |
| 7 | `007-multilang-guardrails` | ES/EN + code-switching, injection/off-topic/abuse handling, PII policy, sentiment-aware tone — built into 002/003 (signals, guard, opt-out purge, language keeping) | ✅ |
| 8 | `008-reengagement` | Silence detection, follow-up schedule & messages, drop-off tracking — spec: [008](specs/008-reengagement/spec.md); backend done (`config/reengagement.yaml`, pure policy, scheduler, `/advance` demo endpoint, analytics); chat polls for reminders, "Avanzar tiempo" demo control, detail block and Analítica card | ✅ |
| 9 | `009-faq-rag` | FAQ knowledge base + retrieval to answer candidate questions — spec: [009](specs/009-faq-rag/spec.md); ~20 approved entries in `config/faq/`, BM25, unanswered questions flagged in the dashboard | ✅ |
| 10 | `010-interview-scheduling` | Offer slots to qualified candidates, recruiter calendar view — spec: [010](specs/010-interview-scheduling/spec.md); availability per city editable in the dashboard, capacity-checked booking, reschedule/cancel by chat, .ics invite, day-before reminder, week view with attendance (external calendars: not built) | ✅ |
| 11 | `011-analytics` | Funnel, completion, drop-off stage, duration, disqualification reasons — `/api/analytics` + Analítica page | ✅ |
| 12 | `012-evals` | Simulated candidates (LLM personas), LLM-as-judge, scenario suite, report — `backend/evals/` (judge 4.12 → 4.70 after fixes) | ✅ |
| 13 | `013-voice-agent` | Browser voice agent reusing the same engine — spec: [013](specs/013-voice-agent/spec.md); `/voz` page (Web Speech API → normal turn API → ElevenLabs TTS proxy, browser voice fallback); full screening by voice verified in headless Chrome with a scripted fake recognizer; real-microphone and real-ElevenLabs test pending | 🟨 |
| 14 | Design docs | [ATS integration](design/ats-integration.md), [deployment & scaling](design/deployment.md) (10K/week) | ✅ |
| 15 | `015-zone-occupancy` | Staffing per zone (Zonas page), zone-demand score factor with live priority, waitlist when the zone is full, hire → +1 — spec: [015](specs/015-zone-occupancy/spec.md) | ✅ |
| 16 | `016-whatsapp` | Real WhatsApp channel (Meta Cloud API): signed webhook, dedupe, reply buttons/lists, media, do-not-contact, reminders via WhatsApp (template after 24 h), channel badge/filter/analytics — spec: [016](specs/016-whatsapp/spec.md), setup: [whatsapp-setup.md](whatsapp-setup.md); built and tested with a fake Graph client, live test pending credentials | 🟨 |
| 17 | `017-catalan` | Catalan as a third candidate language (Barcelona): `ca` / `ca-ES` register, every template and FAQ answer in Catalan, guard tells Catalan from Spanish, extraction v7 / phrasing v7, start screen "Català", voice `ca-ES` (TTS model `eleven_v4_turbo`); summaries stay es/en — spec: [017](specs/017-catalan/spec.md); live-checked (full screening, ES→CA switch, FAQ) | ✅ |
| 18 | Delivery | README, sample conversations, demo video script, presentation | ⬜ |

## Suggested week plan
- **Day 1:** Phases 0–1 (design doc reviewed with you before any code).
- **Day 2:** Phase 2 (engine) + start 3.
- **Day 3:** Phases 3–4 → working end-to-end chat via API.
- **Day 4:** Phases 5–6 → usable product.
- **Day 5:** Phases 7–9.
- **Day 6:** Phases 10–12.
- **Day 7:** Phase 13 if time, 14 and 16 (delivery), rehearse demo.

Cut line if time runs short: 13 (voice) → 10 (scheduling) → 9 (RAG). Never cut tests or the design doc.
