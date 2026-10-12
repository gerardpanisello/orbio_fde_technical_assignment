# Roadmap

Status: ⬜ not started · 🟨 in progress · ✅ done

Target: ~1 week. Order matters: **core first, bonuses on top of a solid core**. Voice last.

| # | Phase / Spec | Deliverable | Status |
|---|---|---|---|
| 0 | Foundations | Repo, CLAUDE.md, ADRs, SDD templates, subagents, tooling | ✅ |
| 1 | `001-process-design` | **Phase 1 doc** (1–2 pages): stages, branching, personality, fields & validation, edge cases, outcomes, tone. Doc: [process-design.md](specs/001-process-design/process-design.md) | ✅ |
| 2 | `002-screening-engine` | Domain models, state machine, validators, zones config, scoring — pure Python, no LLM, fully tested | ✅ |
| 3 | `003-llm-layer` | Claude client, extraction (structured output), reply generation, language detection, summary, retries/fallbacks — live-tested | ✅ |
| 4 | `004-persistence-api` | SQLite models, conversation/candidate storage, FastAPI endpoints | 🟨 |
| 5 | `005-candidate-chat-ui` | WhatsApp-style web chat | ⬜ |
| 6 | `006-recruiter-dashboard` | Pipeline, candidate detail (summary/transcript/JSON), actions, CSV export | ⬜ |
| 7 | `007-multilang-guardrails` | ES/EN + code-switching, injection/off-topic/abuse handling, PII policy, sentiment-aware tone | ⬜ |
| 8 | `008-reengagement` | Silence detection, follow-up schedule & messages, drop-off tracking | ⬜ |
| 9 | `009-faq-rag` | FAQ knowledge base + retrieval to answer candidate questions | ⬜ |
| 10 | `010-interview-scheduling` | Offer slots to qualified candidates, recruiter calendar view | ⬜ |
| 11 | `011-analytics` | Funnel, completion, drop-off stage, duration, disqualification reasons | ⬜ |
| 12 | `012-evals` | Simulated candidates (LLM personas), LLM-as-judge, scenario suite, report | ⬜ |
| 13 | `013-voice-agent` | Browser voice agent reusing the same engine | ⬜ |
| 14 | Design docs | ATS integration API spec, deployment & scaling (10K/week) design | ⬜ |
| 15 | Delivery | README, sample conversations, demo video script, presentation | ⬜ |

## Suggested week plan
- **Day 1:** Phases 0–1 (design doc reviewed with you before any code).
- **Day 2:** Phase 2 (engine) + start 3.
- **Day 3:** Phases 3–4 → working end-to-end chat via API.
- **Day 4:** Phases 5–6 → usable product.
- **Day 5:** Phases 7–9.
- **Day 6:** Phases 10–12.
- **Day 7:** Phase 13 if time, 14–15, rehearse demo.

Cut line if time runs short: 13 (voice) → 10 (scheduling) → 9 (RAG). Never cut tests or the design doc.
