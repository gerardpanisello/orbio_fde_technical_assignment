# ADR 0001 — Claude (Anthropic) as LLM provider

**Status:** Accepted

## Context
The agent must hold natural ES/EN conversations (incl. Spain vs Mexico register and code-switching), extract structured data reliably, resist off-script/injection attempts, and summarise. ~1000 conversations/week now, 10K target.

## Decision
Use the Anthropic API with **two model tiers**, configured via env/config:
- **Conversation model** (larger): phrasing replies, tone adaptation, FAQ answers.
- **Fast model** (smaller): field extraction via tool use / structured output, language & sentiment classification, summaries.

Exact model IDs and per-conversation cost estimate to be verified and recorded in spec 003.

## Alternatives considered
- **OpenAI GPT:** strong structured outputs and Realtime voice API; comparable quality. Not chosen to keep a single provider and because of Claude's instruction-following on persona/guardrails.
- **Gemini:** cheapest; less consistent persona adherence in our experience.
- **Multi-provider abstraction (LiteLLM):** adds a dependency; instead we isolate the provider behind our own small `LLMClient` interface so swapping is cheap.

## Consequences
- Provider lock-in mitigated by the `LLMClient` interface (also lets tests use a fake LLM).
- Two-tier models reduce cost/latency for the high-volume calls.
- Prompt caching can be used for the static system prompt to cut cost at scale.
