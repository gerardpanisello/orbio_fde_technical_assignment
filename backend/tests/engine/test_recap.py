"""T21/T23: hard-field exhaustion, the recap loop and corrections (FR-9, FR-24, FR-25)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AckCorrection,
    AskCorrectionField,
    AskField,
    CloseDisqualified,
    CloseNeedsReview,
    CloseQualifiedUnscheduled,
    OfferSlots,
    ReaskField,
    ShowRecap,
)
from sazon_screening.engine.enums import (
    Availability,
    FieldName,
    FieldStatus,
    PendingKind,
    ReaskReason,
    ReviewReason,
    Stage,
    Status,
)
from sazon_screening.engine.inputs import Asap, Proposal
from tests.engine.builders import (
    Convo,
    adult,
    avail,
    consent,
    exp,
    license,
    loc,
    name,
    no,
    sched,
    start_date,
    unclear,
    vehicle,
    yes,
)

SERVED_CITIES = ["madrid", "barcelona", "valencia", "cdmx", "monterrey"]


def at_location(c: Convo) -> Convo:
    return (
        c.say(consent(True))
        .say(name("Ana López"))
        .say(adult())
        .say(vehicle("car"))
        .say(license(True))
        .expect(AskField, field=FieldName.location)
    )


def profile_answers(c: Convo) -> Convo:
    return (
        c.say(avail("full_time"))
        .say(sched("flexible"))
        .say(exp(3, "Glovo"))
        .say(start_date(Asap()))
    )


def at_recap(config: EngineConfig) -> Convo:
    c = profile_answers(at_location(Convo(config)).say(loc("Coyoacán")))
    return c.expect(ShowRecap).expect_status(Status.in_progress)


class TestHardExhaustion:
    @pytest.mark.ac("AC-19")
    def test_unclear_location_goes_to_review_at_recap(self, config: EngineConfig) -> None:
        c = at_location(Convo(config))
        c.say(unclear("location")).expect(ReaskField, field=FieldName.location)
        c.say(unclear("location")).expect(ReaskField, field=FieldName.location)
        c.say(unclear("location")).expect(AskField, field=FieldName.availability)
        assert c.state.profile.location.status == FieldStatus.unclear
        profile_answers(c)  # the profile is still collected
        c.expect(CloseNeedsReview, reasons=[ReviewReason.location_unclear])
        c.expect_status(Status.needs_review)
        assert c.state.disqualification_reason is None
        assert c.state.drop_off_stage == Stage.recap
        assert all(a.primary.type != "close_disqualified" for a in c.history)

    @pytest.mark.ac("AC-11")
    def test_unrecognisable_place_is_reviewed_never_rejected(self, config: EngineConfig) -> None:
        c = at_location(Convo(config))
        for _ in range(2):
            c.say(loc("xjkq", known=False)).expect(
                ReaskField,
                field=FieldName.location,
                reason=ReaskReason.not_recognised,
                options=SERVED_CITIES,
            )
        c.say(loc("xjkq", known=False)).expect(AskField, field=FieldName.availability)
        profile_answers(c).expect(CloseNeedsReview, reasons=[ReviewReason.location_unclear])

    def test_unclear_zone_keeps_the_city_and_goes_to_review(self, config: EngineConfig) -> None:
        c = at_location(Convo(config)).say(loc("Madrid"))
        for _ in range(3):
            c.say(loc("xjkq", known=False))
        c.expect(AskField, field=FieldName.availability)
        location = c.state.profile.location
        assert location.status == FieldStatus.unclear
        assert location.value is not None
        assert location.value.city == "madrid"
        profile_answers(c).expect(CloseNeedsReview, reasons=[ReviewReason.location_unclear])

    def test_unclear_vehicle_matters_when_the_license_depends_on_it(
        self, bike_free_config: EngineConfig
    ) -> None:
        c = Convo(bike_free_config).say(consent(True)).say(name("Ana López")).say(adult())
        c.say(license(False)).expect(AskField, field=FieldName.vehicle_type)
        for _ in range(3):
            c.say(unclear("vehicle_type"))
        c.expect(AskField, field=FieldName.location).expect_status(Status.in_progress)
        profile_answers(c.say(loc("Coyoacán")))
        c.expect(CloseNeedsReview, reasons=[ReviewReason.vehicle_unclear])

    def test_unclear_age_goes_to_review(self, config: EngineConfig) -> None:
        c = Convo(config).say(consent(True)).say(name("Ana López"))
        for _ in range(3):
            c.say(unclear("age"))
        c.say(vehicle("car")).say(license(True)).say(loc("Coyoacán"))
        profile_answers(c).expect(CloseNeedsReview, reasons=[ReviewReason.age_unclear])


class TestRecap:
    def test_recap_shows_a_copy_of_the_profile(self, config: EngineConfig) -> None:
        c = at_recap(config)
        recap = c.action.primary
        assert isinstance(recap, ShowRecap)
        assert recap.profile == c.state.profile
        assert recap.profile is not c.state.profile
        assert c.state.stage == Stage.recap
        assert c.state.pending.kind == PendingKind.recap

    @pytest.mark.ac("AC-22")
    def test_confirming_offers_slots(self, config: EngineConfig) -> None:
        c = at_recap(config).say(yes(), offered_slots=["s1", "s2"])
        c.expect(OfferSlots, slot_ids=["s1", "s2"]).expect_status(Status.in_progress)
        assert c.state.stage == Stage.scheduling

    def test_confirming_without_slots_is_qualified_unscheduled(self, config: EngineConfig) -> None:
        c = at_recap(config).say(yes())
        c.expect(CloseQualifiedUnscheduled).expect_status(Status.qualified_unscheduled)
        assert c.state.drop_off_stage is None

    @pytest.mark.ac("AC-23")
    def test_correcting_a_field_shows_the_recap_again(self, config: EngineConfig) -> None:
        c = at_recap(config).say(avail("weekends"), correction=True)
        c.expect(ShowRecap)
        recap = c.action.primary
        assert isinstance(recap, ShowRecap)
        assert recap.profile.availability.value == [Availability.weekends]

    @pytest.mark.ac("AC-24")
    @pytest.mark.parametrize(
        ("proposal", "reason"),
        [(loc("Vallecas, Madrid", known=True), "out_of_area"), (license(False), "no_license")],
    )
    def test_correction_that_fails_a_hard_rule_disqualifies(
        self, config: EngineConfig, proposal: Proposal, reason: str
    ) -> None:
        c = at_recap(config).say(proposal, correction=True)
        c.expect(CloseDisqualified, reason=reason).expect_status(Status.disqualified)

    @pytest.mark.ac("AC-25")
    def test_no_without_a_field_asks_what_to_correct(self, config: EngineConfig) -> None:
        c = at_recap(config).say(no()).expect(AskCorrectionField)
        c.say(sched("morning")).expect(ShowRecap)
        c.say(yes(), offered_slots=["s1"]).expect(OfferSlots)

    def test_yes_after_asking_what_to_correct_continues(self, config: EngineConfig) -> None:
        c = at_recap(config).say(no()).say(yes(), offered_slots=["s1"])
        c.expect(OfferSlots)

    def test_faq_at_recap_repeats_it_without_counting(self, config: EngineConfig) -> None:
        c = at_recap(config).say(faq_question=True).expect(ShowRecap)
        assert c.state.recap_rounds == 1

    def test_recap_loop_goes_to_review(self, config: EngineConfig) -> None:
        c = at_recap(config)
        c.say(avail("weekends")).expect(ShowRecap)
        c.say(avail("part_time")).expect(ShowRecap)
        c.say(avail("full_time")).expect(CloseNeedsReview, reasons=[ReviewReason.recap_loop])
        c.expect_status(Status.needs_review)


@pytest.mark.ac("AC-21")
def test_correction_of_the_city_is_acknowledged(config: EngineConfig) -> None:
    c = at_location(Convo(config)).say(loc("Chamberí, Madrid"))
    c.say(avail("full_time")).expect(AskField, field=FieldName.schedule)
    c.say(loc("Coyoacán"), correction=True)
    c.expect(AskField, field=FieldName.schedule).expect_prefaces(AckCorrection)
    assert c.action.prefaces == [AckCorrection(fields=[FieldName.location])]
    value = c.state.profile.location.value
    assert value is not None
    assert (value.city, value.zone) == ("cdmx", "cdmx-coyoacan")
    c.expect_status(Status.in_progress)


def test_faq_while_asking_what_to_correct_repeats_the_question(config: EngineConfig) -> None:
    at_recap(config).say(no()).say(faq_question=True).expect(AskCorrectionField)


def test_unclear_license_goes_to_review(config: EngineConfig) -> None:
    c = Convo(config).say(consent(True)).say(name("Ana López")).say(adult()).say(vehicle("car"))
    for _ in range(3):
        c.say(unclear("has_license"))
    profile_answers(c.say(loc("Coyoacán")))
    c.expect(CloseNeedsReview, reasons=[ReviewReason.license_unclear])
