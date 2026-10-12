# Spec 013 — Browser voice agent (compact)

**Status:** Approved (Gerard, 2026-10-13: option A — browser STT + our pipeline + ElevenLabs TTS)
**Related:** ADR 0005 (turn contract: a new channel is an adapter), ADR 0006, specs 003/005.

## 1. Why
Bonus tier "Great": the same screening by voice in the browser. Some candidates prefer talking to typing (driving, low literacy, older phones). Proving that voice reuses the **same engine and pipeline** is also the architecture argument of ADR 0005.

## 2. Decision & trade-offs
| Option | Verdict |
|---|---|
| **A. Browser speech-to-text (Web Speech API) → our API → ElevenLabs text-to-speech** | **Chosen.** Reuses 100% of the flow, no public URL, free tier enough. Turn-based (no barge-in); ~3.5–4 s per turn + TTS. |
| B. ElevenLabs Conversational AI with our backend as "custom LLM" | More natural turn-taking/barge-in, but needs a public tunnel and an OpenAI-compatible adapter; our per-turn latency would show. Documented as the production path. |
| C. Browser TTS too | Zero setup, robotic voice. Used as **fallback** when ElevenLabs is not configured or fails. |

## 3. Requirements
- FR-1 `/voz` page (and a "Hablar con Sofi" entry on Home): same start screen (language, country), then a voice UI: big mic button (push-to-talk and tap-to-toggle), live transcript of what the candidate says (interim results), Sofi's reply shown as text **and** spoken, conversation transcript below, end-of-call banner per status.
- FR-2 Speech-to-text with the browser Web Speech API (`es-ES`, `es-MX`, `en-US` by selection). If unsupported (e.g. Firefox), show a clear message and offer the text chat.
- FR-3 Turns go through the **existing** endpoints (`POST /api/conversations`, `/messages`); the conversation is a normal conversation (visible in the dashboard), tagged `channel: "voice"` only in the frontend label for now (no backend schema change in this spec).
- FR-4 **Speakable text** (pure frontend helper): strip emojis/markdown/URLs, turn the privacy link into "la política de privacidad que verás en pantalla", read quick replies as "Puedes decir: Sí o No" (or "por ejemplo: Moto, Coche…" when > 3), spell dates naturally ("lunes 19 de octubre"). The on-screen text stays the original.
- FR-5 **TTS proxy** `POST /api/voice/tts {text, language, register}` → `audio/mpeg`. Uses `ELEVENLABS_API_KEY` + a configurable voice id per language in `config/voice.yaml` (a warm female voice, multilingual model). Key never reaches the browser. Errors/missing key → 503, and the frontend falls back to `speechSynthesis` (FR-C). Cache identical (text, voice) in memory to save credits.
- FR-6 Voice-friendly flow: after Sofi finishes speaking, auto-listen (toggleable); "No te he oído, ¿puedes repetir?" on empty recognition; the mic is disabled while Sofi speaks or while waiting for the API (avoid recording herself).
- FR-7 Quick-reply taps still work on screen (accessibility).

## 4. Acceptance criteria
- AC-1 A full screening can be completed by voice in Chrome (es-ES) ending in an interview booked; the conversation appears in the dashboard with the full transcript.
- AC-2 Speakable text: unit tests for emoji/URL stripping, quick replies spoken, dates.
- AC-3 TTS endpoint returns audio with a mocked ElevenLabs client; 503 without key; cache hit avoids a second call (backend tests, no network).
- AC-4 Without `ELEVENLABS_API_KEY` the page still works with browser TTS.
- AC-5 Unsupported browser → explanatory message + link to text chat.
- AC-6 lint/test/build + backend checks green.

## 5. Tasks
- [x] T1 Backend: `config/voice.yaml`, `api/routes/voice.py` TTS proxy (httpx to ElevenLabs REST, cache, 503 path), tests with a fake client. Do **not** modify `api/service.py`, `api/models.py` (WhatsApp work in parallel).
- [x] T2 Frontend: speakable-text helper + tests; speech hooks (`useSpeechRecognition`, `useSpeaker` with ElevenLabs→browser fallback).
- [x] T3 `/voz` page + Home entry; verify; README/ROADMAP.

## 6. Implementation notes (2026-10-13)
- TTS body is `{text, language, country}` (`register` shadows a Pydantic attribute; the country is the register). Added `GET /api/voice/status` (`elevenlabs` | `browser`) so the page shows the engine and skips doomed TTS calls.
- Model `eleven_multilingual_v2`, `mp3_44100_64`. Default voice "Sarah" (`EXAVITQu4vr4xnSDxMaL`) is an ElevenLabs *Default* voice: only for accounts created before March 2026 and retired on 2026-12-31. With a newer account, put the id of "Talia - Warm Soft Guide" (its suggested replacement) or another warm Spanish-speaking voice in `config/voice.yaml` or `ELEVENLABS_VOICE_ID`.
- `/voz` keeps its own conversation id (`useChat` storage key), so it never resumes the text chat's conversation.
- Verified in headless Chrome with a fake `SpeechRecognition`/`speechSynthesis` (full screening to a booked interview, transcript in the dashboard, ElevenLabs path with mocked audio, 503 → browser fallback). Not verified: a real microphone and real ElevenLabs audio.
- Fake LLM mode does not understand "la primera" / "uno" for a slot ("la 1", "opción 1", the time do work); the real extractor is expected to.
