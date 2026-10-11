# 001 — Process design: agreed product decisions (input for the design doc)

Captured 2026-10-11 during planning. These feed `process-design.md` (the Phase 1 deliverable).

## Flow
- **Knock-outs first:** greeting + privacy consent → name → age (18+) → driver's license (+ vehicle type) → city/zone → availability → preferred schedule → delivery experience → start date → confirmation of collected data → outcome.
- Fields given out of order or several at once are accepted (extraction fills any field); the engine only asks for what is still missing.

## Legal / trust
- Privacy notice + explicit consent in the first message (GDPR in Spain, LFPDPPP in Mexico). No consent → polite close, no personal data stored.
- **Age 18+** is a hard rule (not in the brief; justified as a real-world requirement).
- **Vehicle type** (motorbike / car / bicycle / e-bike) collected; determines which license is relevant (a cyclist may not need one → open question for the client).

## Outcomes
- **Disqualified** (no license where required, out of zone, under 18): kind, clear message; recruiter can override from the dashboard. Out-of-zone candidates may be kept in a "future zones" talent pool (open question).
- **Qualified:** agent offers 2–3 real interview slots in the chat and confirms one; appears in the recruiter calendar. Rationale: removes the phone call that 60% of candidates don't answer.
- Soft criteria (experience, availability, schedule, start date) → explainable score / priority, never rejection (ADR 0004).

## Silence / re-engagement
- **Fully configurable by the client, no hard-coded defaults** in code. Config holds: number of follow-ups, delay of each, message intent, and when to mark `abandoned`.
- The design doc will present a *suggested* starting configuration for the client to approve, and note the WhatsApp 24h session window constraint (template messages required after 24h).

## Persona
- Warm and efficient, own name, tuteo, short messages, one question per message, occasional emoji, ES-Spain vs ES-Mexico register, EN when the candidate writes English.

## Open questions for the client (to list in the doc)
- Does a bicycle courier need a license? Min age 18 in both countries?
- Exact service zones per location; keep out-of-zone candidates for future openings?
- Pay/conditions info the agent may share (FAQ scope).
- Who owns the interview calendar (per location manager vs central recruiters)?
- Follow-up cadence (number, delays, quiet hours): we propose 2h / 23h / 72h as a starting point.

## Review notes (reviewer subagent, v1 → v2)
Applied: exits for scheduling (`qualified_unscheduled`), override and corrections; abandoned/opt-out in diagram; do-not-contact list instead of "store nothing"; name regex allows accents/hyphens/apostrophes; experience sanity bound (≤ 40) instead of untestable `age − 16`; Spanish gender agreement ("la asistente"); one question in greeting; 24h-window slip rule; trimmed to ~2 pages.
