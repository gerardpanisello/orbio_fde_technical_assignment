"""T19: the re-ask policy (FR-23, FR-24): at most 2 re-asks, then store `unclear` and go on."""

from collections.abc import Callable

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import AskField, ReaskField
from sazon_screening.engine.enums import FieldName, FieldStatus, Flag, ReaskReason, Status
from tests.engine.builders import (
    Convo,
    adult,
    age,
    consent,
    license,
    loc,
    name,
    unclear,
    vehicle,
)

AVAILABILITY_OPTIONS = ["full_time", "part_time", "weekends"]


def at_availability(config: EngineConfig) -> Convo:
    return (
        Convo(config)
        .say(consent(True))
        .say(name("Ana López"))
        .say(adult())
        .say(vehicle("car"))
        .say(license(True))
        .say(loc("Coyoacán"))
        .expect(AskField, field=FieldName.availability)
    )


@pytest.mark.ac("AC-18")
def test_soft_field_is_reasked_twice_then_stored_unclear(config: EngineConfig) -> None:
    c = at_availability(config)
    c.say(unclear("availability")).expect(
        ReaskField, field=FieldName.availability, options=AVAILABILITY_OPTIONS
    )
    c.say(unclear("availability")).expect(
        ReaskField, field=FieldName.availability, options=AVAILABILITY_OPTIONS
    )
    c.say(unclear("availability")).expect(AskField, field=FieldName.schedule)
    assert c.state.profile.availability.status == FieldStatus.unclear
    assert c.reasks(FieldName.availability) == 3
    c.expect_status(Status.in_progress)


def faq_only(c: Convo) -> Convo:
    return c.say(faq_question=True)


def other_fields_only(c: Convo) -> Convo:
    return c.say(age(30))  # a valid answer to a field we did not ask about


def extraction_failed(c: Convo) -> Convo:
    return c.say(extraction_failed=True)


@pytest.mark.ac("AC-20")
@pytest.mark.parametrize("turn", [faq_only, other_fields_only, extraction_failed])
def test_neutral_turns_do_not_use_a_reask(
    config: EngineConfig, turn: Callable[[Convo], Convo]
) -> None:
    c = at_availability(config).say(unclear("availability"))
    assert c.reasks(FieldName.availability) == 1
    turn(c)
    assert c.reasks(FieldName.availability) == 1
    assert c.state.pending.field == FieldName.availability


def test_empty_turn_counts_as_a_failed_attempt(config: EngineConfig) -> None:
    c = at_availability(config).say()
    c.expect(ReaskField, field=FieldName.availability, reason=ReaskReason.unclear)
    assert c.reasks(FieldName.availability) == 1


def test_invalid_value_gives_its_reason(config: EngineConfig) -> None:
    c = Convo(config).say(consent(True)).say(name("Ana López")).say(age(150))
    c.expect(ReaskField, field=FieldName.age, reason=ReaskReason.implausible_value)


@pytest.mark.ac("AC-15")
def test_first_name_only_is_asked_once_for_the_surname(config: EngineConfig) -> None:
    c = Convo(config).say(consent(True))
    c.say(name("Ana")).expect(
        ReaskField, field=FieldName.full_name, reason=ReaskReason.surname_missing
    )
    c.say(name("Ana")).expect(AskField, field=FieldName.age)
    assert c.state.profile.full_name.value == "Ana"
    assert c.state.profile.full_name.status == FieldStatus.valid
    assert Flag.surname_missing in c.state.flags


def test_unclear_name_is_flagged_and_the_flow_continues(config: EngineConfig) -> None:
    c = Convo(config).say(consent(True))
    c.say(unclear("full_name")).expect(ReaskField, field=FieldName.full_name)
    c.say(unclear("full_name")).expect(ReaskField, field=FieldName.full_name)
    c.say(unclear("full_name")).expect(AskField, field=FieldName.age)
    assert c.state.profile.full_name.status == FieldStatus.unclear
    assert Flag.name_unclear in c.state.flags


def test_vehicle_reask_lists_vehicle_types(config: EngineConfig) -> None:
    c = Convo(config).say(consent(True), name("Ana López"), adult()).say()
    c.expect(
        ReaskField,
        field=FieldName.vehicle_type,
        options=["motorbike", "car", "bicycle", "e_bike", "none"],
    )
