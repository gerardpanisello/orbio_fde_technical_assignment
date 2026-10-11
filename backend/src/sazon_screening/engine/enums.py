"""Language-neutral vocabulary of the engine (plan §3.1).

Every value that crosses the engine boundary (state, actions, record) is one of these
enums, never free text. The phrasing layer (003) turns them into words.
"""

from enum import StrEnum


class FieldName(StrEnum):
    """Things the engine can ask for. `zone` and `slot` are ask targets only, not stored fields."""

    consent = "consent"
    full_name = "full_name"
    age = "age"
    vehicle_type = "vehicle_type"
    has_license = "has_license"
    location = "location"
    zone = "zone"
    availability = "availability"
    schedule = "schedule"
    experience = "experience"
    start_date = "start_date"
    slot = "slot"


class Stage(StrEnum):
    """Conversation stages, in FR-5 order (declaration order matters)."""

    consent = "consent"
    name = "name"
    age = "age"
    vehicle_license = "vehicle_license"
    location = "location"
    availability = "availability"
    schedule = "schedule"
    experience = "experience"
    start_date = "start_date"
    recap = "recap"
    scheduling = "scheduling"


class Status(StrEnum):
    in_progress = "in_progress"
    interview_scheduled = "interview_scheduled"
    qualified_unscheduled = "qualified_unscheduled"
    disqualified = "disqualified"
    needs_review = "needs_review"
    abandoned = "abandoned"
    opted_out = "opted_out"


class VehicleType(StrEnum):
    motorbike = "motorbike"
    car = "car"
    bicycle = "bicycle"
    e_bike = "e_bike"
    none = "none"


class Availability(StrEnum):
    full_time = "full_time"
    part_time = "part_time"
    weekends = "weekends"


class ScheduleSlot(StrEnum):
    morning = "morning"
    afternoon = "afternoon"
    evening = "evening"
    flexible = "flexible"


class Weekday(StrEnum):
    """Declaration order matches `date.weekday()` (Monday = 0)."""

    mon = "mon"
    tue = "tue"
    wed = "wed"
    thu = "thu"
    fri = "fri"
    sat = "sat"
    sun = "sun"


class Language(StrEnum):
    es = "es"
    en = "en"


class Register(StrEnum):
    es_ES = "es-ES"  # noqa: N815 - mirrors the BCP 47 tag
    es_MX = "es-MX"  # noqa: N815 - mirrors the BCP 47 tag
    en = "en"


class Country(StrEnum):
    ES = "ES"
    MX = "MX"


class FieldStatus(StrEnum):
    valid = "valid"
    unclear = "unclear"
    not_asked = "not_asked"
    not_required = "not_required"


class PendingKind(StrEnum):
    """What kind of answer the engine is waiting for; `step()` dispatches on this."""

    ask = "ask"
    confirm_value = "confirm_value"
    confirm_ambiguous = "confirm_ambiguous"
    recap = "recap"
    correction_field = "correction_field"
    slot = "slot"


class ReaskReason(StrEnum):
    unclear = "unclear"
    not_recognised = "not_recognised"
    surname_missing = "surname_missing"
    invalid_characters = "invalid_characters"
    implausible_value = "implausible_value"
    negative_value = "negative_value"
    missing_years = "missing_years"
    empty_selection = "empty_selection"
    consent_required = "consent_required"
    slot_not_offered = "slot_not_offered"
    extraction_failed = "extraction_failed"
    value_rejected = "value_rejected"


class DisqualificationReason(StrEnum):
    under_age = "under_age"
    no_license = "no_license"
    out_of_area = "out_of_area"


class ReviewReason(StrEnum):
    age_unclear = "age_unclear"
    license_unclear = "license_unclear"
    vehicle_unclear = "vehicle_unclear"
    location_unclear = "location_unclear"
    human_requested = "human_requested"
    system_failure = "system_failure"
    abuse = "abuse"
    recap_loop = "recap_loop"
    post_close_correction = "post_close_correction"
    engine_error = "engine_error"


class Flag(StrEnum):
    surname_missing = "surname_missing"
    name_unclear = "name_unclear"
    start_date_normalised = "start_date_normalised"
    human_requested = "human_requested"
    post_close_correction = "post_close_correction"
    system_failure = "system_failure"
    abuse = "abuse"
    do_not_contact = "do_not_contact"
    engine_error = "engine_error"


class Bucket(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"
