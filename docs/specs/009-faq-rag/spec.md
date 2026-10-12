# Spec 009 — FAQ answers grounded in a knowledge base (RAG) — compact

**Status:** Approved (lightweight format, 2026-10-12)
**Related:** spec 003 (FR-13 `answer_faq` hook, guard `_invented_pay`), ADR 0006, spec 001 §3 ("never invents pay or conditions").

## 1. Why
Candidates ask before committing ("¿cuánto se paga?", "¿necesito moto propia?", "¿qué horario hay?"). Today Sofi always answers "lo consulto con el equipo", which pushes the candidate to a recruiter: exactly the call we want to avoid, and a weak demo. The answer must come **only** from content the client approved; a wrong promise about pay or contract is a liability.

## 2. Requirements
- FR-1 **Knowledge base** in `config/faq/` (client-editable YAML): entries with `id`, `question` variants (es/en), `answer` per language (es-ES, es-MX may override, en), `tags`, optional `country` (ES/MX/all), `updated` date. ~20 entries, fictional but plausible: pay model and range per country, contract type, vehicle (own vs company, fuel/maintenance), insurance, schedules and shifts, minimum hours, weekends, payment frequency, tips, uniform and equipment, training, start process, documents needed, locations, interview format, age, license types, multiple apps allowed, how long the process takes, contact a human.
- FR-2 **Retrieve:** given the extracted `faq_question` (+ language, + country if known), return the top-k (k=3) entries with scores. Lexical retrieval (BM25 over question variants + tags, accent/case-insensitive, light stemming for es/en). No external vector DB.
- FR-3 **Ground:** if the best score passes a configured threshold, pass the retrieved entries to the phrasing call; the model answers **only** from them (≤ 600 chars, then resumes the pending question). Country-specific entries are preferred when the country is known; if the country is unknown and the answer differs by country, answer generally and say it depends on the city.
- FR-4 **No match / low confidence:** keep today's behaviour ("lo consulto con el equipo") and flag the question for the recruiter (`faq_unanswered`, stored in the trace and visible in the dashboard detail).
- FR-5 **Guard:** the existing pay guard stays; money amounts are allowed only if they appear in the retrieved approved answer. A grounded answer that fails the guard → falls back to the entry's own text (the approved answer, verbatim), not to the holding message.
- FR-6 **Trace & analytics:** per turn, store the question, retrieved ids + scores, `answered|unanswered`. Analytics: top asked questions, unanswered rate.
- FR-7 Fake mode: retrieval is real (no LLM needed); phrasing uses the entry's approved answer verbatim.

## 3. Plan
- `backend/src/sazon_screening/faq/` — `models.py` (Pydantic + loader validation), `retrieve.py` (small BM25 implementation, ~60 lines, no dependency), `__init__.py`.
- Wire-in: in the pipeline, when the turn has `faq_question`, retrieve before phrasing and set `ctx.faq_answer` (the rendered entries). The engine is unchanged (it already emits the `answer_faq` preface).
- Trade-offs:
  | Option | Why not / why |
  |---|---|
  | Stuff the whole FAQ in the cached system prompt | Simplest and very accurate for 20 entries, but doesn't scale to a real knowledge base (hundreds of entries, per-location data) and gives no retrieval trace to audit. Mentioned as the alternative. |
  | Embeddings + vector DB | Better recall on paraphrases, but needs an embeddings provider and infra; overkill for ~20–100 curated entries. Upgrade path documented. |
  | **BM25 + multilingual question variants (chosen)** | Deterministic, testable offline, explainable scores, zero infra. Paraphrase gap is covered by writing 3–5 variants per entry and by the extractor normalising the question. |
- Tests: retrieval unit tests (ES/EN/MX phrasing, accents, typos-lite), threshold behaviour, guard interplay, pipeline test in fake mode, one `live` test.

## 4. Acceptance criteria
- AC-1 "¿cuánto se cobra?", "how much do you pay?" and "cuánto pagan la hora" retrieve the pay entry first.
- AC-2 With country MX, the pay answer is the Mexico entry (MXN); with ES, the Spain one (EUR).
- AC-3 An unrelated question ("¿cuál es la capital de Francia?") is below threshold → holding message + `faq_unanswered`.
- AC-4 In a conversation, a FAQ mid-flow gets an answer **and** the pending question is asked again in the same message.
- AC-5 A phrased answer containing an amount not in the approved entry fails the guard and the approved text is sent instead.
- AC-6 Invalid FAQ YAML (duplicate id, missing language) fails at startup with a clear error.
- AC-7 Analytics exposes top questions and the unanswered rate.

## 5. Tasks
- [ ] T1 FAQ YAML (~20 entries, es-ES/es-MX/en) + models + loader validation (AC-6).
- [ ] T2 BM25 retrieval + tests (AC-1..AC-3).
- [ ] T3 Pipeline wiring + trace + fake mode (AC-4, AC-5).
- [ ] T4 API/analytics fields + dashboard: show the FAQ in the transcript trace and a "Preguntas frecuentes" card on the analytics page (AC-7).
- [ ] T5 Live check with the real API; add 1–2 FAQ turns to a sample conversation; README/ROADMAP.
