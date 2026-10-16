"""Spec 010 in the engine: move or cancel a booked interview, and a slot taken meanwhile
(ADR 0005 amendment 2026-10-16, spec 002 AC-43..AC-45)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AnswerFaq,
    ClosedAck,
    CloseInterviewCancelled,
    CloseQualifiedUnscheduled,
    ConfirmInterview,
    KeepInterview,
    OfferSlots,
    ReaskField,
)
from sazon_screening.engine.inputs import SlotTaken
from sazon_screening.vocab import FieldName, Flag, Stage, Status
from tests.engine.builders import Convo, age, yes

FRESH = ["s1", "s2", "s3"]  # what the caller offers now; s1 is the booked one


def booked(config: EngineConfig) -> Convo:
    return Convo(config).advance_to_status(Status.interview_scheduled)  # s1


class TestReschedule:
    @pytest.mark.ac("AC-43")
    def test_reschedule_offers_other_slots_and_keeps_the_booking_until_a_pick(
        self, config: EngineConfig
    ) -> None:
        c = booked(config).say(reschedule_interview=True, offered_slots=FRESH)
        c.expect(OfferSlots, slot_ids=["s2", "s3"], reason="reschedule")
        c.expect_status(Status.in_progress)
        assert c.state.selected_slot_id == "s1"  # released only when a new one is booked
        assert c.state.stage is Stage.scheduling
        c.select_slot("s3").expect(ConfirmInterview, slot_id="s3")
        c.expect_status(Status.interview_scheduled)
        assert c.state.selected_slot_id == "s3"
        assert Flag.interview_rescheduled in c.state.flags
        assert c.record().selected_slot_id == "s3"

    @pytest.mark.ac("AC-43")
    def test_none_fits_keeps_the_booked_interview(self, config: EngineConfig) -> None:
        c = booked(config).say(reschedule_interview=True, offered_slots=FRESH)
        c.no_slot_fits().expect(KeepInterview, slot_id="s1")
        c.expect_status(Status.interview_scheduled)
        assert c.state.selected_slot_id == "s1"
        assert Flag.interview_rescheduled not in c.state.flags

    @pytest.mark.ac("AC-43")
    def test_no_other_open_slot_keeps_the_booking_at_once(self, config: EngineConfig) -> None:
        c = booked(config).say(reschedule_interview=True, offered_slots=["s1"])
        c.expect(KeepInterview, slot_id="s1").expect_status(Status.interview_scheduled)
        booked(config).say(reschedule_interview=True).expect(KeepInterview, slot_id="s1")

    @pytest.mark.ac("AC-43")
    def test_silence_or_used_up_reasks_while_moving_keep_the_booking(
        self, config: EngineConfig
    ) -> None:
        c = booked(config).say(reschedule_interview=True, offered_slots=FRESH)
        c.silence().expect(KeepInterview, slot_id="s1").expect_status(Status.interview_scheduled)
        c = booked(config).say(reschedule_interview=True, offered_slots=FRESH)
        c.select_slot("s7").expect(ReaskField).select_slot("s8").expect(ReaskField)
        c.select_slot("s9").expect(KeepInterview, slot_id="s1")

    def test_a_new_offer_gets_its_own_reasks(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.scheduling)
        c.select_slot("s9").expect(ReaskField).select_slot("s1")
        c.say(reschedule_interview=True, offered_slots=FRESH)
        assert c.reasks(FieldName.slot) == 0

    def test_reschedule_with_a_question_answers_it_first(self, config: EngineConfig) -> None:
        c = booked(config).say(reschedule_interview=True, faq_question=True, offered_slots=FRESH)
        c.expect(OfferSlots).expect_prefaces(AnswerFaq)

    @pytest.mark.ac("AC-44")
    def test_reschedule_after_a_cancel_offers_an_interview_again(
        self, config: EngineConfig
    ) -> None:
        c = booked(config).say(cancel_interview=True)
        c.say(reschedule_interview=True, offered_slots=FRESH)
        c.expect(OfferSlots, slot_ids=FRESH, reason=None).expect_status(Status.in_progress)
        c.select_slot("s2").expect(ConfirmInterview).expect_status(Status.interview_scheduled)
        c = booked(config).say(cancel_interview=True).say(reschedule_interview=True)
        c.expect(CloseQualifiedUnscheduled).expect_status(Status.qualified_unscheduled)

    def test_reschedule_without_an_interview_changes_nothing(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.age).say(reschedule_interview=True)
        assert c.action.primary.type == "reask_field"  # a signal-only turn, as before
        c = Convo(config).advance_to_status(Status.waitlisted)
        c.say(reschedule_interview=True, offered_slots=FRESH).expect(ClosedAck)
        c.expect_status(Status.waitlisted)

    def test_a_booked_candidate_is_never_waitlisted_when_moving(self, config: EngineConfig) -> None:
        c = booked(config).say(reschedule_interview=True, offered_slots=FRESH)
        c.say(age(30), correction=True)  # back to the recap (plan OQ-7)
        assert c.action.primary.type == "show_recap"

        c.say(yes(), offered_slots=FRESH, zone_full=True)
        c.expect(OfferSlots, slot_ids=["s2", "s3"], reason="reschedule")


class TestCancel:
    @pytest.mark.ac("AC-44")
    def test_cancel_releases_the_booking(self, config: EngineConfig) -> None:
        c = booked(config).say(cancel_interview=True)
        c.expect(CloseInterviewCancelled).expect_status(Status.qualified_unscheduled)
        assert c.state.selected_slot_id is None
        assert Flag.interview_cancelled in c.state.flags
        record = c.record()
        assert record.selected_slot_id is None
        assert record.score is not None  # still qualified and ranked

    @pytest.mark.ac("AC-44")
    def test_cancel_while_moving_releases_the_booking(self, config: EngineConfig) -> None:
        c = booked(config).say(reschedule_interview=True, offered_slots=FRESH)
        c.say(cancel_interview=True).expect(CloseInterviewCancelled)
        assert c.state.selected_slot_id is None

    def test_cancel_while_choosing_a_first_slot_is_none_fits(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.scheduling).say(cancel_interview=True)
        c.expect(CloseQualifiedUnscheduled).expect_status(Status.qualified_unscheduled)

    @pytest.mark.ac("AC-44")
    @pytest.mark.parametrize(
        "status", [Status.qualified_unscheduled, Status.waitlisted, Status.disqualified]
    )
    def test_cancel_without_a_booking_changes_nothing(
        self, config: EngineConfig, status: Status
    ) -> None:
        c = Convo(config).advance_to_status(status)
        before = c.state.model_copy(deep=True)
        c.say(cancel_interview=True).expect(ClosedAck).expect_status(status)
        assert c.state.flags == before.flags

    def test_opt_out_still_wins(self, config: EngineConfig) -> None:
        c = booked(config).say(cancel_interview=True, opt_out=True)
        c.expect_status(Status.opted_out)
        assert c.state.selected_slot_id is None


class TestSlotTaken:
    @pytest.mark.ac("AC-45")
    def test_slot_taken_offers_the_slots_still_open(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.scheduling)
        c.event(SlotTaken(slot_id="s1", slot_ids=["s1", "s2", "s3"]))
        c.expect(OfferSlots, slot_ids=["s2", "s3"], reason="slot_taken")
        c.expect_status(Status.in_progress)
        assert c.state.selected_slot_id is None
        c.select_slot("s3").expect(ConfirmInterview, slot_id="s3")

    @pytest.mark.ac("AC-45")
    def test_slot_taken_with_nothing_open(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.scheduling)
        c.event(SlotTaken(slot_id="s1", slot_ids=[]))
        c.expect(CloseQualifiedUnscheduled).expect_status(Status.qualified_unscheduled)
        c = booked(config).say(reschedule_interview=True, offered_slots=FRESH)
        c.event(SlotTaken(slot_id="s2", slot_ids=["s1"]))  # only their own slot is left
        c.expect(KeepInterview, slot_id="s1").expect_status(Status.interview_scheduled)

    def test_slot_taken_outside_scheduling_is_ignored(self, config: EngineConfig) -> None:
        booked(config).event(SlotTaken(slot_id="s1", slot_ids=["s2"])).expect(ClosedAck)
        c = Convo(config).advance_to(Stage.age).event(SlotTaken(slot_id="s1", slot_ids=["s2"]))
        assert c.action.primary.type == "ask_field"
