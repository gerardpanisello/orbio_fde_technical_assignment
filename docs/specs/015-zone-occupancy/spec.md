# Spec 015 — Zone occupancy: staffing-aware priority + waitlist (compact)

**Status:** Approved (decisions by Gerard, 2026-10-12)
**Related:** ADR 0004 (hard rules + scoring), ADR 0005 (turn contract — amended here), specs 002 (scoring, record), 004 (API), 006 (dashboard).

## 1. Why
Grupo Sazón doesn't need "drivers", it needs drivers **where it's short**. A candidate in a zone at 40% of its target staffing is worth more than one in a zone already full. Today the score ignores this, so recruiters still have to cross-check staffing by hand. Product idea from Gerard (client-empathy: tie screening to the real operational need).

## 2. Decisions (Gerard, 2026-10-12)
| Question | Decision |
|---|---|
| Where is occupancy managed? | **"Zonas" page in the dashboard**, stored in the DB, editable by recruiters; initial values seeded from config. |
| Does "Contratar" update occupancy? | **Yes, +1 automatically** to the hired candidate's zone. |
| Effect on the candidate | **Score + waitlist**: an explainable "zone demand" factor; and if the zone is **full (≥ 100%)** when the candidate would book an interview, they are **waitlisted** instead (kind message, no slots). Never disqualified for this. |
| Recompute? | **Live**: priority in the dashboard uses current occupancy; the score at conversation close is kept for audit. |

## 3. Requirements
- FR-1 **Staffing per area.** Every served area (a zone, or a city served as a whole) has `target_drivers` and `current_drivers`. Occupancy = current / target. Initial values in `config/zone_staffing.yaml` (seed only); the DB (`zone_staffing` table) is the source of truth after first start. Unknown/unseeded areas default to "no data" (no bonus, never waitlisted).
- FR-2 **Zone demand factor** (scoring, ADR 0004 style): points from occupancy bands in `config/screening.yaml` (e.g. < 50% → +20, < 80% → +12, < 100% → +5, ≥ 100% → 0). Shown in the factor list as "Demanda en su zona: 45% cubierta (+20)". `max_score` grows accordingly; bucket thresholds re-tuned.
- FR-3 **Engine stays pure.** Occupancy is an *input*: `build_record(state, config, occupancy=…)` / `score_candidate(…, occupancy=…)`; the turn context carries `zone_full: bool` for the scheduling decision. The engine never reads the DB.
- FR-4 **Waitlist.** When the recap is confirmed and the candidate's area is full, the engine closes with new status **`waitlisted`** and action **`close_waitlisted`** (no slots offered). Template: "Ahora mismo tenemos cubierto el equipo en {zona}. Te dejamos en lista de espera y te escribiremos en cuanto haya hueco." (es-ES / es-MX / en). Opt-out still works; a later message gets `closed_ack`.
- FR-5 **Hire → +1.** Recruiter action `hire` increments `current_drivers` of the candidate's area (once per candidate; undoing is a manual edit). Stored in the action history.
- FR-6 **Live priority.** `GET /api/candidates` computes score/bucket with **current** occupancy; the record keeps `score_at_close`. Sort by score uses the live score.
- FR-7 **API:** `GET /api/zones` → per area: id, name, city, country, target, current, occupancy %, candidates in pipeline (qualified/interview_scheduled/waitlisted counts); `PATCH /api/zones/{id}` `{target_drivers?, current_drivers?}` (validated ≥ 0). Waitlisted candidates filterable by status.
- FR-8 **Dashboard "Zonas" page:** table grouped by city with an occupancy bar (colour: red < 50%, amber < 80%, green < 100%, grey "cubierta" ≥ 100%), inline edit of target/current, waitlist count linking to the filtered candidates list. Candidate detail shows the zone-demand factor. KPI on Candidatos: "Zonas con déficit".
- FR-9 **Seed:** `config/zone_staffing.yaml` with plausible values so the demo shows variety (some zones < 50%, some full: at least one served zone ≥ 100% so the waitlist can be demoed, e.g. Salamanca (Madrid)).

## 4. Acceptance criteria
- AC-1 Same candidate profile scores higher in a 40%-occupied zone than in a 90% one; the factor appears with its reason.
- AC-2 Changing a zone's target in the dashboard changes the live score/bucket of its candidates without reprocessing conversations; `score_at_close` is unchanged.
- AC-3 Confirming the recap in a full zone → `waitlisted` + waitlist message, no slots; in a non-full zone → slots offered as before.
- AC-4 `hire` increments the zone's current drivers by 1 exactly once per candidate.
- AC-5 Area without staffing data → no bonus, never waitlisted.
- AC-6 `PATCH` with negative numbers → 422.
- AC-7 Zonas page renders bars, edits persist, waitlist link filters candidates.
- AC-8 Engine purity tests still pass (no DB/clock access); all existing tests green.

## 5. Tasks
- [x] T1 Engine: `waitlisted` status + `close_waitlisted` action + `zone_full` in turn context; occupancy-aware scoring factor; amend ADR 0005; spec 002 note. Tests.
- [x] T2 Config: `zone_staffing.yaml`, demand bands in `screening.yaml`, waitlist templates (3 registers). Loader validation.
- [x] T3 API: `zone_staffing` table seeded from config, `/api/zones` GET/PATCH, live scoring in list/detail, hire → +1, `zone_full` passed when entering scheduling, seed personas incl. a waitlisted one. Tests.
- [ ] T4 Frontend: Zonas page, factor display, waitlisted badge/colour, KPI, regenerate API types.
- [ ] T5 README + ROADMAP + process-design note (new outcome "Lista de espera").
