# Backend

Python package for the Grupo Sazón screening agent. See the root README.

```
uv run pytest                                   # tests (incl. property tests, AC coverage gate)
HYPOTHESIS_PROFILE=thorough uv run pytest       # CI: 300 property-test examples (default: 60)
uv run ruff check . && uv run ruff format --check .
uv run mypy                                     # strict, on src/
```

## Engine (spec 002)

`sazon_screening.engine` is the deterministic core: a pure function of
`(state, turn input, config, today)`. It reads no clock, network or files, and never
produces text: it returns a typed action that the LLM layer (003) phrases. Contract:
[ADR 0005](../docs/adr/0005-engine-turn-contract.md).

```python
from datetime import date
from pathlib import Path

from sazon_screening.config import load_config
from sazon_screening.engine import (
    AgeAnswer,
    AgeProposal,
    CandidateTurn,
    ConsentProposal,
    NameProposal,
    Signals,
    TurnContext,
    build_record,
    start,
    step,
)

config = load_config(Path("../config"))  # validated once, at startup
state, action = start(config)  # action.primary: ask_field(consent)

turn = CandidateTurn(
    proposals=[
        ConsentProposal(value=True),
        NameProposal(value="Ana López"),
        AgeProposal(value=AgeAnswer(age=24)),
    ],
    signals=Signals(),  # opt_out, wants_human, faq_question, ...
    context=TurnContext(country_hint="MX"),  # e.g. from the phone prefix
)
state, action = step(state, turn, config, today=date.today())
# action.primary  -> AskField(field="vehicle_type")
# action.prefaces -> [] (answer_faq / ack_correction / redirect when relevant)
# action.language, action.register -> "es", "es-MX"

record = build_record(state, config)  # CandidateRecord: what 004/006 store and show
```

- **Store `state` between turns** (`state.model_dump_json()` / `ConversationState.model_validate_json`).
  `step` never mutates the state you pass in; it returns a new one.
- **Events** from timers and calendars are inputs too: `SilenceExpired()` (returns
  `no_message`: send nothing), `SlotSelected(slot_id=...)`, `NoSlotFits()`.
- `step` never raises: an unexpected bug closes the conversation as `needs_review`
  with flag `engine_error`. Log that flag.
- The record's JSON schema lives in
  [candidate-record.schema.json](../docs/specs/002-screening-engine/candidate-record.schema.json).
  Regenerate it with `uv run python scripts/export_record_schema.py` (a test fails if it drifts).

### Editing the rules (ops)

Business rules live in the repo-root [`config/`](../config/), not in code or prompts:

- `service_areas.yaml`: countries, cities, zones, aliases and timezones. A place that
  is not listed is "out of area".
- `screening.yaml`: minimum age per country, license required per vehicle, known
  platforms, re-ask and loop limits, scoring weights and buckets.

Each file starts with a comment explaining what can be changed. Bump `version` on every
edit: it is stamped on every candidate record. An invalid file stops the app at startup
with a `ConfigError` that names the file and the exact key, for example:

```
screening.yaml: license_required: unknown vehicle type 'scooter' in license_required; allowed: motorbike, car, bicycle, e_bike, none
service_areas.yaml: countries.0.cities.0.timezone: unknown timezone 'Europe/Madird'
```

## LLM layer (spec 003): try the agent

Chat with Sofi in the terminal. Offline by default (`LLM_MODE=fake`): keyword rules read
your messages and the reviewed templates in `config/messages/` answer, so no API key is
needed.

```
uv run python -m sazon_screening.llm.demo --lang es             # Spanish, Spain register
uv run python -m sazon_screening.llm.demo --country MX --debug  # Mexico; show extraction + engine action
uv run python -m sazon_screening.llm.demo --lang en             # English
```

- Type a reply, or the number of a button (`[1] Sí  [2] No`).
- Commands: `/trace` (last turn's trace), `/state`, `/silence` (the candidate goes quiet),
  `/summary [es|en]`, `/quit`. On `/quit` it prints the candidate record and the
  recruiter summary.
- `--today YYYY-MM-DD` fixes the date (e.g. to replay a script).

With the real model (needs `ANTHROPIC_API_KEY` in `../.env`, see `../.env.example`):

```
uv run --env-file ../.env python -m sazon_screening.llm.demo --mode anthropic
```

Configuration: `config/llm.yaml` (models, timeouts, length caps, prices) and
`config/messages/*.yaml` (Sofi's templates and labels) live at the repo root so ops can
edit them without a release. System prompts ship inside the package
(`sazon_screening/llm/prompts/`). An installed package finds `config/` through
`SAZON_CONFIG_DIR`.

## API (spec 004): run the backend

FastAPI app over the agent, with SQLite storage. Offline by default (`LLM_MODE=fake`).

```
uv run uvicorn sazon_screening.api.app:create_app --factory --reload   # http://127.0.0.1:8000
curl -X POST "http://127.0.0.1:8000/api/dev/seed?n=40"                 # demo data (APP_ENV=dev), server's LLM mode
curl -X POST "http://127.0.0.1:8000/api/dev/seed?n=40&mode=fake"       # demo data, always offline (free)
```

Interactive docs at `http://127.0.0.1:8000/docs`. With the real model:
`uv run --env-file ../.env uvicorn sazon_screening.api.app:create_app --factory --reload`.

Environment (all optional; see `../.env.example`):

| Variable | Default | |
|---|---|---|
| `LLM_MODE` | `fake` | `anthropic` needs `ANTHROPIC_API_KEY` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./sazon.db` | any async SQLAlchemy URL (Postgres: `postgresql+asyncpg://...`) |
| `APP_ENV` | `dev` | `prod` turns off `/api/dev/*` (403) |
| `CORS_ORIGINS` | `http://localhost:5173` | comma-separated (the Vite dev server) |
| `REENGAGEMENT_SCHEDULER` | `on` | `off` stops the follow-up loop (spec 008); the schedule itself is `config/reengagement.yaml` |
| `REENGAGEMENT_TIME_SCALE` | `1` | demo speed-up: `60` = an hour of the schedule per minute (quiet hours are ignored when scaled) |

| Method and path | What it does |
|---|---|
| `GET /api/health` | liveness, LLM mode, env |
| `POST /api/conversations` `{language?, country_hint?}` | new chat; 201 with Sofi's greeting |
| `POST /api/conversations/{id}/messages` `{text}` | one turn; `{reply: {text, quick_replies} \| null, status}`. A button tap is sent as its label |
| `GET /api/conversations/{id}` | transcript + status (chat reload) |
| `GET /api/candidates?status=&country=&city=&bucket=&recruiter_status=&q=&sort=` | dashboard list; `sort` is `score`, `updated` or `created`, `-` for descending (default `-updated`) |
| `GET /api/candidates/export.csv` | same filters, as CSV |
| `GET /api/candidates/{id}` | record (002 schema), summary, transcript, traces, recruiter actions |
| `GET /api/candidates/{id}/summary?lang=es\|en` | stored summary; generated once if missing (409 while in progress) |
| `POST /api/candidates/{id}/actions` `{action, note?}` | `shortlist`, `reject`, `hire`, `override`, `note` (audit log) |
| `GET /api/analytics` | funnel totals, completion, drop-off, durations, reasons, fallback rate, cost, FAQ (009), `reengagement` (008) |
| `POST /api/dev/seed?n=40&seed=42[&mode=fake]` | simulated candidates through the real pipeline and the server's agent; `mode=fake` forces the offline rules agent (dev only) |
| `POST /api/dev/conversations/{id}/advance` | re-engagement demo (008): runs the **next** step now (the next reminder, or the abandon after the last one); 409 when there is nothing to advance (dev only) |
| `POST /api/dev/conversations/{id}/silence` | `silence_expired` at once: straight to `abandoned`, skipping the reminders (kept from 004; dev only) |

How it fits together: routes are thin; `api/service.py` runs a turn (load state, call the
agent with no DB session open, save state + messages + trace in one transaction) under
a per-conversation lock; `api/repo.py` holds all the SQL. Tables are created at startup
(no migrations yet): after a schema change, such as spec 008's new columns, **delete an
existing local `sazon.db`** (and `sazon.db-wal`, `sazon.db-shm`) and seed again. Follow-ups
(`sazon_screening/reengagement/`) run in an asyncio loop started in the API lifespan, under
the same per-conversation lock as messages. Interview slots come from `config/interview_slots.yaml` until real
calendars (010). Opting out purges the record (engine) and redacts the stored transcript.
