# ADR 0005 — Engine turn contract: proposals + signals in, typed action out

**Status:** Accepted

## Context
The deterministic engine (spec 002) is used by the chat LLM layer (003), guardrails (007), re-engagement (008), FAQ (009), scheduling (010) and voice (013). They all need one stable interface. Without one, each feature would couple to engine internals or let the LLM drive the flow.

## Decision
The engine is a pure function:

```
step(state, input, config, today) -> (new_state, action)
input  = proposals: {field: typed value | UNCLEAR}  +  signals {opt_out, wants_human, correction,
         faq_question, language, off_topic, abuse, extraction_failed}  +  context {country_hint}
       | event: silence_expired | slot_selected(id) | no_slot_fits
action = one primary action (ask_field, reask_field, confirm_ambiguous, show_recap, offer_slots,
         close_*, no_message, ...) + optional prefaces (answer_faq, ack_correction, redirect)
         + language + register. Never natural-language text.
```

- The **LLM layer** turns free text into `input` (extraction) and turns `action` into text (phrasing).
- **Timers and calendars** (008/010) send `event`s; they never mutate state directly.
- Structured values that need world knowledge are pre-digested by the extractor: `is_known_place` for locations, and start-date expressions (`asap`, `absolute`, `offset`, `next_weekday`). The engine does the deterministic part (matching, date arithmetic).

- `no_message` is an explicit action (e.g. after `silence_expired`), so channels never infer "don't send" from context.

## Alternatives considered
- **LLM returns the next question directly:** natural, but untestable and the flow can drift.
- **Engine returns text templates:** deterministic, but robotic, and every language/register needs duplicate templates.
- **Event-sourced engine (store inputs, rebuild state):** great audit trail, but too heavy now. The pure function makes it easy to add later: just persist inputs.

## Consequences
- The engine is 100% unit-testable without network; the same contract serves chat and voice.
- Adding a channel means writing an adapter, not touching the rules.
- The contract is a versioned boundary: changing an action type is a breaking change for 003/013.
