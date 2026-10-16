# Spec 010 — Interview scheduling: own agenda, capacity, reschedule/cancel, .ics (compact)

**Status:** Approved (Gerard, 2026-10-16: "Agenda propia + invitación .ics"; Google Calendar sync out of scope, documented as next step)
**Related:** spec 001 §6 (qualified → book in chat), spec 002 (scheduling stage, `slot_selected` / `no_slot_fits`, statuses), spec 004 (slot provider), spec 008 (scheduler loop, templates), spec 015 (waitlist), spec 016 (WhatsApp delivery), ADR 0005.

## 1. Why
Booking the interview inside the chat is what removes the phone call (the 60 % problem). Today the slots are fixed (3 days × 10:00/17:00) with **no capacity**: two candidates can take the same slot, recruiters can't say when they're free, and a candidate can't move the interview. That's fine for a demo, not for a product recruiters can start using.

## 2. Requirements
- FR-1 **Availability per city** in the DB, seeded once from `config/interview_slots.yaml` (extended): per city — weekdays, times, `capacity` per slot (interviewers in parallel), `duration_min`, interview `place` (address or "videollamada" + link placeholder), and how many working days ahead to offer. Editable in the dashboard ("Entrevistas → Disponibilidad"). Fictional addresses, clearly marked.
- FR-2 **Slots offered** = generated from the candidate's city availability, next N working days, starting tomorrow, minus slots already at capacity, spread across days (keep `max_slots: 3` and the current one-per-day rotation). Slot id is stable: `<city>:<YYYY-MM-DDTHH:MM>`.
- FR-3 **No double booking:** booking re-checks capacity atomically (inside the per-conversation lock + a DB uniqueness/count check). If the slot filled up meanwhile, Sofi says so ("Ese hueco se acaba de ocupar") and offers fresh slots; never books over capacity. If no slots at all → `qualified_unscheduled` (existing behaviour).
- FR-4 **Reschedule / cancel by chat** after booking: new extraction signals `reschedule_interview` and `cancel_interview` (prompt version bump). Reschedule → engine goes back to scheduling and the API offers fresh slots (the old one is released only when a new one is booked; if none fits, keep the old booking and say so). Cancel → booking released, status `qualified_unscheduled` with flag `interview_cancelled`, kind message. Engine change is minimal and documented as an ADR 0005 amendment (new signal handling in the `interview_scheduled` status).
- FR-5 **Calendar invite:** `GET /api/interviews/{conversation_id}.ics` → valid iCalendar (RFC 5545: VEVENT with UID, DTSTAMP, DTSTART/DTEND with the city timezone, SUMMARY "Entrevista Grupo Sazón — repartidor/a", LOCATION, DESCRIPTION; METHOD:PUBLISH). The confirmation message includes how to add it (web chat: an "Añadir al calendario" button under the banner; WhatsApp: a short link to the same URL when a public base URL is configured, else omitted). The recruiter can download it too.
- FR-6 **Reminder the day before** (reuse the spec 008 scheduler loop): at a configurable hour (e.g. 18:00 local) the day before, "Te recuerdo tu entrevista mañana a las 10:00 en <lugar>. Si no puedes, dime y la cambiamos." Once per booking, respects quiet hours, via the conversation's channel (web/WhatsApp; template outside 24 h for WhatsApp).
- FR-7 **Recruiter view** (Entrevistas page): week view per city with each slot's capacity and booked candidates (click → candidate drawer); mark an interview **asistió / no se presentó** → stored, shown in the drawer, analytics `interviews: {booked, attended, no_show, show_up_rate, rescheduled, cancelled}`; "Disponibilidad" tab to edit FR-1 settings.
- FR-8 Dashboard detail shows the booking (slot, place, .ics download, reschedule/cancel history).

## 3. Plan (for the implementer)
- Backend: `scheduling/` package (pure slot generation + capacity maths with injected `now`, fully unit-tested); DB tables `interview_availability`, `interview_bookings` (conversation_id, slot_id, starts_at, status booked|cancelled|attended|no_show, created/updated) with a capacity check; `api/routes/interviews.py` (.ics, availability GET/PATCH, attendance PATCH, week view GET). Replace the fixed slot provider behind the same interface the service already uses.
- Engine: minimal — handle the two new signals in `interview_scheduled` (and `qualified_unscheduled` for "quiero una cita" → scheduling again if desired: decide and document). Keep it pure; capacity is the API's job (it passes only bookable slots).
- LLM: extraction prompt version bump for the two signals; templates (es-ES/es-MX/en) for slot taken, reschedule offered, cancelled, reminder.
- Frontend: Entrevistas page week view + Disponibilidad tab + attendance buttons; chat "Añadir al calendario"; drawer booking block; analytics card.
- Trade-off: own agenda over Google/Outlook sync — zero setup, works offline and in the demo; real calendar sync (free/busy + event creation via OAuth) is the documented next step (ATS/calendar design doc).

## 4. Acceptance criteria
- AC-1 Slots offered come from the city's availability, skip weekends/past times, and never include full slots.
- AC-2 Capacity 1: two conversations confirming the same slot concurrently → exactly one booked; the other gets "slot taken" + fresh slots.
- AC-3 Reschedule by chat → new slots offered; picking one moves the booking and releases the old one; "none fits" keeps the old booking.
- AC-4 Cancel by chat → booking cancelled, status `qualified_unscheduled`, flag `interview_cancelled`, slot freed.
- AC-5 `.ics` is valid (parses with a strict parser or a structural test: required properties, CRLF line endings, timezone-correct times) for ES and MX cities.
- AC-6 Reminder sent once, the day before at the configured local hour, not in quiet hours, via the right channel.
- AC-7 Availability PATCH validates input (times HH:MM, capacity ≥ 1); changes affect newly offered slots only.
- AC-8 Attendance marking updates analytics `show_up_rate`.
- AC-9 (frontend) Week view, Disponibilidad tab, attendance buttons, chat "Añadir al calendario", drawer block.

## 5. Tasks
- [x] T1 Pure slot generation + capacity (AC-1, AC-7 logic).
- [x] T2 DB + booking with capacity check + slot-taken path (AC-2).
- [x] T3 Engine signals + extraction prompt + templates: reschedule/cancel (AC-3, AC-4).
- [x] T4 `.ics` endpoint (AC-5) + confirmation message link.
- [x] T5 Day-before reminder in the scheduler (AC-6).
- [x] T6 Interviews API: week view, availability, attendance, analytics (AC-7, AC-8).
- [ ] T7 Frontend (AC-9), seed with bookings across the coming week, README/ROADMAP.
