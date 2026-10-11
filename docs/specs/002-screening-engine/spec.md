# Spec 002 — Screening engine (deterministic core)

**Status:** Reviewed (open questions decided with Gerard, 2026-10-11)
**Related:** ADR-0005 (turn contract), ADR-0002 (hybrid state machine), ADR-0004 (hard rules + soft scoring), Spec 001 ([process-design.md](../001-process-design/process-design.md), the source of truth)

## 1. Problem / Why
80% of recruiter time goes to candidates who cannot be hired. Spec 001 fixes that with knock-out questions first and ranked, pre-booked candidates. For the client to trust and audit those outcomes, every decision (what to ask next, whether an answer is valid, whether someone is disqualified, how they are ranked) must be **deterministic, configurable and testable without an LLM** (ADR 0002). This spec defines that core. The LLM layer (003), API (004), re-engagement (008), FAQ (009) and scheduling (010) all plug into it.

## 2. User stories
- As a **candidate**, I want to be asked only for what is still missing, in any order I give it, and never be rejected because my answer was misunderstood.
- As a **recruiter**, I want every outcome to come with a clear reason, an explainable priority and a structured record, so I call the best candidates first and can defend every rejection.
- As **Grupo Sazón ops**, I want to change service areas, license rules and scoring weights in a config file, without touching code or prompts.

## 3. Requirements

### Functional — turn contract
- **FR-1** The engine is a pure function of `(state, turn input, config, today)` → `(new state, next action)`. It reads no clock, network or storage.
- **FR-2** Turn input = zero or more **proposed field values** (each either a typed value or the marker `unclear`) plus **signals**: `opt_out`, `wants_human`, `correction`, `faq_question`, `language` (es/en), `off_topic`, `abuse`, `extraction_failed`. Context: `country_hint` (e.g. from the phone prefix), optional `offered_slots`.
- **FR-3** The engine also accepts out-of-band **events**: `silence_expired` (from 008) and `slot_selected` / `no_slot_fits` (from 010).
- **FR-4** Output = exactly **one primary action** plus optional **prefaces**, never natural-language text. Primary actions: `ask_field`, `reask_field(reason, options)`, `confirm_ambiguous(options)`, `confirm_value`, `ask_correction_field`, `show_recap`, `offer_slots`, `close_disqualified(reason)`, `close_needs_review`, `close_opted_out`, `close_qualified_unscheduled`, `confirm_interview`, `handoff_to_human`, `closed_ack`. Prefaces: `answer_faq`, `ack_correction`, `redirect`. Every action carries the current `language` and `register` (es-ES / es-MX / en). One question per action (Spec 001 §7).

### Functional — flow & state
- **FR-5** Stages, in order: consent → name → age → vehicle + license → location → availability → schedule → experience → start date → recap → scheduling. Statuses: `in_progress`, `interview_scheduled`, `qualified_unscheduled`, `disqualified`, `needs_review`, `abandoned`, `opted_out`.
- **FR-6** State always exposes `stage`, `pending_field`, per-field re-ask counts, `status`, `drop_off_stage`, `language`, flags — enough for 008 to resume and for 011 to report drop-off.
- **FR-7** Consent requires an explicit yes. Proposals in the **same turn** as consent = true are applied (after consent). Proposals received while consent is not given are discarded. A decline closes as `opted_out` with no screening data in the record.
- **FR-8** Out-of-order and multi-field input is accepted in any stage; the engine asks only for missing fields, knock-outs before profile. Within a turn, proposals are validated in stage order.
- **FR-9** A proposal for an already-filled field **overwrites** it (latest wins) and all hard rules are re-evaluated. With the `correction` signal, the action carries `ack_correction`.
- **FR-10** Precedence per turn: `opt_out` > `abuse` > apply proposals & hard rules (disqualification) > `wants_human` > `faq_question` > next ask.
- **FR-11** `opt_out` is honoured in every stage and every status, including after an interview is booked. On opt-out all screening field values are **purged**; the record keeps only `status`, `drop_off_stage`, `language` and the `do_not_contact` flag (GDPR / LFPDPPP data minimisation).
- **FR-12** `wants_human` → status `needs_review`, flag `human_requested`, action `handoff_to_human`; later turns return `closed_ack` (or `answer_faq`) until a recruiter acts (outside this spec).
- **FR-13** `faq_question` → preface `answer_faq`, then resume the pending field (FAQ content is 009's job).
- **FR-14** `silence_expired` → `abandoned` with `drop_off_stage` + `pending_field`, except in scheduling, where it yields `qualified_unscheduled` (never `abandoned`, Spec 001 §6). Any later turn on an `abandoned` conversation resumes it at the pending field as `in_progress`.
- **FR-15** Turns on a closed conversation (`disqualified`, `interview_scheduled`, `qualified_unscheduled`, `needs_review`) do not change screening data; they return `answer_faq` or `closed_ack`. Exception: a correction **after disqualification** to the field that caused it is stored as a proposed value next to the original (not applied), status moves to `needs_review` with flag `post_close_correction`, and the action is `close_needs_review`. It never auto-requalifies (prevents gaming); a recruiter decides.

### Functional — validation (per Spec 001 §4)
- **FR-16 Name:** ≥ 2 words; letters incl. accents, spaces, hyphens, apostrophes. First name only → ask for surname once, then accept + flag `surname_missing`. Name is required but **not qualifying**: if still unclear after re-asks, continue + flag `name_unclear`.
- **FR-17 Age:** `is_adult` bool and/or `age` int. Age below the configured minimum (default 18) or `is_adult = false` → disqualify `under_age`. Implausible age (e.g. > 99) → re-ask.
- **FR-18 Vehicle & license:** vehicle ∈ {motorbike, car, bicycle, e_bike, none}. Whether a license is required per vehicle type comes from config (default: all). License is asked only if required for the vehicle; if not required, stored as `not_required`. A "no license" answer given before the vehicle is known disqualifies (`no_license`) only if **every** vehicle type requires one; otherwise it waits for the vehicle.
- **FR-19 Location:** raw location text is matched against config service areas by exact name, alias, then fuzzy match (configurable threshold, accent/case-insensitive) → `country`, `city`, `zone` IDs.
  - Matches ≥ 2 areas → narrow with `country_hint`; if still > 1 → `confirm_ambiguous(options)`.
  - City matched and served, zones defined but none given → ask zone.
  - City matched but zone not served → disqualify `out_of_area`.
  - A location proposal carries `is_known_place` (set by the extractor: is this text a real place?).
  - Not matched **and** `is_known_place = true` (e.g. "Zaragoza") → disqualify `out_of_area` immediately.
  - Not matched **and** `is_known_place = false` (typo, gibberish) → treated as `unclear`: `reask_field(reason=not_recognised)` listing served cities, under the normal re-ask policy (FR-23/24) → exhausted → `needs_review`. Ambiguity never disqualifies.
- **FR-20 Availability / schedule:** non-empty set of {full_time, part_time, weekends} / {morning, afternoon, evening, flexible}; otherwise re-ask with options.
- **FR-21 Experience:** years int ≥ 0 ("none" = 0, empty platforms); > 40 → `confirm_value`; negative → re-ask. Platforms normalised to config IDs; unknown → `other:<text>`.
- **FR-22 Start date:** the engine receives a **structured date expression**, not free text and not only an absolute date: one of `asap`, `absolute(ISO date)`, `offset(n days|weeks)`, `next_weekday(mon…sun)`. It resolves it against the injected `today`. Past dates → `today` + flag `start_date_normalised`. *Why:* turning "el lunes" into a structure is language understanding (LLM); calendar arithmetic is deterministic and the LLM gets it wrong (which Monday? today is Monday?). Keeping arithmetic in code makes it testable and auditable.

### Functional — re-ask, recap, scheduling
- **FR-23** At most **2 re-asks per field** (3 attempts total), each with a reason code and options where the field is closed. A turn increments the counter only if it carries an `unclear`/invalid value for the pending field, or nothing at all. FAQ-only turns, turns that fill other fields, and `extraction_failed` turns do not count.
- **FR-24** Exhausted **soft** field (availability, schedule, experience, start date) → stored `unclear`, continue. Exhausted **hard** field (age, license, location; vehicle only when it decides whether a license is needed) → stored `unclear`, continue collecting the profile, then at recap → `needs_review`. **Ambiguity never disqualifies**; a later clear hard-rule failure still disqualifies.
- **FR-25** Recap: `show_recap` with all values. Yes → re-check hard rules → `offer_slots`. A correction → apply (FR-9) → re-check → re-show recap or disqualify. "No" without detail → `ask_correction_field`. Loop guard: after a configurable number of recap rounds → `needs_review`.
- **FR-26** Scheduling: `offer_slots` (slots supplied by the caller). A valid `slot_selected` id → `interview_scheduled` + `confirm_interview`. An id not offered → re-ask policy; exhaustion or `no_slot_fits` → `qualified_unscheduled`.
- **FR-27** `extraction_failed` → re-ask the pending field without consuming a re-ask; after a configurable number of consecutive failures → `needs_review`, flag `system_failure`.
- **FR-28** `off_topic` or first `abuse` → preface `redirect`, resume. Repeated `abuse` (configurable count) → `needs_review` + flag `abuse` + `close_needs_review`.

### Functional — config, scoring, output
- **FR-29 Config (YAML, client-editable, validated at load):** service areas (country → city → zones, each with ID, display names per language, aliases, timezone); fuzzy threshold; license-required-by-vehicle map; minimum age per country; known platforms; max re-asks; recap and failure loop guards; scoring weights and bucket thresholds; a config version. Invalid config (duplicate IDs, unknown vehicle types, missing weights, thresholds out of order) fails fast with a clear error.
- **FR-30 Scoring:** computed only from soft fields (experience years, platforms, availability breadth, schedule flexibility, start-date proximity) using config weights. Output: numeric score, bucket (high / medium / low), and a list of **factors** `{field, value, points, reason_code}` whose points sum to the score. `unclear` fields contribute 0 and appear as factor `unknown`. Produced for `interview_scheduled`, `qualified_unscheduled` and `needs_review`; `null` otherwise.
- **FR-31 Candidate record:** JSON-serialisable, with every screening field (value + status: `valid` | `unclear` | `not_asked` | `not_required`), `status`, `disqualification_reason` (`under_age` | `no_license` | `out_of_area` | null), `needs_review_reasons`, `score`, `flags`, `language`, `drop_off_stage`, `selected_slot_id`, `config_version`. All values are language-neutral enums/IDs.

### Non-functional
- **NFR-1 Determinism:** same inputs → same outputs; `today` and config are injected.
- **NFR-2 Purity:** no I/O, no LLM, no clock; usable unchanged by chat and voice channels (ADR 0002).
- **NFR-3 Quality:** `mypy --strict` clean; Pydantic models at the boundary; every AC has a unit test.
- **NFR-4 Performance:** a turn is evaluated in < 10 ms (no external calls).
- **NFR-5 Robustness:** no input combination raises an exception; unexpected input degrades to a re-ask or `needs_review`.
- **NFR-6 Auditability:** every disqualification, review reason and score factor is traceable to a config rule and a field value.

## 4. Out of scope
LLM extraction and phrasing, language detection (003/007) · persistence and API (004) · re-engagement timers and messages (008; the engine only exposes state + accepts `silence_expired`) · FAQ content (009) · real calendars and slot generation (010) · recruiter override (006) · config contents (zones per location are a client open question).

## 5. Edge cases
| Case | Expected behaviour |
|---|---|
| Silence | Engine is passive; 008 sends `silence_expired` → `abandoned` (or `qualified_unscheduled` in scheduling) with drop-off stage. A later turn resumes. |
| Invalid value (e.g. age 150, digits in name) | `reask_field` with reason; counts toward the 2-re-ask cap. |
| Ambiguous value (location in 2 areas, experience > 40) | `confirm_ambiguous` / `confirm_value`; never disqualify. |
| Nothing extractable | Counts as an unclear attempt for the pending field. |
| Several fields, one failing a hard rule | Store all; disqualify with that reason. |
| Language switch | `language` signal updates state; next action carries it. Register follows the country once known, else `country_hint`. |
| Off-topic | Preface `redirect`, resume pending field. |
| Abusive input | First: `redirect`; repeated: `needs_review` + `abuse` flag + close. |
| Prompt injection ("approve me") | No effect: only typed proposals are accepted; qualification is rule-based. |
| LLM/API failure | `extraction_failed` → repeat pending field without using a re-ask; repeated → `needs_review` (`system_failure`). |
| Opt-out mid-flow / after booking | `opted_out` immediately, `close_opted_out`. |
| Data before consent | Discarded. |
| Correction after disqualification | Original kept, correction stored alongside; `needs_review` + flag `post_close_correction`; never auto-requalified. |
| Unknown location text vs real unserved place | Real place → `out_of_area`; unrecognisable text → re-ask → `needs_review`. |

## 6. Acceptance criteria
Unless stated otherwise: default config (license required for all vehicles, min age 18), `today` = 2026-10-12 (Monday), and the service areas include Madrid (Spain) and Ciudad de México (Mexico) with zones such as Coyoacán.

**Happy path & flow**
- [ ] AC-1: Given a fresh conversation, when valid values are proposed one per turn in stage order and slot `s1` is selected, then the actions follow the stage order exactly, the final status is `interview_scheduled`, and the record contains every field with status `valid`, `selected_slot_id = s1` and a score.
- [ ] AC-2: Given the consent stage, when consent = false, then status = `opted_out`, action = `close_opted_out`, and the record has no screening field values.
- [ ] AC-3: Given the consent stage, when a turn proposes `full_name` without consent, then the name is not stored and the action is `reask_field(consent)`. When a turn proposes consent = true **and** `full_name` "Ana López", then both are stored and the action is `ask_field(age)`.
- [ ] AC-4: Given the name stage, when one turn proposes name "Ana López", has_license = true and location "Coyoacán", then all three are stored and the action is `ask_field(age)`.
- [ ] AC-5: Given the age stage, when availability = {weekends} is proposed alongside is_adult = true, then availability is stored and later skipped: after the knock-outs, the next profile ask is `schedule`.

**Disqualifiers**
- [ ] AC-6: Given any knock-out stage, when age = 17 is proposed (even together with other valid fields), then status = `disqualified`, reason = `under_age`, action = `close_disqualified(under_age)`, and the other fields are kept in the record.
- [ ] AC-7: Given vehicle = motorbike, when has_license = false, then the candidate is disqualified with reason `no_license`.
- [ ] AC-8: Given config where bicycle does not require a license, when vehicle = bicycle, then license is not asked, is stored as `not_required`, and the next action is `ask_field(location)`.
- [ ] AC-9: Given that bicycle config and vehicle unknown, when has_license = false, then the candidate is not disqualified and the action is `ask_field(vehicle_type)`; when vehicle = motorbike follows, then the candidate is disqualified (`no_license`).
- [ ] AC-10: Given city Madrid with configured zones, when location is a Madrid zone not in the list, then the candidate is disqualified with reason `out_of_area`.
- [ ] AC-11: Given the location stage, when "Zaragoza" is proposed with `is_known_place = true`, then the candidate is disqualified (`out_of_area`). When "xjkq" is proposed with `is_known_place = false`, then the action is `reask_field(location, reason=not_recognised)` with the served cities as options, and after the re-asks are exhausted the outcome at recap is `needs_review` (never `disqualified`).

**Location matching**
- [ ] AC-12: Given aliases, when the location is "CDMX", "coyoacan" or "Cuyoacán", then it resolves to the Ciudad de México / Coyoacán IDs.
- [ ] AC-13: Given a name configured in two service areas and no `country_hint`, when it is proposed, then the action is `confirm_ambiguous` listing both; given `country_hint` matches one of them, then it resolves without asking.
- [ ] AC-14: Given a city with zones, when only the city is proposed, then the action is `ask_field(zone)`.

**Field validation**
- [ ] AC-15: Given the name stage, when "Ana" is proposed, then the action is `reask_field(full_name, reason=surname_missing)`; when "Ana" is proposed again, then it is stored, flag `surname_missing` is set, and the flow continues.
- [ ] AC-16: Given the experience stage, when years = 45, then the action is `confirm_value(experience)`; when confirmed, then 45 is stored. When years = "none", then years = 0 and platforms = []. When a platform is "Rappi Turbo" (not in config), then it is stored as `other:Rappi Turbo`.
- [ ] AC-17: Given today = 2026-10-12, when the start date is `next_weekday(mon)` → 2026-10-19; `offset(2 weeks)` → 2026-10-26; `asap` → 2026-10-12; `absolute(2026-09-01)` → 2026-10-12 + flag `start_date_normalised`.

**Re-ask policy**
- [ ] AC-18: Given the availability stage, when three consecutive turns propose `unclear`, then the 2nd and 3rd actions are `reask_field` with options, availability is then stored as `unclear`, and the next action is `ask_field(schedule)`.
- [ ] AC-19: Given the location stage, when three consecutive turns are unclear, then location is `unclear`, the profile is still collected, and at recap the status is `needs_review` with reason `location_unclear` and action `close_needs_review`. The status is never `disqualified`.
- [ ] AC-20: Given a pending field with 1 re-ask used, when a turn contains only a FAQ question, only other valid fields, or `extraction_failed`, then the re-ask count stays at 1.

**Corrections & recap**
- [ ] AC-21: Given city = Madrid stored during the profile stage, when a `correction` proposes "Coyoacán", then the location is overwritten, the hard rules pass, and the action carries the `ack_correction` preface plus the pending field ask.
- [ ] AC-22: Given the recap stage, when the candidate confirms, then the action is `offer_slots`.
- [ ] AC-23: Given the recap stage, when a correction changes availability, then the new value is stored and `show_recap` is returned with it.
- [ ] AC-24: Given the recap stage, when a correction changes location to an unserved zone (or license to false), then status = `disqualified` with the matching reason.
- [ ] AC-25: Given the recap stage, when the candidate says "no" without naming a field, then the action is `ask_correction_field`.

**Signals & events**
- [ ] AC-26: Given each stage and each non-opted-out status (parametrised, including `interview_scheduled`), when `opt_out` is received (even with proposals), then status = `opted_out`, action = `close_opted_out`, all screening field values are purged, and the record keeps `drop_off_stage` and flag `do_not_contact`.
- [ ] AC-26b: Given a candidate disqualified for `no_license`, when a `correction` proposes has_license = true, then status = `needs_review`, flag `post_close_correction`, the original value and the proposed correction are both in the record, and the action is `close_needs_review`.
- [ ] AC-27: Given an in-progress conversation, when `wants_human` is received, then status = `needs_review`, flag `human_requested`, action = `handoff_to_human`; a later turn returns `closed_ack`.
- [ ] AC-28: Given pending field = schedule, when `faq_question` is received alone, then the action is `ask_field(schedule)` with preface `answer_faq`; when it comes with a valid schedule, then the preface is `answer_faq` and the ask is the next field.
- [ ] AC-29: Given pending field = vehicle_type, when `silence_expired`, then status = `abandoned`, `drop_off_stage = vehicle_license`; when a later turn arrives, then status = `in_progress` and the action is `ask_field(vehicle_type)`. Given the scheduling stage, when `silence_expired`, then status = `qualified_unscheduled`.
- [ ] AC-30: Given `offer_slots` with ids {s1, s2}, when `slot_selected(s9)` arrives, then the action is `reask_field(slot)`; when `no_slot_fits` arrives, then status = `qualified_unscheduled`.
- [ ] AC-31: Given the configured threshold N of consecutive `extraction_failed` turns, when N is reached, then status = `needs_review` with flag `system_failure`. Given the abuse threshold, the first `abuse` returns a `redirect` preface and reaching the threshold closes as `needs_review` with flag `abuse`.
- [ ] AC-32: Given `language = en`, then the next action has `language = en`; given city = Ciudad de México and language = es, then `register = es-MX`.

**Scoring, config, output**
- [ ] AC-33: Given fixed weights and a candidate (3 years, glovo, {full_time, weekends}, flexible, asap), then the score equals the sum of the factor points, the bucket matches the configured thresholds, and each factor names its field, value and reason code. Given availability `unclear`, then that factor has 0 points and reason `unknown`.
- [ ] AC-34: Given the same candidate, when only the YAML weights change, then the score/bucket changes with no code change; disqualified and opted-out records have `score = null`.
- [ ] AC-35: Given an invalid config (duplicate zone ID, unknown vehicle type, or bucket thresholds out of order), when it is loaded, then it fails with an error naming the problem.
- [ ] AC-36: Given any final record (one per status), when it is serialised with `json.dumps` and validated against the record schema, then it succeeds and contains all FR-31 keys with language-neutral values.

## 7. Decisions (resolved open questions, 2026-10-11)
| # | Question | Decision |
|---|---|---|
| 1 | Start-date contract | Structured expression resolved by the engine (FR-22). |
| 2 | Bicycle license / no vehicle | Config default: license required for all vehicles; `vehicle = none` accepted (not a disqualifier). *Assumption, to confirm with client.* |
| 3 | Minimum age | 18 in both countries, per-country config. *Assumption, to confirm with client.* |
| 4 | Unrecognised location | Real place → `out_of_area`; unrecognisable → re-ask → `needs_review` (FR-19). Talent pool: out of scope. |
| 5 | Data before consent | Applied only if consent is in the same turn (FR-7). |
| 6 | Mid-flow opt-out | Purge fields, keep minimal data + do-not-contact (FR-11). |
| 7 | Correction after disqualification | `needs_review` + flag, never auto-requalify (FR-15). |
| 8 | Confirm before disqualifying | No (the extractor only proposes a clear `false`; ambiguity is already `unclear`). |
| 9 | `wants_human` | Pause screening (FR-12). |
| 10 | Abuse close | `needs_review` + `abuse` flag, no new status. |
| 11 | Default thresholds (config) | Max re-asks 2 · recap rounds 3 · consecutive extraction failures 3 · abuse count 2 · fuzzy match ≥ 85/100. |
| 12 | Turn contract ADR | Yes → [ADR 0005](../../adr/0005-engine-turn-contract.md). |
