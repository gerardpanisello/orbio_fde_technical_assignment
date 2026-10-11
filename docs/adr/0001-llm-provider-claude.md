# ADR 0001 — Claude (Anthropic) as LLM provider

**Status:** Accepted

## Context
The agent must hold natural ES/EN conversations (incl. Spain vs Mexico register and code-switching), extract structured data reliably, resist off-script/injection attempts, and summarise. ~1000 conversations/week now, 10K target.

## Decision
Use the Anthropic API with **two model tiers**, configured via env/config:
- **Conversation model** (larger): phrasing replies, tone adaptation, FAQ answers.
- **Fast model** (smaller): field extraction via tool use / structured output, language & sentiment classification, summaries.

Concrete choice (verified against Anthropic's model table, 2026-10-11; IDs live in config):

| Role | Model | Price in / out per 1M tokens | Why |
|---|---|---|---|
| Extraction, classification, summary | `claude-haiku-5-5` | $0.10 / $0.50 | High volume, schema-constrained output; cheapest current model with structured outputs |
| Reply phrasing (candidate-facing) | `claude-sonnet-5-5` | $2 / $10 | Tone, register (es-ES / es-MX / en), persona adherence; it is what the candidate reads |
| Eval judge (offline only) | `claude-opus-5-5` | $4 / $20 | Most capable current Opus to grade the other two |

**Rough cost** (assumption: ~12 turns per screening, ~2K input + ~200 output tokens for extraction and ~1.5K + ~80 for phrasing per turn, before prompt caching): about **$0.05 per candidate**, so **~$50/week at 1,000 applications** and ~$500/week at 10K. Prompt caching of the static system prompt should lower this further. Spec 003 measures the real numbers.

## Alternatives considered
- **OpenAI GPT:** strong structured outputs and Realtime voice API; comparable quality. Not chosen to keep a single provider and because of Claude's instruction-following on persona/guardrails.
- **Gemini:** cheapest; less consistent persona adherence in our experience.
- **Multi-provider abstraction (LiteLLM):** adds a dependency; instead we isolate the provider behind our own small `LLMClient` interface so swapping is cheap.

## Consequences
- Provider lock-in mitigated by the `LLMClient` interface (also lets tests use a fake LLM).
- Two-tier models reduce cost/latency for the high-volume calls.
- Prompt caching can be used for the static system prompt to cut cost at scale.
