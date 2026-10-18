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
- [x] T1 vocab/engine (`ca`, `ca-ES` register rules), schema, record schema regen.
- [x] T2 Extraction prompt + mapping; fake rules basic Catalan.
- [x] T3 `ca-ES.yaml` templates, labels, dates, guard stopwords; phrasing prompt note.
- [x] T4 FAQ `ca` answers + variants.
- [x] T5 Frontend: start screen "Català", labels, voice `ca-ES`; regenerate types.
- [x] T6 Live check (AC-1, AC-2, AC-4), README/ROADMAP, sample conversation in Catalan.

## 5. Notes (implementation, 2026-10-19)
- **Prompts:** extraction.v7 (`language` may be `ca`; Catalan-only cues such as "tinc", "visc", "vull", "sóc", "d'acord", "amb", "els", "a la tarda", "l'any"; a Catalan place name never makes a message Catalan), phrasing.v7 (ca-ES register row, feminine forms, apostrophes, no Spanish calques), summary.v2 (the note is always in the recruiter's language). `llm.yaml` 2026-10-19.2. Wire schema still all-required/non-nullable.
- **Fallbacks:** Catalan is optional only for display data (place names, slot labels: fall back to es). Every message template and every FAQ answer (`ca-ES`, required) is Catalan; the last-resort message too.
- **Guard:** the language check counts Catalan-only words against Spanish-only words, so a Catalan reply is never rejected as Spanish and a Spanish reply in a Catalan chat falls back to the Catalan template. "Hi ha" is not the English "Hi"; "Bona tarda!" is a repeated greeting; "encantat" is a masculine form. Every greeting must keep "automated" and the privacy link (the live run once dropped "(automàtica)").
- **Summary:** recruiter summaries are es/en only (`lang=ca` is 422). The live run once wrote the note in Catalan, so a narrative in another language is now dropped (facts only) and logged.
- **Voice (FR-7), verified 2026-10-19 on elevenlabs.io/docs/models:** Catalan (ca) is listed for `eleven_v4`, `eleven_v4_turbo`, `eleven_v3` and `eleven_v3_conversational`; it is not listed for `eleven_multilingual_v2` (our default) or `eleven_flash_v2_5`. `config/voice.yaml` therefore has `models: {ca: eleven_v4_turbo}` (the docs' recommendation for real-time agents); Catalan uses the `es` voice id unless a `ca` one is set. Not tested against the real API (no ElevenLabs key in this environment); without a key the browser speaks with a `ca-ES` voice, and recognition runs in `ca-ES`.
- **Live check (real model):** a full Catalan screening (with "quant es cobra?" answered from `pay-es` in Catalan) and an ES→CA switch both reached `interview_scheduled` with every Sofi message in Catalan; sample: [l-catalan](../../sample-conversations/l-catalan.md).
- **Known limits:** interview places (`interview_slots.yaml`) are single-language client data, so a Catalan confirmation shows "(dirección ficticia)" from the demo address (English chats already did); a per-language place would fix it. FAQ analytics label a Catalan question with the entry's Spanish question. Analytics have no per-language breakdown yet, so there is nothing to extend for FR-8 beyond the drawer label.
