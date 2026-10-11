"""T10: age/vehicle/license validators and the hard rules built on them (FR-17, FR-18)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.inputs import UNCLEAR, AgeAnswer
from sazon_screening.engine.rules import (
    hard_rule_failure,
    license_need,
    min_age_for,
    sync_license_requirement,
)
from sazon_screening.engine.state import ConversationState, LocationValue, Slot
from sazon_screening.engine.validators import (
    Accepted,
    Rejected,
    validate_age,
    validate_license,
    validate_vehicle,
)
from sazon_screening.vocab import (
    Country,
    DisqualificationReason,
    FieldStatus,
    ReaskReason,
    VehicleType,
)
from tests.engine.conftest import MakeConfig


def state_with(
    *,
    age: AgeAnswer | None = None,
    vehicle: VehicleType | None = None,
    has_license: bool | None = None,
    country: Country | None = None,
) -> ConversationState:
    state = ConversationState()
    if age is not None:
        state.profile.age = Slot(status=FieldStatus.valid, value=age)
    if vehicle is not None:
        state.profile.vehicle_type = Slot(status=FieldStatus.valid, value=vehicle)
    if has_license is not None:
        state.profile.has_license = Slot(status=FieldStatus.valid, value=has_license)
    if country is not None:
        state.profile.location = Slot(
            status=FieldStatus.valid,
            value=LocationValue(
                raw_text="x", country=country, city="c", zone=None, in_service_area=True
            ),
        )
    return state


class TestAgeValidator:
    @pytest.mark.ac("AC-6")
    @pytest.mark.parametrize("age", [5, 13, 100, 150, -1])
    def test_implausible_age_is_reasked(self, config: EngineConfig, age: int) -> None:
        outcome = validate_age(
            AgeAnswer(age=age),
            min_plausible=config.thresholds.min_plausible_age,
            max_plausible=config.thresholds.max_plausible_age,
        )
        assert outcome == Rejected(ReaskReason.implausible_value)

    @pytest.mark.parametrize(
        "answer", [AgeAnswer(age=17), AgeAnswer(age=14), AgeAnswer(is_adult=False)]
    )
    def test_under_age_is_still_a_valid_answer(self, answer: AgeAnswer) -> None:
        # Validators accept it; rejecting the candidate is the hard rule's job.
        assert validate_age(answer, min_plausible=14, max_plausible=99) == Accepted(answer)

    def test_unclear_is_reasked(self) -> None:
        outcome = validate_age(UNCLEAR, min_plausible=14, max_plausible=99)
        assert outcome == Rejected(ReaskReason.unclear)


class TestVehicleAndLicenseValidators:
    def test_vehicle_is_accepted(self) -> None:
        assert validate_vehicle(VehicleType.car) == Accepted(VehicleType.car)

    def test_unclear_vehicle_offers_every_type(self) -> None:
        assert validate_vehicle(UNCLEAR) == Rejected(
            ReaskReason.unclear, options=("motorbike", "car", "bicycle", "e_bike", "none")
        )

    @pytest.mark.parametrize("answer", [True, False])
    def test_license_answer_is_accepted(self, answer: bool) -> None:
        assert validate_license(answer) == Accepted(answer)

    def test_unclear_license_is_reasked(self) -> None:
        assert validate_license(UNCLEAR) == Rejected(ReaskReason.unclear)


class TestUnderAge:
    @pytest.mark.ac("AC-6")
    @pytest.mark.parametrize("answer", [AgeAnswer(age=17), AgeAnswer(is_adult=False)])
    def test_under_age_disqualifies(self, config: EngineConfig, answer: AgeAnswer) -> None:
        assert hard_rule_failure(state_with(age=answer), config) == "under_age"

    @pytest.mark.parametrize("answer", [AgeAnswer(age=18), AgeAnswer(is_adult=True)])
    def test_adult_passes(self, config: EngineConfig, answer: AgeAnswer) -> None:
        assert hard_rule_failure(state_with(age=answer), config) is None

    def test_explicit_age_wins_over_is_adult(self, config: EngineConfig) -> None:
        answer = AgeAnswer(is_adult=True, age=17)
        assert hard_rule_failure(state_with(age=answer), config) == "under_age"

    def test_unknown_country_uses_the_lowest_minimum(self, make_config: MakeConfig) -> None:
        config = make_config(screening={"min_age": {"ES": 18, "MX": 16}})
        assert min_age_for(None, config) == 16
        assert min_age_for(Country.ES, config) == 18
        # Never disqualify on an unknown country; the rule re-runs once location is known.
        assert hard_rule_failure(state_with(age=AgeAnswer(age=17)), config) is None
        mexico = state_with(age=AgeAnswer(age=17), country=Country.MX)
        assert hard_rule_failure(mexico, config) is None
        spain = state_with(age=AgeAnswer(age=17), country=Country.ES)
        assert hard_rule_failure(spain, config) == "under_age"


class TestLicense:
    @pytest.mark.ac("AC-7")
    def test_motorbike_without_license_disqualifies(self, config: EngineConfig) -> None:
        state = state_with(vehicle=VehicleType.motorbike, has_license=False)
        assert hard_rule_failure(state, config) == DisqualificationReason.no_license

    @pytest.mark.ac("AC-8")
    def test_bicycle_needs_no_license_when_configured(self, bike_free_config: EngineConfig) -> None:
        assert license_need(VehicleType.bicycle, bike_free_config) == "not_required"
        state = state_with(vehicle=VehicleType.bicycle)
        sync_license_requirement(state, bike_free_config)
        assert state.profile.has_license.status == FieldStatus.not_required

    @pytest.mark.ac("AC-8")
    def test_bicycle_without_license_is_not_disqualified(
        self, bike_free_config: EngineConfig
    ) -> None:
        state = state_with(vehicle=VehicleType.bicycle, has_license=False)
        sync_license_requirement(state, bike_free_config)
        assert state.profile.has_license.status == FieldStatus.not_required
        assert state.profile.has_license.value is False  # kept for audit
        assert hard_rule_failure(state, bike_free_config) is None

    @pytest.mark.ac("AC-9")
    def test_no_license_waits_for_vehicle_when_it_depends(
        self, bike_free_config: EngineConfig
    ) -> None:
        assert license_need(None, bike_free_config) == "depends"
        state = state_with(has_license=False)
        sync_license_requirement(state, bike_free_config)
        assert state.profile.has_license.status == FieldStatus.valid
        assert hard_rule_failure(state, bike_free_config) is None

    @pytest.mark.ac("AC-9")
    def test_switching_from_bicycle_to_motorbike_restores_the_license(
        self, bike_free_config: EngineConfig
    ) -> None:
        state = state_with(vehicle=VehicleType.bicycle, has_license=False)
        sync_license_requirement(state, bike_free_config)
        state.profile.vehicle_type = Slot(status=FieldStatus.valid, value=VehicleType.motorbike)
        sync_license_requirement(state, bike_free_config)
        assert state.profile.has_license.status == FieldStatus.valid
        assert hard_rule_failure(state, bike_free_config) == "no_license"

    def test_not_required_slot_without_value_goes_back_to_not_asked(
        self, bike_free_config: EngineConfig
    ) -> None:
        state = state_with(vehicle=VehicleType.bicycle)
        sync_license_requirement(state, bike_free_config)
        state.profile.vehicle_type = Slot(status=FieldStatus.valid, value=VehicleType.car)
        sync_license_requirement(state, bike_free_config)
        assert state.profile.has_license.status == FieldStatus.not_asked

    def test_no_license_with_unknown_vehicle_disqualifies_when_all_need_one(
        self, config: EngineConfig
    ) -> None:
        assert license_need(None, config) == "required"
        assert hard_rule_failure(state_with(has_license=False), config) == "no_license"

    def test_unclear_vehicle_counts_as_unknown(self, bike_free_config: EngineConfig) -> None:
        state = state_with(has_license=False)
        state.profile.vehicle_type = Slot(status=FieldStatus.unclear)
        assert hard_rule_failure(state, bike_free_config) is None

    def test_vehicle_none_is_not_a_disqualifier(self, config: EngineConfig) -> None:
        state = state_with(vehicle=VehicleType.none, has_license=True)
        assert hard_rule_failure(state, config) is None

    def test_under_age_is_checked_before_license(self, config: EngineConfig) -> None:
        state = state_with(age=AgeAnswer(age=16), vehicle=VehicleType.motorbike, has_license=False)
        assert hard_rule_failure(state, config) == "under_age"


def test_no_vehicle_needs_a_license_when_config_says_so(make_config: MakeConfig) -> None:
    config = make_config(screening={"license_required": {v.value: False for v in VehicleType}})
    assert license_need(None, config) == "not_required"
    state = state_with(has_license=False)
    sync_license_requirement(state, config)
    assert state.profile.has_license.status == FieldStatus.not_required
