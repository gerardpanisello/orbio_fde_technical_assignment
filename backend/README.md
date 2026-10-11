# Backend

Python package for the Grupo Sazón screening agent. See the root README.

```
uv run pytest                                   # tests (incl. property tests, AC coverage gate)
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
