"""Static flow tables (plan §3.2).

The engine never hard-codes "after age comes vehicle". It asks for the first field in
`FIELD_ORDER` that is still missing, so out-of-order answers (FR-8) need no special case.
"""

from typing import Final

from sazon_screening.config import EngineConfig
from sazon_screening.engine.enums import FieldName, FieldStatus, Stage
from sazon_screening.engine.location import needs_zone
from sazon_screening.engine.state import ConversationState

# Knock-outs first, then profile (Spec 001 §3). `zone` follows `location`: it is only
# asked when the matched city has zones and none was given.
FIELD_ORDER: Final[tuple[FieldName, ...]] = (
    FieldName.consent,
    FieldName.full_name,
    FieldName.age,
    FieldName.vehicle_type,
    FieldName.has_license,
    FieldName.location,
    FieldName.zone,
    FieldName.availability,
    FieldName.schedule,
    FieldName.experience,
    FieldName.start_date,
)

# The stage a pending field belongs to; this is what `drop_off_stage` reports (FR-6).
FIELD_STAGE: Final[dict[FieldName, Stage]] = {
    FieldName.consent: Stage.consent,
    FieldName.full_name: Stage.name,
    FieldName.age: Stage.age,
    FieldName.vehicle_type: Stage.vehicle_license,
    FieldName.has_license: Stage.vehicle_license,
    FieldName.location: Stage.location,
    FieldName.zone: Stage.location,
    FieldName.availability: Stage.availability,
    FieldName.schedule: Stage.schedule,
    FieldName.experience: Stage.experience,
    FieldName.start_date: Stage.start_date,
    FieldName.slot: Stage.scheduling,
}

# Hard fields decide qualification; when they run out of re-asks the candidate goes to
# needs_review, never disqualified (FR-24). vehicle_type is hard only when the license
# requirement depends on it, so rules.py handles it dynamically.
HARD_FIELDS: Final[frozenset[FieldName]] = frozenset(
    {FieldName.age, FieldName.has_license, FieldName.location, FieldName.zone}
)

# Soft fields only feed the score; exhausting them stores `unclear` and moves on.
SOFT_FIELDS: Final[frozenset[FieldName]] = frozenset(
    {FieldName.availability, FieldName.schedule, FieldName.experience, FieldName.start_date}
)


def next_missing_field(state: ConversationState, config: EngineConfig) -> FieldName | None:
    """The first field, in stage order, that still needs an answer.

    This one query replaces a hand-written transition table: whatever arrived out of
    order is simply skipped (FR-8). `unclear` counts as done (FR-24); a license that is
    `not_required` is skipped (rules.sync_license_requirement keeps that status current).
    """
    for field in FIELD_ORDER:
        if _is_missing(field, state, config):
            return field
    return None


def _is_missing(field: FieldName, state: ConversationState, config: EngineConfig) -> bool:
    location = state.profile.location
    match field:
        case FieldName.consent:
            return state.consent is not True
        case FieldName.location:
            return location.status is FieldStatus.not_asked and location.value is None
        case FieldName.zone:
            # A served city split into zones, with no zone yet: stored partially (AC-14).
            return (
                location.status is FieldStatus.not_asked
                and location.value is not None
                and needs_zone(location.value, config)
            )
        case _:
            slot = getattr(state.profile, field.value)
            return bool(slot.status is FieldStatus.not_asked)
