# ADR 0002 — Hybrid architecture: deterministic state machine + LLM

**Status:** Accepted

## Context
Screening decisions affect real people (labour context, possible legal scrutiny). The client needs predictable outcomes, auditability and the ability to change rules (zones, criteria) without retraining prompts. At the same time, candidates write messy free text ("tengo carné desde hace 3 años y he currado en glovo").

## Decision
Split responsibilities:
- **State machine (code):** owns stages, which field to ask next, validation, disqualification, scoring, re-engagement timing. Deterministic and unit-tested.
- **LLM (Claude):** (1) **extracts** any fields present in a message into a Pydantic schema (can fill several fields at once, out of order); (2) **phrases** the next reply given the engine's instruction (e.g. `ask_field=availability`, `reask_reason=ambiguous`) in the right language and tone.

The LLM never decides qualification; it only proposes extracted values, which code validates.

## Alternatives considered
- **Autonomous LLM agent with tools:** more natural, but less predictable, harder to test, outcomes harder to audit.
- **LangGraph / Pydantic AI:** structure for free, but adds abstraction to explain and debug; our graph is small enough to own.
- **Pure rule-based bot:** predictable but fails on free text and feels robotic → drop-off.

## Consequences
- Engine fully testable without API calls; LLM parts tested with fakes + evals.
- Two LLM calls per turn (extract + reply) → mitigate with fast model for extraction and parallelism where possible.
- Same engine reusable by the voice channel.
