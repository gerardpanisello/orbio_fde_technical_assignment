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

## Amendments

### 2026-10-12: waitlist when the area is fully staffed (spec 015)
A breaking change to the contract, as the Consequences above anticipate:
- **Input:** `TurnContext.zone_full: bool` (default `false`). The caller (004) sets it from
  live staffing data when the candidate's area is at or above 100 % of its target. The
  engine reads it only when the recap is confirmed (entering scheduling).
- **Status:** `waitlisted` (closed, like `qualified_unscheduled`): qualified, no slots offered.
  Never a rejection: opt-out still works, later messages get `closed_ack`, and a post-close
  correction that would fail a hard rule goes to `needs_review` (as AC-26c).
- **Action:** `close_waitlisted(area_id)`. Phrased with a per-register template naming the area.
- **Scoring input:** `score_candidate(..., occupancy=)` / `build_record(..., occupancy=)` take the
  area's staffing ratio (current / target, `None` = no data) for the zone-demand factor. The
  engine still does no I/O: occupancy and `zone_full` are looked up by the caller.

Channels and phrasing (003, 013) must handle the new action; the message catalog's
startup check fails if a register has no `close_waitlisted` template.

### 2026-10-16: move or cancel a booked interview, and a slot taken meanwhile (spec 010)
Another breaking change, kept minimal. The engine still decides only the flow; which
slots are open and the booking itself stay with the caller (004/010).
- **Signals:** `reschedule_interview`, `cancel_interview` (extraction prompt v6). Read only
  where there is something to act on, before the closed-conversation handling:
  - `reschedule_interview` on `interview_scheduled` -> back to `in_progress` / scheduling
    with the slots the caller sent in `TurnContext.offered_slots`, minus the booked one
    (`offer_slots`, `reason: "reschedule"`). `selected_slot_id` keeps the booked slot until
    a new `slot_selected`: "none fits", running out of re-asks or `silence_expired` keep
    it (`keep_interview(slot_id)`, status back to `interview_scheduled`). A new pick sets
    flag `interview_rescheduled`. On `qualified_unscheduled` (e.g. after a cancel) the same
    signal offers slots again (`reason: null`): a qualified candidate asking for an
    interview gets one. While choosing a slot it re-offers fresh slots.
  - `cancel_interview` on `interview_scheduled` (or while moving it) -> `selected_slot_id =
    null`, status `qualified_unscheduled`, flag `interview_cancelled`, action
    `close_interview_cancelled`. While choosing a first slot it means "none fits". On any
    other status it changes nothing (normal handling).
  - `opt_out` still wins over both.
- **Event:** `slot_taken(slot_id, slot_ids)`. The caller sends it instead of the pick's
  `slot_selected` when storing the booking found the slot full (FR-3). From pending
  `slot`: `offer_slots` with `slot_ids` minus the taken (and the booked) one, `reason:
  "slot_taken"`; nothing open -> `keep_interview` (moving) or `qualified_unscheduled`.
- **Actions:** `keep_interview(slot_id)`, `close_interview_cancelled`; `offer_slots` gains
  `reason: null | "slot_taken" | "reschedule"`. Per-register templates for all of them.
- **Caller contract:** a booking is created when `selected_slot_id` changes to a new id and
  released when it changes to `null` (cancel, opt-out). The engine never offers the booked
  slot back, and `interview_scheduled` always has a `selected_slot_id`
  (property-tested invariants).
- **Re-asks:** a new offer (reschedule, re-booking) starts the slot re-ask counter again.
