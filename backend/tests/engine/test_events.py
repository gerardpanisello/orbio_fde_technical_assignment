"""T22/T24: out-of-band events: slot selection (FR-26) and silence (FR-14)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AskField,
    CloseQualifiedUnscheduled,
    ConfirmInterview,
    NoMessage,
    OfferSlots,
    ReaskField,
)
from sazon_screening.engine.enums import FieldName, ReaskReason, Stage, Status
from tests.engine.builders import OFFERED_SLOTS, Convo, age, license, sched, vehicle


def at_scheduling(config: EngineConfig) -> Convo:
    return Convo(config).advance_to(Stage.scheduling).expect(OfferSlots, slot_ids=OFFERED_SLOTS)


class TestSlots:
    def test_offered_slot_books_the_interview(self, config: EngineConfig) -> None:
        c = at_scheduling(config).select_slot("s2")
        c.expect(ConfirmInterview, slot_id="s2").expect_status(Status.interview_scheduled)
        assert c.state.selected_slot_id == "s2"
        assert c.state.drop_off_stage == Stage.scheduling

    @pytest.mark.ac("AC-30")
    def test_slot_not_offered_is_reasked(self, config: EngineConfig) -> None:
        c = at_scheduling(config).select_slot("s9")
        c.expect(
            ReaskField,
            field=FieldName.slot,
            reason=ReaskReason.slot_not_offered,
            options=OFFERED_SLOTS,
        )
        c.expect_status(Status.in_progress)
        c.select_slot("s1").expect(ConfirmInterview, slot_id="s1")

    @pytest.mark.ac("AC-30")
    def test_no_slot_fits_is_qualified_unscheduled(self, config: EngineConfig) -> None:
        c = at_scheduling(config).no_slot_fits()
        c.expect(CloseQualifiedUnscheduled).expect_status(Status.qualified_unscheduled)
        assert c.state.selected_slot_id is None
        assert c.state.drop_off_stage == Stage.scheduling

    def test_slot_reasks_exhausted_is_qualified_unscheduled(self, config: EngineConfig) -> None:
        c = at_scheduling(config)
        c.select_slot("s7").expect(ReaskField).select_slot("s8").expect(ReaskField)
        c.select_slot("s9").expect(CloseQualifiedUnscheduled)
        c.expect_status(Status.qualified_unscheduled)

    def test_slot_event_outside_scheduling_is_ignored(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.age).select_slot("s1")
        c.expect(AskField, field=FieldName.age).expect_status(Status.in_progress)
        assert c.state.selected_slot_id is None

    def test_faq_during_scheduling_repeats_the_offer(self, config: EngineConfig) -> None:
        c = at_scheduling(config).say(faq_question=True)
        c.expect(OfferSlots, slot_ids=OFFERED_SLOTS)

    def test_empty_turn_during_scheduling_uses_a_reask(self, config: EngineConfig) -> None:
        c = at_scheduling(config).say()
        c.expect(ReaskField, field=FieldName.slot, options=OFFERED_SLOTS)

    def test_correction_during_scheduling_shows_the_recap_again(self, config: EngineConfig) -> None:
        # Plan OQ-7: re-confirm the profile, then offer the slots again.
        c = at_scheduling(config).say(sched("morning"), correction=True)
        c.expect_status(Status.in_progress)
        assert c.action.primary.type == "show_recap"
        assert c.state.stage == Stage.recap


class TestSilence:
    @pytest.mark.ac("AC-29")
    def test_silence_abandons_and_a_later_turn_resumes(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.vehicle_license)
        c.expect(AskField, field=FieldName.vehicle_type)
        c.silence().expect(NoMessage).expect_status(Status.abandoned)
        assert c.state.drop_off_stage == Stage.vehicle_license
        assert c.state.pending.field == FieldName.vehicle_type
        c.say().expect(AskField, field=FieldName.vehicle_type).expect_status(Status.in_progress)
        assert c.state.drop_off_stage is None  # resumed: it has not dropped off any more
        assert c.reasks(FieldName.vehicle_type) == 0  # the resume turn is neutral

    @pytest.mark.ac("AC-29")
    def test_silence_in_scheduling_is_qualified_unscheduled(self, config: EngineConfig) -> None:
        c = at_scheduling(config).silence()
        c.expect(CloseQualifiedUnscheduled).expect_status(Status.qualified_unscheduled)

    def test_resume_turn_with_an_answer_moves_on(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.vehicle_license).silence()
        c.say(vehicle("car")).expect(AskField, field=FieldName.has_license)

    def test_silence_when_not_in_progress_changes_nothing(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.age).silence()
        before = c.state.model_dump()
        c.silence().expect(NoMessage)
        assert c.state.model_dump() == before
        c.say(age(17)).silence().expect(NoMessage).expect_status(Status.disqualified)


def test_second_silence_after_resume_records_the_new_stage(config: EngineConfig) -> None:
    c = Convo(config).advance_to(Stage.vehicle_license).silence()
    c.say(vehicle("car")).say(license(True)).silence()
    assert c.state.drop_off_stage == Stage.location
    c.expect_status(Status.abandoned)


def test_silence_in_scheduling_records_the_stage(config: EngineConfig) -> None:
    c = at_scheduling(config).silence().expect_status(Status.qualified_unscheduled)
    assert c.state.drop_off_stage == Stage.scheduling
