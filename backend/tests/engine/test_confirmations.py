"""T20: value confirmations, ambiguous places and the zone question (FR-19, FR-21)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AskField,
    CloseDisqualified,
    ConfirmAmbiguous,
    ConfirmValue,
    ReaskField,
)
from sazon_screening.engine.state import Experience
from sazon_screening.vocab import Country, FieldName, FieldStatus, ReaskReason, Stage
from tests.engine.builders import (
    Convo,
    adult,
    avail,
    choice,
    consent,
    exp,
    license,
    loc,
    name,
    no,
    sched,
    unclear,
    vehicle,
    yes,
)


def at_location(config: EngineConfig, *, country_hint: Country | None = None) -> Convo:
    return (
        Convo(config, country_hint=country_hint)
        .say(consent(True))
        .say(name("Ana López"))
        .say(adult())
        .say(vehicle("car"))
        .say(license(True))
        .expect(AskField, field=FieldName.location)
    )


def at_experience(config: EngineConfig) -> Convo:
    return (
        at_location(config)
        .say(loc("Coyoacán"))
        .say(avail("full_time"))
        .say(sched("flexible"))
        .expect(AskField, field=FieldName.experience)
    )


class TestConfirmValue:
    @pytest.mark.ac("AC-16")
    def test_unusual_years_are_confirmed_then_stored(self, config: EngineConfig) -> None:
        c = at_experience(config).say(exp(45, "Glovo"))
        c.expect(
            ConfirmValue,
            field=FieldName.experience,
            value=Experience(years=45, platforms=["glovo"]),
        )
        assert c.state.profile.experience.status == FieldStatus.not_asked
        c.say(yes()).expect(AskField, field=FieldName.start_date)
        assert c.state.profile.experience.value == Experience(years=45, platforms=["glovo"])

    @pytest.mark.ac("AC-16")
    def test_rejected_value_is_asked_again(self, config: EngineConfig) -> None:
        c = at_experience(config).say(exp(45))
        c.say(no()).expect(
            ReaskField, field=FieldName.experience, reason=ReaskReason.value_rejected
        )
        c.say(exp(4)).expect(AskField, field=FieldName.start_date)
        assert c.state.profile.experience.value == Experience(years=4, platforms=[])

    def test_a_new_value_replaces_the_confirmation(self, config: EngineConfig) -> None:
        c = at_experience(config).say(exp(45)).say(exp(5))
        c.expect(AskField, field=FieldName.start_date)
        assert c.state.profile.experience.value == Experience(years=5, platforms=[])

    def test_faq_while_confirming_repeats_the_confirmation(self, config: EngineConfig) -> None:
        c = at_experience(config).say(exp(45)).say(faq_question=True)
        c.expect(ConfirmValue, field=FieldName.experience)

    @pytest.mark.ac("AC-16")
    def test_none_means_zero_years(self, config: EngineConfig) -> None:
        c = at_experience(config).say(exp("none"))
        c.expect(AskField, field=FieldName.start_date)
        assert c.state.profile.experience.value == Experience(years=0, platforms=[])


class TestAmbiguousPlace:
    @pytest.mark.ac("AC-13")
    def test_ambiguous_place_is_confirmed_by_choice(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("El Carmen"))
        c.expect(ConfirmAmbiguous, field=FieldName.location)
        options = [ref.id for ref in c.action.primary.options]  # type: ignore[union-attr]
        assert options == ["mty-el-carmen", "val-el-carmen"]
        c.say(choice("mty-el-carmen")).expect(AskField, field=FieldName.availability)
        value = c.state.profile.location.value
        assert value is not None
        assert (value.city, value.zone, value.raw_text) == (
            "monterrey",
            "mty-el-carmen",
            "El Carmen",
        )

    @pytest.mark.ac("AC-13")
    def test_country_hint_avoids_the_question(self, config: EngineConfig) -> None:
        c = at_location(config, country_hint=Country.MX).say(loc("El Carmen"))
        c.expect(AskField, field=FieldName.availability)

    def test_naming_the_city_picks_the_option(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("El Carmen")).say(loc("Monterrey"))
        c.expect(AskField, field=FieldName.availability)
        assert c.state.profile.location.value is not None
        assert c.state.profile.location.value.zone == "mty-el-carmen"

    def test_unknown_choice_reasks_with_the_same_options(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("El Carmen")).say(choice("madrid"))
        c.expect(
            ReaskField,
            field=FieldName.location,
            options=["mty-el-carmen", "val-el-carmen"],
        )
        c.say(choice("val-el-carmen")).expect(AskField, field=FieldName.availability)

    def test_only_the_first_confirmation_of_a_turn_is_asked(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("El Carmen"), exp(45))
        c.expect(ConfirmAmbiguous)
        assert c.state.profile.experience.status == FieldStatus.not_asked


class TestZone:
    @pytest.mark.ac("AC-14")
    def test_city_then_zone(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("Madrid")).expect(AskField, field=FieldName.zone)
        c.say(loc("Centro")).expect(AskField, field=FieldName.availability)
        value = c.state.profile.location.value
        assert value is not None
        assert value.zone == "mad-centro"

    def test_unserved_zone_answer_is_out_of_area(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("Madrid")).say(loc("Vallecas", known=True))
        c.expect(CloseDisqualified, reason="out_of_area")
        assert c.state.drop_off_stage == Stage.location

    def test_zone_reask_lists_the_city_zones(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("Madrid")).say(loc("xjkq", known=False))
        c.expect(
            ReaskField,
            field=FieldName.zone,
            reason=ReaskReason.not_recognised,
            options=["mad-centro", "mad-chamberi", "mad-salamanca"],
        )


class TestEdgePaths:
    def test_unclear_consent_is_reasked(self, config: EngineConfig) -> None:
        Convo(config).say(unclear("consent")).expect(
            ReaskField, field=FieldName.consent, reason=ReaskReason.consent_required
        )

    def test_unclear_confirmation_reasks_the_value(self, config: EngineConfig) -> None:
        c = at_experience(config).say(exp(45)).say(unclear("confirmation"))
        c.expect(ReaskField, field=FieldName.experience, reason=ReaskReason.unclear)

    def test_empty_turn_while_disambiguating_lists_the_options(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("El Carmen")).say()
        c.expect(ReaskField, field=FieldName.location, options=["mty-el-carmen", "val-el-carmen"])
        assert c.state.pending.kind == "confirm_ambiguous"

    def test_unknown_place_while_disambiguating_is_validated_normally(
        self, config: EngineConfig
    ) -> None:
        c = at_location(config).say(loc("El Carmen")).say(loc("xjkq", known=False))
        c.expect(ReaskField, field=FieldName.location, reason=ReaskReason.not_recognised)
        c.say(unclear("location")).expect(ReaskField, field=FieldName.location)
        c.say(loc("Coyoacán")).expect(AskField, field=FieldName.availability)

    def test_empty_turn_on_the_zone_lists_the_zones(self, config: EngineConfig) -> None:
        c = at_location(config).say(loc("Madrid")).say()
        c.expect(
            ReaskField,
            field=FieldName.zone,
            options=["mad-centro", "mad-chamberi", "mad-salamanca"],
        )
