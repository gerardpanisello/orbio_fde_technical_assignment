"""The candidate record (FR-31): the engine's output contract for storage (004) and the
recruiter dashboard (006).

Everything is a language-neutral enum or ID, except what the candidate typed (name,
raw location text). The JSON schema is exported to
`docs/specs/002-screening-engine/candidate-record.schema.json`; a test fails if it drifts.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sazon_screening.config import EngineConfig
from sazon_screening.engine.inputs import AgeAnswer
from sazon_screening.engine.scoring import ScoreResult, score_candidate
from sazon_screening.engine.state import (
    ConversationState,
    Experience,
    LocationValue,
    PostCloseCorrection,
    Slot,
)
from sazon_screening.vocab import (
    Availability,
    DisqualificationReason,
    FieldStatus,
    Flag,
    Language,
    ReviewReason,
    ScheduleSlot,
    Stage,
    Status,
    VehicleType,
)


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldRecord[T](_Record):
    status: FieldStatus
    value: T | None


class RecordFields(_Record):
    full_name: FieldRecord[str]
    age: FieldRecord[AgeAnswer]
    vehicle_type: FieldRecord[VehicleType]
    has_license: FieldRecord[bool]
    location: FieldRecord[LocationValue]
    availability: FieldRecord[list[Availability]]
    schedule: FieldRecord[list[ScheduleSlot]]
    experience: FieldRecord[Experience]
    start_date: FieldRecord[date]


class CandidateRecord(_Record):
    record_version: Literal[1] = 1
    status: Status
    disqualification_reason: DisqualificationReason | None
    needs_review_reasons: list[ReviewReason]
    score: ScoreResult | None
    flags: list[Flag]
    language: Language
    drop_off_stage: Stage | None
    selected_slot_id: str | None
    config_version: str
    consent: bool | None
    fields: RecordFields
    post_close_corrections: list[PostCloseCorrection]


# Only candidates a recruiter will act on are ranked (FR-30).
_SCORED = frozenset({Status.interview_scheduled, Status.qualified_unscheduled, Status.needs_review})


def build_record(state: ConversationState, config: EngineConfig) -> CandidateRecord:
    """Snapshot of a conversation for storage and the dashboard. Pure, like `step`.

    The score is computed here, not stored in the state, so it always matches the
    config version stamped next to it (AC-34).
    """
    profile = state.profile
    score = None
    if state.status in _SCORED and state.last_turn_on is not None:
        score = score_candidate(profile, config, reference_date=state.last_turn_on)
    return CandidateRecord(
        status=state.status,
        disqualification_reason=state.disqualification_reason,
        needs_review_reasons=list(state.needs_review_reasons),
        score=score,
        flags=list(state.flags),
        language=state.language,
        drop_off_stage=state.drop_off_stage,
        selected_slot_id=state.selected_slot_id,
        config_version=state.config_version,
        consent=state.consent,
        fields=RecordFields(
            full_name=_field(profile.full_name),
            age=_field(profile.age),
            vehicle_type=_field(profile.vehicle_type),
            has_license=_field(profile.has_license),
            location=_field(profile.location),
            availability=_field(profile.availability),
            schedule=_field(profile.schedule),
            experience=_field(profile.experience),
            start_date=_field(profile.start_date),
        ),
        post_close_corrections=[c.model_copy(deep=True) for c in state.post_close_corrections],
    )


def _field[T](slot: Slot[T]) -> FieldRecord[T]:
    value = slot.value.model_copy(deep=True) if isinstance(slot.value, BaseModel) else slot.value
    return FieldRecord[T](status=slot.status, value=value)
