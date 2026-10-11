"""Static flow tables (plan §3.2).

The engine never hard-codes "after age comes vehicle". It asks for the first field in
`FIELD_ORDER` that is still missing, so out-of-order answers (FR-8) need no special case.
"""

from typing import Final

from sazon_screening.engine.enums import FieldName, Stage

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
