"""Conversation state (plan §3.4): everything needed to resume a conversation and report on it.

The state is a plain serialisable model so 004 can store it as JSON. `step()` deep-copies
it on entry and mutates only its private copy, so a caller's state never changes.
Lists that are conceptually sets are kept sorted/unique so JSON output is deterministic.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from sazon_screening.engine.enums import (
    Availability,
    Country,
    DisqualificationReason,
    FieldName,
    FieldStatus,
    Flag,
    Language,
    PendingKind,
    ReviewReason,
    ScheduleSlot,
    Stage,
    Status,
    VehicleType,
)
from sazon_screening.engine.inputs import AgeAnswer


class _State(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Slot[T](_State):
    """One screening field: its value and how we got it (FR-31 field status)."""

    status: FieldStatus = FieldStatus.not_asked
    value: T | None = None


class LocationValue(_State):
    raw_text: str  # what the candidate said, kept for audit (NFR-6)
    country: Country | None
    city: str | None  # config city id
    zone: str | None  # config zone id; None while the zone is still to be asked
    in_service_area: bool  # False only for a real place we do not serve


class Experience(_State):
    years: int
    platforms: list[str]  # config platform ids, or "other:<text>"


class Profile(_State):
    full_name: Slot[str] = Field(default_factory=Slot[str])
    age: Slot[AgeAnswer] = Field(default_factory=Slot[AgeAnswer])
    vehicle_type: Slot[VehicleType] = Field(default_factory=Slot[VehicleType])
    has_license: Slot[bool] = Field(default_factory=Slot[bool])
    location: Slot[LocationValue] = Field(default_factory=Slot[LocationValue])
    availability: Slot[list[Availability]] = Field(default_factory=Slot[list[Availability]])
    schedule: Slot[list[ScheduleSlot]] = Field(default_factory=Slot[list[ScheduleSlot]])
    experience: Slot[Experience] = Field(default_factory=Slot[Experience])
    start_date: Slot[date] = Field(default_factory=Slot[date])


class AreaRef(BaseModel):
    """A resolved service area: a zone, or a city served as a whole."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str  # zone id, or city id when there is no zone
    country: Country
    city: str
    zone: str | None


class PendingAsk(_State):
    """What the engine is waiting for. `step()` dispatches on `kind`."""

    kind: PendingKind
    field: FieldName | None = None  # None for recap / correction_field
    candidate_value: Experience | None = None  # confirm_value payload
    options: list[AreaRef] = []  # confirm_ambiguous payload
    raw_text: str | None = None  # confirm_ambiguous: what the candidate said (audit)


class PostCloseCorrection(_State):
    """A correction received after disqualification: stored, never applied (FR-15)."""

    field: FieldName
    original: JsonValue
    proposed: JsonValue


class ConversationState(_State):
    state_version: Literal[1] = 1
    status: Status = Status.in_progress
    stage: Stage = Stage.consent
    pending: PendingAsk = Field(
        default_factory=lambda: PendingAsk(kind=PendingKind.ask, field=FieldName.consent)
    )
    consent: bool | None = None
    profile: Profile = Field(default_factory=Profile)
    reasks: dict[FieldName, int] = {}  # FR-23 counters; never reset (audit)
    consecutive_extraction_failures: int = 0
    abuse_count: int = 0
    recap_rounds: int = 0  # number of show_recap actions emitted
    flags: list[Flag] = []  # sorted, unique: use add_flag
    needs_review_reasons: list[ReviewReason] = []  # first-occurrence order: use add_reason
    disqualification_reason: DisqualificationReason | None = None
    drop_off_stage: Stage | None = None
    language: Language = Language.es
    country_hint: Country | None = None
    offered_slot_ids: list[str] = []
    selected_slot_id: str | None = None
    post_close_corrections: list[PostCloseCorrection] = []
    config_version: str = ""
    last_turn_on: date | None = None  # injected `today` of the last step (scoring reference)


def add_flag(state: ConversationState, flag: Flag) -> None:
    """Add a flag once; flags are a set, stored sorted for deterministic JSON."""
    state.flags = sorted({*state.flags, flag})


def add_reason(state: ConversationState, reason: ReviewReason) -> None:
    """Add a review reason once, keeping the order in which reasons arose."""
    if reason not in state.needs_review_reasons:
        state.needs_review_reasons = [*state.needs_review_reasons, reason]
