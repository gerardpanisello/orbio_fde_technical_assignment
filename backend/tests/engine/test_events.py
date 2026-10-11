"""T22/T24: out-of-band events: slot selection (FR-26) and silence (FR-14)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AskField,
    CloseQualifiedUnscheduled,
    ConfirmInterview,
    OfferSlots,
    ReaskField,
)
from sazon_screening.engine.enums import FieldName, ReaskReason, Stage, Status
from tests.engine.builders import OFFERED_SLOTS, Convo, sched


def at_scheduling(config: EngineConfig) -> Convo:
    return Convo(config).advance_to(Stage.scheduling).expect(OfferSlots, slot_ids=OFFERED_SLOTS)


class TestSlots:
    def test_offered_slot_books_the_interview(self, config: EngineConfig) -> None:
        c = at_scheduling(config).select_slot("s2")
        c.expect(ConfirmInterview, slot_id="s2").expect_status(Status.interview_scheduled)
        assert c.state.selected_slot_id == "s2"
        assert c.state.drop_off_stage is None

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
