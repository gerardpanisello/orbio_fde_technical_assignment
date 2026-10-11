# ADR 0006 — Candidate-facing LLM text is guarded by code, with template fallback

**Status:** Accepted

## Context
Every message a candidate reads is written by an LLM (spec 003 phrasing; later FAQ answers 009, follow-ups 008, voice 013). LLM output can be too long, ask two questions, invent pay or conditions, switch language, or simply fail (timeout, refusal). The brief demands "graceful failures, no crashes", and a recruiting message with a wrong promise is a real liability for the client.

## Decision
Every candidate-facing text goes through the same three steps:
1. **Generate** from a typed instruction (the engine action, the FAQ entry...), never from free conversation.
2. **Check in code** (deterministic, cheap): length cap per action type, at most one question, language matches, no numbers or currency (pay) unless they came from the source data, quick replies built by code (never by the model).
3. **Fallback** to a deterministic **template** for that action, language and register if generation fails or any check fails. The trace records `fallback` and why.

## Alternatives considered
- **Trust the model + prompt only:** simplest, but failures reach candidates and can't be measured.
- **Templates only:** safe but robotic, and doesn't handle register or code-switching naturally → more drop-off.
- **Second LLM call as a judge on every message:** better recall for subtle issues, but doubles latency and cost per turn. We use the LLM judge offline in evals (spec 012) instead.

## Consequences
- The candidate always receives a sensible message, even with the API down (templates double as the offline/fake-mode output).
- Fallback rate becomes a quality metric in analytics (011).
- Templates must be maintained for every action × language × register; they are also the reference the eval compares tone against.
