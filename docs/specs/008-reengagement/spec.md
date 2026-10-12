# Spec 008 — Re-engagement: follow-ups when a candidate goes silent (compact)

**Status:** Approved (2026-10-12)
**Related:** spec 001 §5 ("Stops responding": client-configured schedule, quiet hours, WhatsApp 24 h window, `abandoned` after the last one), spec 002 (`silence_expired` event, `drop_off_stage`), decisions.md ("configurable, no hard-coded defaults").

## 1. Why
60% of candidates don't answer a phone call. In chat many will start and stall halfway. A well-timed, short reminder that picks up exactly where they left recovers part of them at almost zero cost; without it every stall becomes a lost candidate.

## 2. Requirements
- FR-1 **Config, not code** (`config/reengagement.yaml`): `enabled`, list of follow-ups each with `after` (duration since the candidate's last message, e.g. `2h`, `23h`, `72h`) and `kind` (`nudge` | `last_call`), `abandon_after` (after the last follow-up), `quiet_hours` (`22:00–09:00`, evaluated in the city's timezone, else the country's default), and `whatsapp_window_hours: 24`. Shipped values = the suggested starting point from spec 001 (2 h, 23 h, 72 h, abandon 24 h after the last one), labelled as such. Validated at startup.
- FR-2 **Who is eligible:** conversations `in_progress` whose last message is from the agent (we are waiting for the candidate). Any candidate message resets the cycle. Closed statuses never get follow-ups. Opted-out never.
- FR-3 **Follow-up message:** short (≤ 300 chars), picks up the **pending question** ("¿Seguimos? Solo nos faltan 3 preguntas: ¿qué disponibilidad tienes?"), mentions progress, no pressure, last one says it's the last reminder. Phrased by the LLM with a template fallback (ADR 0006); fake mode uses the template. Follow-ups that would be sent after the WhatsApp 24 h window are marked `requires_template: true` (in production they must use an approved WhatsApp template; here they are sent as the template text).
- FR-4 **Quiet hours:** a follow-up due inside quiet hours is postponed to the end of the quiet period (local time). If postponing pushes it past the 24 h window, it becomes a template follow-up.
- FR-5 **Abandon:** `abandon_after` past the last follow-up with no reply → engine event `silence_expired` → `abandoned` (engine records `drop_off_stage`), no message.
- FR-6 **Resume:** a reply at any time (even after `abandoned`) resumes the conversation (engine already supports it). Record which follow-up (if any) the candidate came back after.
- FR-7 **Scheduler:** an in-process periodic task in the API (lifespan), every `tick_seconds`, finds due follow-ups and sends them; uses the same per-conversation lock as messages so a candidate reply and a follow-up never race. Idempotent: a follow-up step is sent at most once (stored per conversation).
- FR-8 **Demo controls:** `REENGAGEMENT_TIME_SCALE` env (e.g. `60` = 1 h passes in 1 min) for live demos; dev endpoint `POST /api/dev/conversations/{id}/advance` runs the **next** step immediately (next follow-up, or abandon), replacing/complementing the existing `/silence`.
- FR-9 **Visibility:** follow-up messages are stored as agent messages with `kind: "follow_up"` + step number; the chat shows them (polls while open); candidate detail shows follow-ups sent and whether the candidate came back; `GET /api/analytics` adds `reengagement: {follow_ups_sent, conversations_nudged, reactivated, reactivation_rate, by_step: [{step, sent, reactivated}]}`.

## 3. Plan
- `backend/src/sazon_screening/reengagement/` — `config.py` (models + loader), `policy.py` (**pure**: given last candidate message time, steps already sent, timezone, now → next action `send(step, at, requires_template) | abandon(at) | none`; all time maths here, fully unit-tested with injected `now`), `scheduler.py` (API loop: query eligible conversations, apply policy, send via the agent's phraser, persist).
- LLM: follow-up phrasing via a new templates group in `config/messages/*.yaml` (`follow_up.nudge`, `follow_up.last_call`) + the existing phrasing call with the pending ask as context (prompt version bump if needed).
- DB: `conversations.last_candidate_at`, `follow_ups_sent` (int), `reactivated_after_step` (nullable); messages gain `kind`.
- Engine: unchanged (pure); only `silence_expired` is used.
- Trade-off: in-process scheduler is fine for one instance and the demo; production = a scheduler service / delayed queue with a DB lock (see `docs/design/deployment.md`).

## 4. Acceptance criteria
- AC-1 Policy: last candidate message at 10:00, steps 2 h/23 h/72 h → first follow-up due 12:00; nothing before; second at 09:00 next day (23 h) unless quiet hours.
- AC-2 Quiet hours: a follow-up due at 23:30 local is postponed to 09:00 local; Mexico City and Madrid use their own timezones.
- AC-3 Past the 24 h window → `requires_template: true`.
- AC-4 After the last follow-up + `abandon_after` → `abandoned` with the right `drop_off_stage`, no message.
- AC-5 A candidate reply after follow-up 2 resumes at the pending question; `reactivated_after_step = 2`; no more follow-ups until they go silent again.
- AC-6 Closed, opted-out or candidate-last conversations never receive follow-ups; a step is never sent twice (idempotent under two concurrent ticks).
- AC-7 Follow-up text ≤ 300 chars, mentions the pending question; falls back to the template on LLM failure.
- AC-8 `advance` dev endpoint runs exactly the next step; analytics `reengagement` numbers add up.
- AC-9 (frontend) Chat shows follow-ups arriving (polling); live panel "Avanzar tiempo" button; detail shows follow-ups; analytics card "Re-engagement".

## 5. Tasks
- [x] T1 Config + pure policy + tests (AC-1..AC-4).
- [x] T2 Templates + follow-up phrasing (AC-7).
- [x] T3 DB fields + scheduler loop + lock + idempotency + resume tracking (AC-5, AC-6).
- [x] T4 Dev `advance` endpoint, time scale, analytics (AC-8); seed a few nudged/reactivated conversations.
- [ ] T5 Frontend (AC-9) — separate agent.
- [ ] T6 README/ROADMAP/process-design note.
