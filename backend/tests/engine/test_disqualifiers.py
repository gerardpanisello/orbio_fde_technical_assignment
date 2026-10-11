"""T18: hard rules applied inside the conversation loop (FR-17, FR-18, FR-19)."""

from collections.abc import Callable

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import AskField, CloseDisqualified, ReaskField
from sazon_screening.vocab import (
    DisqualificationReason,
    FieldName,
    FieldStatus,
    ReaskReason,
    Stage,
    Status,
)
from tests.engine.builders import (
    Convo,
    adult,
    age,
    avail,
    born,
    consent,
    license,
    loc,
    name,
    vehicle,
)

UNDER_AGE = CloseDisqualified(reason=DisqualificationReason.under_age)


def at_consent(config: EngineConfig) -> Convo:
    return Convo(config)


def at_age(config: EngineConfig) -> Convo:
    return Convo(config).say(consent(True)).say(name("Ana López"))


def at_vehicle(config: EngineConfig) -> Convo:
    return at_age(config).say(age(25))


def at_location(config: EngineConfig) -> Convo:
    return at_age(config).say(age(25)).say(vehicle("car")).say(license(True))


class TestUnderAge:
    @pytest.mark.ac("AC-6")
    def test_under_age_with_consent_and_name(self, config: EngineConfig) -> None:
        c = Convo(config).say(consent(True), name("Ana López"), age(17))
        c.expect(CloseDisqualified, reason=DisqualificationReason.under_age)
        c.expect_status(Status.disqualified)
        assert c.state.disqualification_reason == DisqualificationReason.under_age
        assert c.state.profile.full_name.value == "Ana López"  # other fields kept

    @pytest.mark.ac("AC-6")
    @pytest.mark.parametrize(
        ("start", "stage"),
        [(at_age, Stage.age), (at_vehicle, Stage.vehicle_license), (at_location, Stage.location)],
    )
    @pytest.mark.parametrize("with_others", [False, True])
    def test_under_age_at_any_knockout_stage(
        self,
        config: EngineConfig,
        start: Callable[[EngineConfig], Convo],
        stage: Stage,
        with_others: bool,
    ) -> None:
        c = start(config)
        assert c.state.stage == stage
        others = [avail("weekends"), loc("Coyoacán")] if with_others else []
        c.say(age(17), *others).expect(CloseDisqualified, reason="under_age")
        c.expect_status(Status.disqualified)
        assert c.state.drop_off_stage == stage
        if with_others:
            assert c.state.profile.availability.status == FieldStatus.valid
            assert c.state.profile.location.status == FieldStatus.valid

    def test_disqualified_conversation_reports_the_reason_once(self, config: EngineConfig) -> None:
        c = at_age(config).say(age(17))
        assert c.action.primary == UNDER_AGE


class TestLicense:
    @pytest.mark.ac("AC-7")
    def test_motorbike_then_no_license(self, config: EngineConfig) -> None:
        c = at_age(config).say(adult()).say(vehicle("motorbike"))
        c.expect(AskField, field=FieldName.has_license)
        c.say(license(False)).expect(CloseDisqualified, reason="no_license")
        assert c.state.drop_off_stage == Stage.vehicle_license

    @pytest.mark.ac("AC-8")
    def test_bicycle_skips_the_license(self, bike_free_config: EngineConfig) -> None:
        c = at_age(bike_free_config).say(adult()).say(vehicle("bicycle"))
        c.expect(AskField, field=FieldName.location)
        assert c.state.profile.has_license.status == FieldStatus.not_required

    @pytest.mark.ac("AC-9")
    def test_no_license_waits_for_the_vehicle(self, bike_free_config: EngineConfig) -> None:
        c = at_age(bike_free_config).say(adult(), license(False))
        c.expect(AskField, field=FieldName.vehicle_type).expect_status(Status.in_progress)
        c.say(vehicle("motorbike")).expect(CloseDisqualified, reason="no_license")

    @pytest.mark.ac("AC-9")
    def test_no_license_then_bicycle_continues(self, bike_free_config: EngineConfig) -> None:
        c = at_age(bike_free_config).say(adult(), license(False))
        c.say(vehicle("bicycle")).expect(AskField, field=FieldName.location)

    def test_no_license_before_vehicle_with_default_config(self, config: EngineConfig) -> None:
        at_age(config).say(adult(), license(False)).expect(CloseDisqualified, reason="no_license")


class TestOutOfArea:
    @pytest.mark.ac("AC-10")
    def test_unserved_zone_of_a_served_city(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("Vallecas, Madrid", known=True))
        c.expect(CloseDisqualified, reason="out_of_area").expect_status(Status.disqualified)
        assert c.state.drop_off_stage == Stage.location

    @pytest.mark.ac("AC-11")
    def test_real_unserved_city(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("Zaragoza", known=True))
        c.expect(CloseDisqualified, reason="out_of_area")


class TestBirthYear:
    """Spec 003 decision 2: "nací en el 2000" -> the engine works out the age from today."""

    @pytest.mark.ac("AC-38")
    def test_birth_year_of_an_adult_is_accepted(self, config: EngineConfig) -> None:
        c = at_age(config).say(born(2000))
        c.expect(AskField, field=FieldName.vehicle_type).expect_status(Status.in_progress)
        assert c.state.profile.age.status == FieldStatus.valid

    @pytest.mark.ac("AC-38")
    def test_birth_year_of_a_minor_disqualifies(self, config: EngineConfig) -> None:
        c = at_age(config).say(born(2010))
        c.expect(CloseDisqualified, reason=DisqualificationReason.under_age)
        c.expect_status(Status.disqualified)

    @pytest.mark.ac("AC-38")
    def test_boundary_year_is_reasked_never_disqualified(self, config: EngineConfig) -> None:
        # Born 2008: 17 or 18 on 2026-10-12, depending on the birthday.
        c = at_age(config).say(born(2008))
        c.expect(ReaskField, field=FieldName.age, reason=ReaskReason.unclear)
        c.expect_status(Status.in_progress)
        assert c.reasks(FieldName.age) == 1

    @pytest.mark.ac("AC-38")
    def test_implausible_birth_year_is_reasked(self, config: EngineConfig) -> None:
        c = at_age(config).say(born(1900))
        c.expect(ReaskField, field=FieldName.age, reason=ReaskReason.implausible_value)

    @pytest.mark.ac("AC-38")
    def test_explicit_age_wins_over_birth_year(self, config: EngineConfig) -> None:
        c = at_age(config).say(born(2010, years=25))
        c.expect(AskField, field=FieldName.vehicle_type).expect_status(Status.in_progress)
