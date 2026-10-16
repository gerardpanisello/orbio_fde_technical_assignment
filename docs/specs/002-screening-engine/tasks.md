# Tasks 002 — Screening engine (deterministic core)

**Implements:** [plan.md](plan.md) · [spec.md](spec.md)

Rules:
- Each task is small (< ~1h) and **test-first**: write the listed tests, see them fail, then implement.
- Each task ends with **all checks green**. Run this in `backend/`:
  `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q`
- Every new test carries `@pytest.mark.ac("AC-n")` when it covers an AC (registered in T1).
- One implementer works top to bottom. Each task only depends on the ones above it.
- Paths are relative to `backend/` unless they start with `config/` or `docs/` (repo root).
- Open questions OQ-1…OQ-7 (plan §8): implement the documented default and do not block.

## A. Foundations & config

- [x] **T1 — Skeleton & tooling.**
  - `uv add tzdata` and `uv add --dev hypothesis`.
  - Create the packages `src/sazon_screening/config/` and `src/sazon_screening/engine/` (empty `__init__.py`).
  - Create `tests/config/`, `tests/engine/` and `tests/fixtures/config/`.
  - In `pyproject.toml`, register the marker under `[tool.pytest.ini_options]`: `markers = ["ac(id): acceptance criterion covered by this test"]`.
  - Test: `tests/engine/test_imports.py` imports both packages.
  - *(NFR-3)*
  - *Note (impl):* `tests/`, `tests/config/` and `tests/engine/` are packages (`__init__.py`) so helpers import as `tests.engine.builders`; shared paths live in `tests/paths.py`.

- [x] **T2 — Enums & flow tables.**
  - `engine/enums.py`: all enums in plan §3.1.
  - `engine/flow.py`: `FIELD_ORDER`, `FIELD_STAGE`, `HARD_FIELDS`, `SOFT_FIELDS`. Do not write `next_missing_field` yet.
  - Tests `tests/engine/test_flow_tables.py`:
    - the stage order matches FR-5;
    - every `FieldName` has a stage;
    - `FIELD_STAGE[vehicle_type] == FIELD_STAGE[has_license] == Stage.vehicle_license` (the AC-29 drop-off value);
    - hard and soft sets are disjoint.
  - *(FR-5, FR-6)*

- [x] **T3 — Service-area config models.**
  - `config/models.py`: `Area`, `Zone`, `City`, `CountryArea`, `ServiceAreasConfig`, with validators for:
    - slug ids;
    - ids unique across the whole file;
    - `ZoneInfo(timezone)` loads;
    - no duplicate normalised name/alias inside one city.
  - A temporary local `normalise()` is fine. Move it to `engine/location.py` in T11 and import it from there.
  - Tests `tests/config/test_models.py`:
    - a valid minimal dict passes;
    - duplicate zone id → error naming the id (**AC-35**);
    - bad timezone → error;
    - the same zone name in two cities is allowed.
  - *(FR-29)*
  - *Note (impl):* `Area` holds `names`/`aliases` only; `Zone`/`City` declare `id: Slug` and `CountryArea` declares `id: Country` (overriding a field type in a subclass is rejected by mypy strict). `names` must cover every `Language`.

- [x] **T4 — Screening config models + EngineConfig.**
  - `Platform`, `Thresholds` (spec §7 #11 defaults), `StartDateBand`, `ScoringConfig`, `ScreeningConfig`, `EngineConfig` (frozen, `version` property, cross-file `min_age` coverage check).
  - The `license_required` validator rejects unknown vehicle types and missing ones, with a named message.
  - Tests:
    - unknown vehicle `scooter` → error naming it (**AC-35**);
    - missing `e_bike` → error;
    - buckets `high <= medium` → error (**AC-35**);
    - start-date bands not increasing → error;
    - missing availability weight → error;
    - `min_age` missing a configured country → error;
    - threshold defaults equal spec §7 #11.
  - *(FR-29)*
  - *Note (impl):* availability weights are explicit fields of `AvailabilityScoring` (flat YAML stays as in plan §3.11; a test checks they cover the enum). Extra fail-fast checks added: unique platform ids, `min_plausible_age < max_plausible_age`, `default_country` must be configured. Helpers: `ScreeningConfig.requires_license(vehicle)`, `EngineConfig.thresholds`, `ScoringConfig.max_score`.

- [x] **T5 — Loader + test fixture config.**
  - `config/loader.py`: `ConfigError` and `load_config(config_dir: Path) -> EngineConfig`, using `yaml.safe_load`. Pydantic errors are re-formatted as `"<file>: <dotted.path>: <msg>"`. A missing file and invalid YAML also produce `ConfigError`.
  - Create the small fixture YAMLs in `tests/fixtures/config/`:
    - Madrid with zones Centro, Chamberí, Salamanca;
    - CDMX with Coyoacán, Cuauhtémoc (alias Roma) and Centro;
    - Barcelona with no zones;
    - "El Carmen" in Valencia (ES) and Monterrey (MX);
    - all platforms;
    - default thresholds and weights from plan §3.11.
  - `tests/engine/conftest.py` fixtures: `config`, `bike_free_config`, `today`, `make_config(**overrides)`.
  - Tests `tests/config/test_loader.py`:
    - the fixture loads;
    - a broken copy written to `tmp_path` raises `ConfigError` whose message contains the file name and the path (**AC-35**);
    - a missing file raises `ConfigError`.
  - *(FR-29)*
  - *Note (impl):* `make_config` / `bike_free_config` re-validate `EngineConfig` from a deep-merged `model_dump` instead of `model_copy`, so every validator (and the location index built in T11) applies to variants too. Cross-file errors are reported under `screening.yaml`.

- [x] **T6 — Shipped client config.**
  - Write the full `config/service_areas.yaml`:
    - Spain: Madrid, Barcelona, Valencia, Sevilla, Málaga;
    - Mexico: Ciudad de México, Guadalajara, Monterrey, Puebla;
    - 4–6 real zones each, names in es/en, aliases and timezones;
    - "El Carmen" in Valencia and Monterrey; "Centro" in several cities.
  - Write the full `config/screening.yaml` (plan §3.11).
  - Add a header comment to each file explaining what ops can edit.
  - Tests `tests/config/test_shipped_config.py`:
    - it loads;
    - it contains `madrid` and `cdmx-coyoacan`, and the aliases CDMX/DF/BCN/MTY/GDL;
    - "El Carmen" is in two countries;
    - all 7 platform ids are present;
    - `license_required` covers every `VehicleType`.
  - *(FR-29)*

## B. Boundary models

- [x] **T7 — Inputs.**
  - `engine/inputs.py`: `Unclear`/`UNCLEAR`, `StartDateExpr` union, `AgeAnswer` (at least one of `is_adult`/`age`), `LocationAnswer`, `ExperienceAnswer`, the 12 proposal models, the `Proposal` union, `Signals`, `TurnContext`, `CandidateTurn`, `SilenceExpired`, `SlotSelected`, `NoSlotFits`, `TurnInput`.
  - Tests `tests/engine/test_inputs.py`:
    - parse from plain dicts, the way 003 will send them (each proposal type, `{"kind": "unclear"}` values, each start-date kind);
    - a `TurnInput` JSON round-trip;
    - unknown field or extra keys → `ValidationError`;
    - `TypeAdapter(TurnInput).json_schema()` builds.
  - *(FR-2, FR-3, FR-22, ADR 0005)*
  - *Note (impl):* `Unclear.kind` has no default (`UNCLEAR = Unclear(kind="unclear")`): otherwise an empty `{}` from the LLM would silently parse as an unclear answer. Proposal and start-date models default their `field`/`kind`, so `NameProposal(value=...)` and `Asap()` work in builders. `StartDateProposal.value` is one discriminated union that includes `Unclear`.

- [x] **T8 — State & actions.**
  - `engine/state.py`: `Slot[T]`, `LocationValue`, `Experience`, `Profile`, `AreaRef`, `PendingAsk`, `PostCloseCorrection`, `ConversationState`, and the helpers `add_flag` / `add_reason` (sorted/ordered unique).
  - `engine/actions.py`: all primary actions, prefaces, `EngineAction`, and `register_for()`.
  - Tests `tests/engine/test_state_actions.py`:
    - a default state JSON round-trip;
    - `add_flag` stays sorted and unique;
    - every action type serialises with its `type` tag;
    - `register_for` table: en→en; es + MX→es-MX; es + no country + hint MX→es-MX; es + nothing→default (**AC-32**, unit).
  - *(FR-4, FR-6)*
  - *Note (impl):* `NoMessage` (`no_message`) added per the OQ-2 decision. `ConversationState.pending` defaults to `ask(consent)`. `register_for(..., *, default_country)` is keyword-only for the default. The `EngineAction.register` field triggers a Pydantic shadowing warning (`ABCMeta.register`, harmless); it is silenced locally so the contract keeps the name `register`. **For T21:** `ShowRecap(profile=...)` must get `profile.model_copy(deep=True)`, otherwise the action aliases the mutable state.

## C. Validators & rules

- [x] **T9 — Consent & name.**
  - `engine/validators.py`: the outcome dataclasses `Accepted`, `Rejected`, `NeedsConfirmation`, plus `validate_consent` and `validate_name`.
  - Tests `tests/engine/test_validators.py`, parametrised:
    - "Ana López", "María-José O'Neill", "José  Pérez " (spaces collapsed) are accepted;
    - "Ana2 López" → `invalid_characters`;
    - "Ana" with `reasks_used=0` → `surname_missing`;
    - "Ana" with `reasks_used=1` → Accepted + flag `surname_missing` (**AC-15**, unit);
    - consent `UNCLEAR` → `consent_required`.
  - *(FR-7, FR-16)*

- [x] **T10 — Age, vehicle, license + rules.**
  - In `validators.py`: `validate_age`, `validate_vehicle`, `validate_license`.
  - `engine/rules.py`: `license_need`, `min_age_for`, `hard_rule_failure` (`under_age`, `no_license` only for now), `sync_license_requirement`, `DISQUALIFYING_FIELDS`.
  - Tests `tests/engine/test_rules.py`:
    - age 17 → `under_age`; `is_adult=False` → `under_age`; age 150 → `implausible_value`; age 5 → `implausible_value` (**AC-6**, unit);
    - motorbike + no license → `no_license` (**AC-7**, unit);
    - `bike_free_config` + bicycle → `not_required`, and the slot becomes `not_required` (**AC-8**, unit);
    - `bike_free_config` + vehicle unknown + no license → `depends`, no failure (**AC-9**, unit);
    - default config + vehicle unknown + no license → `no_license`;
    - unknown country uses the lowest minimum age.
  - *(FR-17, FR-18)*

- [x] **T11 — Location: normalise, index, exact/alias match.**
  - `engine/location.py`: `normalise`, `IndexEntry`, `LocationIndex` (built as a `PrivateAttr` in an `EngineConfig` after-validator), and `match_location` with segment splitting and exact/alias hits only.
  - Tests `tests/engine/test_location.py`, parametrised:
    - "CDMX", "DF", "Ciudad de México", "coyoacan", "COYOACÁN" → cdmx / coyoacán (**AC-12**, part);
    - "Coyoacán, CDMX" → the zone;
    - "Madrid" → city only;
    - `normalise` table (accents, case, punctuation).
  - *(FR-19)*
  - *Note (impl):* `LocationIndex` is a frozen dataclass (`entries`, `cities`, `zones_by_city`, `served_city_ids()`, `zone_entries()`), built in an `EngineConfig` after-validator and exposed as `config.location_index`. `config/models.py` imports `normalise`/`LocationIndex` from `engine/location.py`; the reverse import is `TYPE_CHECKING`-only, so there is no cycle. The segment combination (incl. `CityWithUnknownZone`) landed here because it is one function; a city **without** zones plus an unknown extra part resolves to that city (it is served whole).

- [x] **T12 — Location: fuzzy, hint narrowing, ambiguity, city context.**
  - Add the `similarity()` wrapper over `difflib`, fuzzy hits (≥ 4 chars, threshold, within 2 points of best), `country_hint` narrowing (only when at least one match survives), `within_city` priority, and `CityWithUnknownZone`.
  - Tests:
    - "Cuyoacán" → coyoacán (**AC-12**);
    - "Coyoacan" with the threshold set to 95 via `make_config` → no match (proves config drives it);
    - "El Carmen" without hint → 2 refs; with hint MX → monterrey (**AC-13**);
    - "Centro" with hint ES in the fixture → still unique to Madrid; in the shipped config → several refs;
    - `within_city="madrid"` + "Centro" → `mad-centro`;
    - "Vallecas, Madrid" → `CityWithUnknownZone`;
    - "xjkq" → `NoMatch`.
  - *(FR-19)*
  - *Deviation:* the planned test "`Coyoacan` with threshold 95 → no match" cannot hold: "Coyoacan" is an **exact** match after `normalise`, so the threshold never applies. The test uses the typo "Cuyoacán" (87.5) at threshold 95 instead, which proves the same point.

- [x] **T13 — `validate_location` + `out_of_area` rule.**
  - Implement `validate_location` (the plan §3.6 table) and add `out_of_area` to `hard_rule_failure`.
  - Tests, parametrised over the table rows:
    - "Madrid" → partial, zone missing (**AC-14**, unit);
    - "Vallecas, Madrid" known → `in_service_area=False` → `out_of_area` (**AC-10**, unit);
    - "Zaragoza" known → `out_of_area`; "xjkq" unknown → `Rejected(not_recognised, served city ids)` (**AC-11**, unit);
    - "El Carmen" no hint → `NeedsConfirmation(ambiguous)` with 2 options (**AC-13**, unit).
  - *(FR-19)*
  - *Note (impl), relevant to T17/T20:* `needs_zone(value, config)` in `location.py` tells the caller a partial city must stay `not_asked` and that `zone` is next. Beyond the plan table: (a) with a zone pending, re-asks list **that city's zone ids**, not the served cities; (b) repeating the same city while the zone is pending returns `Rejected(unclear, zone ids)`, so it counts as a failed attempt instead of looping on `ask_field(zone)` without consuming re-asks; (c) a configured place is accepted even if `is_known_place=false` (config is the source of truth); (d) a zone answer stores `raw_text="<city text>, <zone text>"` for audit. `location.py` is ~280 lines (target ~250).

- [x] **T14 — Availability, schedule, experience.**
  - `validate_availability`, `validate_schedule`, `validate_experience` (exact platform matching via `normalise` + aliases, `other:<text>`).
  - Tests:
    - duplicates are de-duplicated and sorted; empty → `empty_selection` with all options;
    - years 45 → `NeedsConfirmation(value)`; "none" → `Experience(0, [])`; -1 → `negative_value`; `None` → `missing_years`;
    - "Uber Eats" → `uber_eats`; "Rappi Turbo" → `other:Rappi Turbo` (**AC-16**, unit).
  - *(FR-20, FR-21)*
  - *Note (impl):* `normalise()` moved to a tiny `engine/text.py` (re-exported by `location.py`), because `location.py` imports `validators.py` and platform matching needs it too: no import cycle. Multi-choice values are stored de-duplicated in **enum declaration order** (deterministic, reads naturally). Platforms are stored as a sorted unique list; `"none"` years ignores any platforms (FR-21). `validate_experience(..., platforms=config.screening.platforms, confirm_above=...)`.

- [x] **T15 — Start date.**
  - `resolve_start_date` and `validate_start_date`.
  - Tests, parametrised with today = 2026-10-12 (Monday):
    - `next_weekday(mon)` → 10-19;
    - `next_weekday(wed)` → 10-14;
    - `offset(2 weeks)` → 10-26;
    - `offset(3 days)` → 10-15;
    - `asap` → 10-12;
    - `absolute(2026-09-01)` → 10-12 + flag `start_date_normalised`;
    - `absolute(2026-11-02)` stays as given;
    - `offset(-1 days)` → `negative_value` (**AC-17**).
  - *(FR-22)*
  - *Note (impl):* any resolved date in the past (not only `absolute`) is moved to `today` + flag. An offset so large it overflows the calendar returns `Rejected(implausible_value)` instead of raising (NFR-5).

## D. `step()`, built up incrementally

- [x] **T16 — `start()`, `step()` skeleton, consent gate, test driver.**
  - `engine/step.py`:
    - `start()`;
    - `step()`, the safety-net wrapper around `step_unchecked()`;
    - copy-on-entry, `finish()` (language + register), `on_candidate_turn` (precedence skeleton with only opt-out at consent and the consent gate wired).
  - `engine/collect.py`: `apply_proposals` (consent gate, stage-order validation, latest wins), `next_missing_field` (in `flow.py`), `next_action` (ask only), `reask_or_exhaust` for consent (OQ-1 default).
  - `engine/closing.py`: `opt_out`.
  - Create `tests/engine/builders.py`: the proposal factories and `Convo` (`say`, `event`, `expect`, `expect_status`, `expect_prefaces`, `history`, `record` stub).
  - Tests `tests/engine/test_flow.py`:
    - `start` → `ask_field(consent)`;
    - consent false → `opted_out`, `close_opted_out`, empty profile, flag `do_not_contact` (**AC-2**);
    - name without consent → not stored + `reask_field(consent)`;
    - consent + "Ana López" → both stored, `ask_field(age)` (**AC-3**);
    - the caller's state is unchanged after `step`.
  - *(FR-1, FR-7, FR-11)*
  - *Note (impl):* the start-date factory in `builders.py` is `start_date(expr)` (avoids clashing with `engine.start`); `Convo` also offers `reasks(field)` and `primaries()`. OQ-1: consent re-asks never close, and the consent counter is capped at `max_reasks + 1` so the T29 invariant holds. Data sent without consent yields `reask(consent, consent_required)`; a FAQ-only turn at consent is neutral.

- [x] **T17 — Profile collection, out of order.**
  - Wire all validators into `apply_proposals`, including license sync and `zone` via `next_missing_field`, plus `set_pending` (keeps `stage` in sync).
  - Tests `test_flow.py`:
    - name + license true + "Coyoacán" in one turn → all stored, `ask_field(age)` (**AC-4**);
    - `is_adult` + availability {weekends} → availability skipped later; after the knock-outs, the first profile ask is `schedule` (**AC-5**);
    - within a turn, proposals are validated in stage order;
    - a re-proposed field overwrites (latest wins).
  - *(FR-8, FR-9)*

- [x] **T18 — Hard rules in the loop.**
  - `hard_rule_failure` is called after `apply_proposals`, plus `close_disqualified` (status, reason, `drop_off_stage`).
  - Tests `tests/engine/test_disqualifiers.py`:
    - age 17 at the consent+name, age, vehicle and location stages, alone and with other valid fields → `disqualified/under_age`, other fields kept (**AC-6**);
    - motorbike then license false → `no_license` (**AC-7**);
    - `bike_free_config` + bicycle → license `not_required`, next `ask_field(location)` (**AC-8**);
    - `bike_free_config`: license false with unknown vehicle → `ask_field(vehicle_type)`, then motorbike → `no_license` (**AC-9**);
    - "Vallecas, Madrid" known → `out_of_area` (**AC-10**);
    - "Zaragoza" known → `out_of_area` (**AC-11**, first half).
  - *(FR-17, FR-18, FR-19)*

- [x] **T19 — Re-ask policy (soft fields, name).**
  - `classify_attempt`, `reask_or_exhaust` for all fields, `default_options`, soft exhaustion, `name_unclear`.
  - Tests `tests/engine/test_reask.py`:
    - availability unclear ×3 → actions 2 and 3 are `reask_field` with all options, then availability `unclear` and `ask_field(schedule)` (**AC-18**);
    - with 1 re-ask used, a FAQ-only turn, an other-fields-only turn and an `extraction_failed` turn each leave the count at 1 (parametrised, **AC-20**);
    - "Ana" twice → `reask(surname_missing)`, then stored + flag (**AC-15**);
    - an empty turn counts as a failed attempt;
    - name unclear ×3 → flag `name_unclear`, flow continues.
  - *(FR-16, FR-23, FR-24)*
  - *Note (impl):* the `extraction_failed` path (repeat the pending ask without using a re-ask, close as `system_failure` at the threshold) landed here because AC-20 needs it; T23 added the threshold tests. Neutral turns: FAQ, off-topic, abuse, a language change, and the first turn after a resume (T24).

- [x] **T20 — Confirmations and zone ask.**
  - The `confirm_value` and `confirm_ambiguous` handlers, the "first confirmation of the turn becomes pending" rule, and `within_city` for a pending zone.
  - Tests:
    - years 45 → `confirm_value(experience)`, yes → 45 stored; no → `reask_field(experience, value_rejected)` (**AC-16**);
    - "none" → years 0, platforms [] (**AC-16**);
    - "El Carmen" without hint → `confirm_ambiguous` with 2 options; `choice(monterrey id)` → stored; with `country_hint=MX` → no confirmation (**AC-13**);
    - "Madrid" → `ask_field(zone)`, then "Centro" → `mad-centro` (**AC-14**);
    - zone answer "Vallecas" (known) → `out_of_area`.
  - *(FR-19, FR-21)*
  - *Note (impl):* to keep modules near ~250 lines, proposal application moved from `collect.py` to a new `engine/apply.py` (`Applied`, `apply_proposals`, `set_pending`, `answers_pending`); `collect.py` keeps attempt classification, the re-ask policy and the next ask. Answers to a pending confirmation (yes/no, an option id, or naming one option's city such as "Monterrey") are resolved inside `apply_proposals`, so the hard rules see the final values of the turn. A failed ambiguity answer re-asks as `reask_field(location, options=<same option ids>)` and keeps `confirm_ambiguous` pending. A neutral turn (e.g. FAQ) while confirming repeats the confirmation. `PendingAsk.raw_text` keeps the ambiguous text for audit.

- [x] **T21 — Hard exhaustion + recap.**
  - `review_reasons` in `rules.py`. In `closing.py`: `close_needs_review`, `show_recap` (loop guard), and the `recap` and `correction_field` handlers.
  - Tests `tests/engine/test_recap.py`:
    - location unclear ×3 → profile still collected → at recap `needs_review/location_unclear` with `close_needs_review`, never disqualified (**AC-19**);
    - "xjkq" unknown ×3 → `reask(not_recognised, served cities)`, then `needs_review` at recap (**AC-11**, second half);
    - confirm → `offer_slots` (with `offered_slots` in context) (**AC-22**);
    - correction of availability → stored + `show_recap` with the new value (**AC-23**);
    - correction to an unserved zone, and license→false, → disqualified with the matching reason (parametrised, **AC-24**);
    - "no" alone → `ask_correction_field` (**AC-25**);
    - the 4th recap → `needs_review/recap_loop`;
    - with vehicle unclear + license false + `bike_free_config` → `vehicle_unclear`.
  - *(FR-24, FR-25)*
  - *Note (impl):* `recap` and `correction_field` share one handler, `collect.on_recap`. Any accepted value goes through `next_action`: a correction that leaves a field missing (e.g. license required again) asks for it; otherwise the recap is shown again. A neutral turn with no proposals (FAQ, off-topic, language switch) repeats the recap **without** counting a round, so FAQs cannot trip the `recap_loop` guard. `review_reasons` lists reasons in stage order (age, vehicle, license, location). `show_recap` sends a deep copy of the profile. `enter_scheduling` (needed for AC-22) falls back to the slots offered earlier when the turn carries none.

- [x] **T22 — Scheduling.**
  - `enter_scheduling`, `on_slot_event`, the slot handler and `close_qualified_unscheduled`.
  - Tests `tests/engine/test_events.py` + `test_flow.py`:
    - offered {s1, s2} → `slot_selected(s9)` → `reask_field(slot, slot_not_offered, [s1, s2])` (**AC-30**);
    - `no_slot_fits` → `qualified_unscheduled` (**AC-30**);
    - slot re-asks exhausted → `qualified_unscheduled`;
    - recap confirmed without `offered_slots` → `qualified_unscheduled`;
    - `slot_selected` outside scheduling → ignored;
    - the full happy path, one field per turn → exact action sequence, `interview_scheduled`, `selected_slot_id = s1` (**AC-1**; the record assertions are finished in T28).
  - *(FR-26)*
  - *Note (impl):* `on_slot_event` lives in `step.py` (events); the candidate-turn handler for a pending slot is `collect.on_slot_answer` (a correction re-opens the recap per OQ-7, a neutral turn repeats `offer_slots`, an empty turn uses a slot re-ask). A slot event while the conversation is not `in_progress` returns `closed_ack`; outside scheduling it repeats the pending ask. `Convo.advance_to(stage)` (planned for T24) was added here with a canonical valid candidate, because the scheduling tests need it.

- [x] **T23 — Signals: correction, wants_human, FAQ, off-topic, abuse, extraction failures.**
  - Complete the precedence in `on_candidate_turn`, `repeat_pending`, `handoff`, and the preface ordering in `finish`.
  - Tests `tests/engine/test_signals.py`:
    - city stored (Chamberí, Madrid) + `correction` "Coyoacán" → overwritten, `ack_correction` preface + pending ask (**AC-21**, in `test_recap.py`);
    - `wants_human` → `needs_review`, flag `human_requested`, `handoff_to_human` (**AC-27**, first half);
    - pending schedule: FAQ alone → `answer_faq` + `ask_field(schedule)`; FAQ + valid schedule → `answer_faq` + next field (**AC-28**);
    - 3 `extraction_failed` → `needs_review/system_failure`, with the first two being `reask(extraction_failed)` (**AC-31**);
    - abuse once → `redirect` preface; twice → `needs_review/abuse` + `close_needs_review` (**AC-31**);
    - off-topic → `redirect`, no re-ask consumed;
    - FR-10 precedence matrix (plan §7.3).
  - *(FR-9, FR-10, FR-12, FR-13, FR-27, FR-28)*

- [x] **T24 — Opt-out everywhere + silence.**
  - Finish `opt_out` (purge per FR-11) and `on_silence` (abandoned / qualified_unscheduled), plus the resume rule (the first turn after resume is neutral). Add `Convo.advance_to(stage)` and `advance_to_status(status)`.
  - Tests `tests/engine/test_opt_out.py`:
    - parametrised over every pending stage × statuses {in_progress, abandoned, disqualified, needs_review, qualified_unscheduled, interview_scheduled}, opt-out with proposals → `opted_out`, `close_opted_out`, no field values, `drop_off_stage` kept, flags = [`do_not_contact`] (**AC-26**);
    - an opted-out state then any turn → `closed_ack` (OQ-4).
  - Tests `test_events.py`:
    - pending `vehicle_type` + silence → `abandoned`, `drop_off_stage=vehicle_license`; the next turn → `in_progress` + `ask_field(vehicle_type)`; silence in scheduling → `qualified_unscheduled` (**AC-29**).
  - *(FR-11, FR-14)*
  - *Note (impl):* `silence_expired` on a conversation that is not `in_progress` (already abandoned, closed, opted out) returns `no_message` with no state change; the plan's pseudo-code said `closed_ack`, but a timer must never make the channel send text (OQ-2 decision). The AC-26 matrix covers only reachable combinations: {in_progress, disqualified, needs_review} × all 11 stages, abandoned × all stages except scheduling (silence there yields qualified_unscheduled), and qualified_unscheduled / interview_scheduled at scheduling (45 cases). `Convo.advance_to_status(status, at=stage)` reaches each one.

- [x] **T25 — Closed statuses + post-close correction.**
  - `on_closed` and `post_close_corrections`.
  - Tests `tests/engine/test_closed.py`:
    - disqualified `no_license` + `correction` with license true → `needs_review`, flag `post_close_correction`, record keeps the original `false` and the proposed `true`, `close_needs_review` (**AC-26b**);
    - a correction to an unrelated field after disqualification → `closed_ack`, no change;
    - after `handoff_to_human`, the next turn → `closed_ack` (**AC-27**);
    - for each closed status, a FAQ turn → `answer_faq` + `closed_ack` and the profile is unchanged.
  - *(FR-12, FR-15)*
  - *Note (impl):* `on_closed` and `post_close_corrections` live in `closing.py`; `apply._validate` became public `validate_proposal` so post-close values go through the same validators. As in the plan, the `correction` signal is not required: any valid value for a disqualifying field that differs from the stored one counts. Values are stored JSON-ready (`to_jsonable_python`). **Decided (FR-15 updated):** the correction is always recorded (de-duplicated), but the status only moves to `needs_review` if the corrected values would pass the rule that caused the disqualification (checked on a throwaway copy via `_would_pass`); otherwise the candidate stays `disqualified` and gets `closed_ack` (e.g. age 17 -> 16).

- [x] **T26 — Language & register end-to-end.**
  - Tests `test_signals.py`:
    - `language=en` signal → next action `language=en`, `register=en`;
    - CDMX location + es → `es-MX`;
    - Madrid + es → `es-ES`;
    - no location + hint MX → `es-MX`;
    - a language change alone does not consume a re-ask (**AC-32**).
  - *(FR-4, edge case "language switch")*
  - *Note (impl):* test-only task: the behaviour (language signal, `register_for` in `finish`, language switch counted as neutral) was built in T16/T19, so these tests passed on first run. Extra cases: register follows the stored location over the phone prefix; a "language" signal equal to the current language is not neutral; closing actions carry the language too. Group D size check: `apply.py` is ~305 lines (over the ~250 target); `step.py` 242, `collect.py` 213, `closing.py` 170.

## E. Scoring & record

- [x] **T27 — Scoring.**
  - `engine/scoring.py`: `ScoreFactor`, `ScoreResult`, `score_candidate`.
  - Tests `tests/engine/test_scoring.py`:
    - AC-33 candidate → the 5 factors, `score == sum(points) == 82`, bucket `high`, each factor has field/value/reason (**AC-33**);
    - availability `unclear` → that factor is 0 / `unknown` (**AC-33**);
    - doubled weights via `make_config` → a different score/bucket, no code change (**AC-34**);
    - caps respected;
    - `other:*` platforms score 0;
    - start-date bands at the boundaries (3, 4, 14, 15, 30, 31 days).
  - *(FR-30, NFR-6)*
  - *Note (impl):* `FactorReason` lives in `enums.py`. Factor values: years as int, platforms and availability/schedule as ID lists, start date as an ISO string. `flexible` scores the flexible weight regardless of other slots; otherwise `per_slot × n`. A start date before the reference date counts as 0 days. The AC-34 test changes `points_per_year` and the bucket thresholds via `make_config` (82/high → 70/medium) instead of doubling every weight; same point, easier to read.

- [x] **T28 — Candidate record + schema export.**
  - `engine/record.py`: `FieldRecord`, `RecordFields`, `CandidateRecord`, `build_record` (score only for scheduled / unscheduled / needs_review).
  - `scripts/export_record_schema.py` writes `docs/specs/002-screening-engine/candidate-record.schema.json`. Commit the generated file.
  - Finish `Convo.record()`.
  - Tests `tests/engine/test_record.py`:
    - one record per status (via `advance_to_status`) → `json.dumps(record.model_dump(mode="json"))` + `CandidateRecord.model_validate_json` succeed; the key set covers FR-31; enum values are language-neutral (**AC-36**);
    - disqualified and opted-out → `score is None` (**AC-34**);
    - opted-out record has no field values (**AC-2**, **AC-26**);
    - the AC-1 record has every field `valid`, `selected_slot_id="s1"` and a score (**AC-1**);
    - the committed schema equals `CandidateRecord.model_json_schema()`.
  - *(FR-31)*
  - *Note (impl):* the score is computed in `build_record` (reference date `state.last_turn_on`, never the clock); a state that never stepped has no score. A declined consent is now stored as `consent=False` (it was left `None`) so the record shows the explicit refusal. The AC-36 test checks every string in the record except candidate text (`full_name`, `raw_text`) against an ID/enum/ISO pattern, and covers all seven statuses via `Convo.advance_to_status`. Regenerate the schema with `uv run python scripts/export_record_schema.py` (run from `backend/`).

## F. Robustness & close-out

- [x] **T29 — Property, purity and performance tests.**
  - `tests/engine/strategies.py`: Hypothesis strategies for proposals (valid, invalid and `UNCLEAR`), signals, events and contexts.
  - `test_properties.py`: the invariants in plan §7.4 on `step_unchecked`, `derandomize=True`, `max_examples=300`.
  - `test_purity.py`: AST scan of `engine/`.
  - `test_performance.py`: < 10 ms mean per turn.
  - Fix any bug Hypothesis finds by adding a regular regression test **first**.
  - *(NFR-1, NFR-2, NFR-4, NFR-5)*
  - *Note (impl):* purely random turns rarely get past consent, so each generated conversation starts with a random-length prefix of the canonical valid candidate (`builders.canonical_turns()`) followed by up to 40 random turns; a sampling run reached all 11 stages and all 7 statuses. The allowed-transition set adds `abandoned → {disqualified, needs_review, qualified_unscheduled, opted_out}`: a turn after silence resumes **and** is evaluated in the same step. Hypothesis (300 examples, `derandomize=True`) found no bugs, so no regression test was needed. The purity scan also forbids `sys`, `uuid`, `secrets`, `socket`, `subprocess`, `print` and `input`. Measured: ~0.2 ms per turn (limit 10 ms). The property test adds ~7 s to the suite.

- [x] **T30 — Public API & AC coverage gate.**
  - `engine/__init__.py` re-exports the public API (`start`, `step`, `build_record`, `score_candidate`, input/action/state/record models) with `__all__`.
  - `tests/test_ac_coverage.py` parses `docs/specs/002-screening-engine/spec.md` for `AC-\d+b?` and fails if any id has no `pytest.mark.ac` in `tests/`.
  - Run `uv run pytest --cov=sazon_screening.engine` and add tests for any branch of `step.py`/`collect.py`/`closing.py` that is not covered, or justify it in the PR.
  - *(NFR-3, all ACs)*
  - *Deviation (import order):* `engine/__init__.py` resolves its 63 exports **lazily** (PEP 562 `__getattr__`; a `TYPE_CHECKING` block gives mypy/IDEs the real names). `config/models.py` imports `engine.enums`/`engine.location`, so importing `sazon_screening.config` first runs `engine/__init__`. An eager `from .step import start` there was tried and fails with `ImportError: cannot import name 'EngineConfig' from partially initialized module 'sazon_screening.config'`. `test_public_api.py` checks four import orders in fresh interpreters. Cleaner long-term fix (not done, larger change): move the shared vocabulary (enums) and the location index out of `engine/`, so that `config` never imports `engine`.
  - *Coverage:* `uv run pytest --cov=sazon_screening --cov-branch` → 99%. Gap tests were added (unclear consent/confirmation, empty turn while disambiguating or on a zone, FAQ at `correction_field`, `license_unclear`, a config where no vehicle needs a license, a missing display language). The unreachable `slot` case in `default_options` was removed. Two branches stay uncovered on purpose: `closing.py` `if s.disqualification_reason is None` (type narrowing; it is always set while disqualified) and the fall-through of the exhaustive `match` over `TurnInput` in `step.py`.
  - `tests/test_ac_coverage.py` also fails if a marker names an AC that is not in spec.md.

- [x] **T31 — Verify & update docs.**
  - Walk through AC-1…AC-36 (incl. AC-26b) against the tests and tick the spec checkboxes.
  - Update `docs/ROADMAP.md` (002 ✅).
  - Add a short "Engine" section to the README: how to call `start`/`step`, and how ops edit `config/` (with the `ConfigError` example).
  - Record the OQ decisions taken (plan §8) in spec §7 once the human has answered them.
  - *(all)*
  - *Note (impl):* all 37 AC checkboxes ticked (each has a marked test; the gate enforces it). There is no root README yet, so the "Engine" section went into `backend/README.md`; its code sample was executed to check the documented output. Plan §8 OQ decisions are recorded in spec §7, and decision row 7 now matches the updated FR-15. **Rename found during close-out:** `engine/step.py` → `engine/turn.py`. With lazy exports, importing the submodule `engine.step` rebinds the package attribute `step` to the module, so `from sazon_screening.engine import step` returned a module, not the function. `test_public_api.py` now imports every submodule first and asserts that the entry points are functions.

## G. Amendment 2026-10-13: month-level start dates

- [x] **T32 — `offset(n months)` and `month(m)` start dates (AC-41, AC-42).**
  - Bug from a live run: "el mes que viene" and "El mes al que vamos a entrar" were re-asked for a concrete day; a month is a valid answer for a delivery driver.
  - `inputs.py`: `Offset.unit` gains `"months"`; new variant `Month(month)`. `validators.py`: both resolve to the 1st of that month (today if it is the current month) and add flag `start_date_approximate`. `apply.py` clears the flag whenever a new start date is stored. `ShowRecap.start_date_approximate` carries it to the phrasing layer.
  - Regenerated `candidate-record.schema.json` (new `Flag` value).
  - *(FR-22)*
