"""Hard qualification rules (ADR 0004, plan §3.7).

These functions are the only place where a candidate can be rejected. They read stored
values and config, never raw input, so every disqualification traces to one config rule
and one stored value (NFR-6). Ambiguity never disqualifies: an unknown value is treated
in the candidate's favour and the rule runs again once it is known.
"""

from typing import Final, Literal

from sazon_screening.config import EngineConfig
from sazon_screening.engine.enums import (
    Country,
    DisqualificationReason,
    FieldName,
    FieldStatus,
    ReviewReason,
    VehicleType,
)
from sazon_screening.engine.state import ConversationState, Profile

LicenseNeed = Literal["required", "not_required", "depends"]

# Which fields caused each disqualification: a later correction to one of these is
# stored for a recruiter to review, never auto-applied (FR-15).
DISQUALIFYING_FIELDS: Final[dict[DisqualificationReason, frozenset[FieldName]]] = {
    DisqualificationReason.under_age: frozenset({FieldName.age}),
    DisqualificationReason.no_license: frozenset({FieldName.has_license, FieldName.vehicle_type}),
    DisqualificationReason.out_of_area: frozenset({FieldName.location}),
}
# Every field a hard rule reads: a later change to one of these can change the outcome.
HARD_RULE_FIELDS: Final[frozenset[FieldName]] = frozenset().union(*DISQUALIFYING_FIELDS.values())


def known_vehicle(profile: Profile) -> VehicleType | None:
    """The vehicle, if the candidate gave a clear one; unclear counts as unknown."""
    slot = profile.vehicle_type
    return slot.value if slot.status is FieldStatus.valid else None


def license_need(vehicle: VehicleType | None, config: EngineConfig) -> LicenseNeed:
    """Does this candidate need a license? Unknown vehicle -> "depends" unless config is uniform.

    With the default config every vehicle needs one, so a "no license" answer can
    disqualify before we know the vehicle (FR-18). If some vehicles are exempt, we wait.
    """
    screening = config.screening
    if vehicle is not None:
        return "required" if screening.requires_license(vehicle) else "not_required"
    needs = {screening.requires_license(v) for v in VehicleType}
    if needs == {True}:
        return "required"
    if needs == {False}:
        return "not_required"
    return "depends"


def min_age_for(country: Country | None, config: EngineConfig) -> int:
    """Minimum age for the country; unknown country -> the most lenient configured value."""
    min_age = config.screening.min_age
    if country is not None and country in min_age:
        return min_age[country]
    return min(min_age.values())


def hard_rule_failure(
    state: ConversationState, config: EngineConfig
) -> DisqualificationReason | None:
    """First failing knock-out rule, in stage order, or None if the candidate can continue."""
    profile = state.profile
    if _is_under_age(profile, config):
        return DisqualificationReason.under_age
    if _lacks_required_license(profile, config):
        return DisqualificationReason.no_license
    if _is_out_of_area(profile):
        return DisqualificationReason.out_of_area
    return None


def sync_license_requirement(state: ConversationState, config: EngineConfig) -> None:
    """Keep the license slot consistent with the current vehicle (AC-8, AC-9).

    A license that is not required is stored as `not_required` (the value is kept for
    audit). If the vehicle later changes to one that needs a license, the slot comes
    back: `valid` if we already had an answer, otherwise it is asked.
    """
    slot = state.profile.has_license
    if license_need(known_vehicle(state.profile), config) == "not_required":
        slot.status = FieldStatus.not_required
    elif slot.status is FieldStatus.not_required:
        slot.status = FieldStatus.not_asked if slot.value is None else FieldStatus.valid


def _is_under_age(profile: Profile, config: EngineConfig) -> bool:
    slot = profile.age
    if slot.status is not FieldStatus.valid or slot.value is None:
        return False
    answer = slot.value
    if answer.age is not None:  # an explicit age beats "I'm an adult"
        location = profile.location.value
        country = location.country if location is not None else None
        return answer.age < min_age_for(country, config)
    return answer.is_adult is False


def _lacks_required_license(profile: Profile, config: EngineConfig) -> bool:
    slot = profile.has_license
    if slot.status is not FieldStatus.valid or slot.value is not False:
        return False
    return license_need(known_vehicle(profile), config) == "required"


def _is_out_of_area(profile: Profile) -> bool:
    """Only a real place we do not serve; unrecognised text is re-asked, never rejected."""
    slot = profile.location
    return (
        slot.status is FieldStatus.valid
        and slot.value is not None
        and not slot.value.in_service_area
    )


def review_reasons(profile: Profile, config: EngineConfig) -> list[ReviewReason]:
    """Hard fields we could not read: a recruiter decides at recap (FR-24, AC-19).

    Ambiguity never disqualifies. Reasons are listed in stage order.
    """
    reasons: list[ReviewReason] = []
    if profile.age.status is FieldStatus.unclear:
        reasons.append(ReviewReason.age_unclear)
    if (
        profile.vehicle_type.status is FieldStatus.unclear
        and license_need(None, config) == "depends"
        and profile.has_license.value is not True
    ):
        reasons.append(ReviewReason.vehicle_unclear)  # it decides whether a license is needed
    need = license_need(known_vehicle(profile), config)
    if profile.has_license.status is FieldStatus.unclear and need != "not_required":
        reasons.append(ReviewReason.license_unclear)
    if profile.location.status is FieldStatus.unclear:
        reasons.append(ReviewReason.location_unclear)
    return reasons
