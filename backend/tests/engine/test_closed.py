"""T25: turns on closed conversations never change screening data (FR-12, FR-15)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AnswerFaq,
    ClosedAck,
    CloseDisqualified,
    CloseNeedsReview,
    HandoffToHuman,
)
from sazon_screening.engine.inputs import Proposal
from sazon_screening.engine.state import PostCloseCorrection
from sazon_screening.vocab import (
    FieldName,
    Flag,
    ReviewReason,
    Stage,
    Status,
)
from tests.engine.builders import Convo, adult, age, avail, license, loc, vehicle

CLOSED = [
    Status.disqualified,
    Status.needs_review,
    Status.qualified_unscheduled,
    Status.waitlisted,
    Status.interview_scheduled,
]


def disqualified_no_license(config: EngineConfig) -> Convo:
    c = Convo(config).advance_to(Stage.age).say(adult()).say(vehicle("motorbike"))
    return c.say(license(False)).expect_status(Status.disqualified)


class TestPostCloseCorrection:
    @pytest.mark.ac("AC-26b")
    def test_correction_of_the_disqualifying_field_goes_to_review(
        self, config: EngineConfig
    ) -> None:
        c = disqualified_no_license(config).say(license(True), correction=True)
        c.expect(CloseNeedsReview, reasons=[ReviewReason.post_close_correction])
        c.expect_status(Status.needs_review)
        assert Flag.post_close_correction in c.state.flags
        assert c.state.profile.has_license.value is False  # never auto-applied
        assert c.state.post_close_corrections == [
            PostCloseCorrection(field=FieldName.has_license, original=False, proposed=True)
        ]
        assert c.state.disqualification_reason == "no_license"  # kept for the recruiter

    def test_age_correction_after_under_age(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.age).say(age(17)).say(age(19), correction=True)
        c.expect(CloseNeedsReview).expect_status(Status.needs_review)
        assert c.state.post_close_corrections == [
            PostCloseCorrection(
                field=FieldName.age,
                original={"is_adult": None, "age": 17, "birth_year": None},
                proposed={"is_adult": None, "age": 19, "birth_year": None},
            )
        ]

    @pytest.mark.ac("AC-26b")
    def test_correction_that_still_fails_the_rule_stays_disqualified(
        self, config: EngineConfig
    ) -> None:
        # FR-15: recorded for the recruiter, but no review is opened (17 -> 16 still fails).
        c = Convo(config).advance_to(Stage.age).say(age(17))
        c.say(age(16), correction=True).expect(ClosedAck).expect_status(Status.disqualified)
        assert c.state.post_close_corrections == [
            PostCloseCorrection(
                field=FieldName.age,
                original={"is_adult": None, "age": 17, "birth_year": None},
                proposed={"is_adult": None, "age": 16, "birth_year": None},
            )
        ]
        assert Flag.post_close_correction not in c.state.flags
        assert c.state.needs_review_reasons == []
        assert c.state.profile.age.value is not None
        assert c.state.profile.age.value.age == 17  # never applied

    @pytest.mark.ac("AC-26b")
    def test_correction_that_leaves_another_rule_failing_stays_disqualified(
        self, config: EngineConfig
    ) -> None:
        # Under-age AND no license: fixing the age alone must not open a review.
        c = Convo(config).advance_to(Stage.age).say(age(17), license(False))
        c.expect(CloseDisqualified, reason="under_age")
        c.say(age(25), correction=True).expect(ClosedAck).expect_status(Status.disqualified)
        assert len(c.state.post_close_corrections) == 1  # still recorded for the recruiter

    def test_repeated_correction_is_recorded_once(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.age).say(age(17))
        c.say(age(16), correction=True).say(age(16), correction=True)
        assert len(c.state.post_close_corrections) == 1

    def test_license_correction_with_a_bike_free_config_still_needs_the_license(
        self, bike_free_config: EngineConfig
    ) -> None:
        # Changing the vehicle to a bicycle would pass the license rule: review it.
        c = Convo(bike_free_config).advance_to(Stage.age).say(adult()).say(vehicle("motorbike"))
        c.say(license(False)).expect_status(Status.disqualified)
        c.say(vehicle("bicycle"), correction=True).expect(CloseNeedsReview)
        c.expect_status(Status.needs_review)

    def test_location_correction_after_out_of_area(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.location).say(loc("Zaragoza", known=True))
        c.expect_status(Status.disqualified)
        c.say(loc("Coyoacán"), correction=True).expect_status(Status.needs_review)
        (correction,) = c.state.post_close_corrections
        assert correction.field == FieldName.location
        assert isinstance(correction.proposed, dict)
        assert correction.proposed["zone"] == "cdmx-coyoacan"

    def test_unrelated_correction_changes_nothing(self, config: EngineConfig) -> None:
        c = disqualified_no_license(config)
        before = c.state.model_dump()
        c.say(avail("weekends"), correction=True).expect(ClosedAck)
        assert c.state.model_dump() == before

    def test_same_value_is_not_a_correction(self, config: EngineConfig) -> None:
        c = disqualified_no_license(config).say(license(False), correction=True)
        c.expect(ClosedAck).expect_status(Status.disqualified)


class TestClosedStatuses:
    @pytest.mark.ac("AC-27")
    def test_after_handoff_turns_get_an_acknowledgement(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.schedule).say(wants_human=True).expect(HandoffToHuman)
        c.say().expect(ClosedAck).expect_status(Status.needs_review)

    @pytest.mark.parametrize("status", CLOSED)
    def test_faq_on_a_closed_conversation(self, config: EngineConfig, status: Status) -> None:
        c = Convo(config).advance_to_status(status)
        profile = c.state.profile.model_copy(deep=True)
        c.say(avail("weekends"), vehicle("car"), faq_question=True)
        c.expect(ClosedAck).expect_prefaces(AnswerFaq).expect_status(status)
        assert c.state.profile == profile

    @pytest.mark.parametrize("status", CLOSED)
    def test_events_on_a_closed_conversation(self, config: EngineConfig, status: Status) -> None:
        c = Convo(config).advance_to_status(status)
        c.select_slot("s1").expect(ClosedAck).expect_status(status)


BOOKED = [Status.interview_scheduled, Status.qualified_unscheduled, Status.waitlisted]


class TestCorrectionAfterBooking:
    """FR-15: a qualified candidate who now fails a hard rule goes to a recruiter."""

    @pytest.mark.ac("AC-26c")
    @pytest.mark.parametrize("status", BOOKED)
    @pytest.mark.parametrize(
        ("proposal", "field"),
        [
            (age(16), FieldName.age),
            (license(False), FieldName.has_license),
            (loc("Zaragoza", known=True), FieldName.location),
        ],
        ids=["under_age", "no_license", "out_of_area"],
    )
    def test_failing_correction_goes_to_review(
        self, config: EngineConfig, status: Status, proposal: Proposal, field: FieldName
    ) -> None:
        c = Convo(config).advance_to_status(status)
        profile = c.state.profile.model_copy(deep=True)
        slot = c.state.selected_slot_id
        c.say(proposal, correction=True)
        c.expect(CloseNeedsReview, reasons=[ReviewReason.post_close_correction])
        c.expect_status(Status.needs_review)
        assert Flag.post_close_correction in c.state.flags
        assert c.state.profile == profile  # never applied
        assert c.state.selected_slot_id == slot  # the recruiter decides about the booking
        assert [pc.field for pc in c.state.post_close_corrections] == [field]
        assert c.state.disqualification_reason is None

    @pytest.mark.ac("AC-26c")
    @pytest.mark.parametrize("status", BOOKED)
    def test_correction_that_still_passes_changes_nothing(
        self, config: EngineConfig, status: Status
    ) -> None:
        c = Convo(config).advance_to_status(status)
        before = c.state.model_dump()
        c.say(age(30), loc("Roma"), correction=True).expect(ClosedAck).expect_status(status)
        assert c.state.model_dump() == before
