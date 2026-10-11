"""T28: the candidate record handed to 004/006 (FR-31, AC-36)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.record import CandidateRecord, RecordFields
from sazon_screening.vocab import FieldStatus, Stage, Status
from tests.engine.builders import Convo, consent
from tests.paths import BACKEND_DIR

SCHEMA_FILE = (
    BACKEND_DIR.parent / "docs" / "specs" / "002-screening-engine" / "candidate-record.schema.json"
)
FR31_KEYS = {
    "fields",
    "status",
    "disqualification_reason",
    "needs_review_reasons",
    "score",
    "flags",
    "language",
    "drop_off_stage",
    "selected_slot_id",
    "config_version",
}
SCREENING_FIELDS = {
    "full_name",
    "age",
    "vehicle_type",
    "has_license",
    "location",
    "availability",
    "schedule",
    "experience",
    "start_date",
}
SCORED = {Status.interview_scheduled, Status.qualified_unscheduled, Status.needs_review}
# Free text the candidate typed is data, not engine vocabulary.
CANDIDATE_TEXT_KEYS = {"full_name", "raw_text"}
NEUTRAL = re.compile(r"^[A-Za-z0-9_:.+\-]*$")  # ids, enum values, ISO dates, versions


def engine_strings(node: Any, key: str = "") -> list[str]:
    """Every string in the record except what the candidate typed."""
    if key in CANDIDATE_TEXT_KEYS:
        return []
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for k, v in node.items() for s in engine_strings(v, k)]
    if isinstance(node, list):
        return [s for item in node for s in engine_strings(item, key)]
    return []


@pytest.mark.ac("AC-36")
@pytest.mark.parametrize("status", list(Status))
def test_every_final_record_serialises(config: EngineConfig, status: Status) -> None:
    c = Convo(config).advance_to_status(status)
    record = c.record()
    dumped = json.dumps(record.model_dump(mode="json"))
    assert CandidateRecord.model_validate_json(dumped) == record
    data = json.loads(dumped)
    assert set(data) >= FR31_KEYS
    assert set(data["fields"]) == SCREENING_FIELDS
    for field in data["fields"].values():
        assert set(field) == {"status", "value"}
        assert field["status"] in {s.value for s in FieldStatus}
    assert all(NEUTRAL.match(s) for s in engine_strings(data)), engine_strings(data)
    assert data["status"] == status.value


@pytest.mark.ac("AC-34")
@pytest.mark.parametrize("status", list(Status))
def test_score_only_for_qualified_or_review(config: EngineConfig, status: Status) -> None:
    record = Convo(config).advance_to_status(status).record()
    if status in SCORED:
        assert record.score is not None
        assert record.score.score == sum(f.points for f in record.score.factors)
    else:
        assert record.score is None


@pytest.mark.ac("AC-2")
def test_declined_consent_record_has_no_screening_data(config: EngineConfig) -> None:
    record = Convo(config).say(consent(False)).record()
    assert record.status == Status.opted_out
    assert record.consent is False
    assert all(f.value is None for f in _fields(record))
    assert all(f.status == FieldStatus.not_asked for f in _fields(record))


@pytest.mark.ac("AC-26")
def test_opted_out_record_keeps_only_minimal_data(config: EngineConfig) -> None:
    record = Convo(config).advance_to_status(Status.opted_out, at=Stage.experience).record()
    assert all(f.value is None for f in _fields(record))
    assert record.flags == ["do_not_contact"]
    assert record.drop_off_stage == Stage.experience
    assert record.score is None
    assert record.disqualification_reason is None
    assert record.post_close_corrections == []


@pytest.mark.ac("AC-1")
def test_happy_path_record(config: EngineConfig) -> None:
    record = Convo(config).advance_to_status(Status.interview_scheduled).record()
    assert all(f.status == FieldStatus.valid for f in _fields(record))
    assert record.selected_slot_id == "s1"
    assert record.score is not None
    assert record.score.score == 82  # canonical candidate: 15 + 10 + 22 + 15 + 20
    assert record.config_version == config.version
    assert record.consent is True


def test_disqualified_record_explains_why(config: EngineConfig) -> None:
    record = Convo(config).advance_to_status(Status.disqualified).record()
    assert record.disqualification_reason == "under_age"
    assert record.fields.age.value is not None
    assert record.fields.age.value.age == 17


def test_committed_schema_is_up_to_date() -> None:
    # Regenerate with: uv run python scripts/export_record_schema.py
    committed = json.loads(Path(SCHEMA_FILE).read_text(encoding="utf-8"))
    assert committed == CandidateRecord.model_json_schema()


def _fields(record: CandidateRecord) -> list[Any]:
    return [getattr(record.fields, name) for name in RecordFields.model_fields]
