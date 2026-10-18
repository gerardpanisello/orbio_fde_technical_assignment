# Spec 017 — Catalan (ca) as a third candidate language (compact)

**Status:** Approved (Gerard, 2026-10-19)
**Related:** spec 001 §5 (language switch), spec 003 (language detection, register, templates, guard), spec 007 (multilang), spec 009 (FAQ per language), spec 013 (voice), ADR 0005 (`language` + `register` on every action).

## 1. Why
Grupo Sazón has locations in Barcelona; many candidates there prefer Catalan. Answering in the candidate's language lowers drop-off and shows client empathy. English already works; Catalan is the missing local language.

## 2. Requirements
- FR-1 `Language` gains `ca`; register `ca-ES` (Catalan is only offered for Spain). Candidate can start in Catalan (start screen option "Català") or switch mid-conversation; code-switching ES↔CA↔EN follows the latest message's dominant language (same rule as ES↔EN). Data stays language-neutral.
- FR-2 Extraction detects `ca` (prompt version bump; wire schema still all-required/non-nullable). Catalan answers are extracted like Spanish ones ("tinc 24 anys", "carnet de conduir", "visc a Gràcia", "el mes que ve", "caps de setmana", "a la tarda").
- FR-3 Phrasing writes natural Catalan in Sofi's persona (feminine forms: "encantada"), same rules (≤ 300 chars, one question, no invented facts). New `config/messages/ca-ES.yaml` with **every** template (catalog coverage check must pass) — the fallback is always Catalan, never Spanish.
- FR-4 Guard language check recognises Catalan (stopwords) so Catalan replies don't fall back by mistake; month names, dates ("dilluns 19 d'octubre"), quick-reply labels and recap labels in Catalan.
- FR-5 FAQ: every entry gets a `ca` answer (+ 2–3 Catalan question variants); retrieval works for Catalan questions ("quant es cobra?").
- FR-6 Recruiter summary stays ES/EN (recruiters' choice); it states "Idioma del candidato: catalán".
- FR-7 Voice: `/voz` offers Català (STT `ca-ES`); TTS via ElevenLabs if the model supports Catalan (verify in their docs), else browser voice `ca-ES`; document what was verified.
- FR-8 Dashboard: language filter/label shows "Catalán"; analytics by language includes `ca`.

## 3. Acceptance criteria
- AC-1 A full screening entirely in Catalan reaches `interview_scheduled`; every Sofi message is Catalan (live check).
- AC-2 Switching ES → CA mid-conversation switches replies to Catalan and keeps all data.
- AC-3 Catalog coverage: `ca-ES.yaml` covers every template; every shipped template passes the guard.
- AC-4 Catalan FAQ question retrieves the right entry and is answered in Catalan.
- AC-5 Extraction mapping tests for typical Catalan answers (fake/scripted) and language detection `ca`.
- AC-6 Existing ES/EN tests stay green; record schema regenerated if the enum changes.

## 4. Tasks
- [ ] T1 vocab/engine (`ca`, `ca-ES` register rules), schema, record schema regen.
- [ ] T2 Extraction prompt + mapping; fake rules basic Catalan.
- [ ] T3 `ca-ES.yaml` templates, labels, dates, guard stopwords; phrasing prompt note.
- [ ] T4 FAQ `ca` answers + variants.
- [ ] T5 Frontend: start screen "Català", labels, voice `ca-ES`; regenerate types.
- [ ] T6 Live check (AC-1, AC-2, AC-4), README/ROADMAP, sample conversation in Catalan.
