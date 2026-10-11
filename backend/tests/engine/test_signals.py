"""T23/T26: signals (FR-9, FR-10, FR-12, FR-13, FR-27, FR-28) and language/register."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AckCorrection,
    AnswerFaq,
    AskField,
    CloseDisqualified,
    CloseNeedsReview,
    CloseOptedOut,
    HandoffToHuman,
    ReaskField,
    Redirect,
)
from sazon_screening.engine.enums import (
    FieldName,
    Flag,
    ReaskReason,
    ReviewReason,
    Stage,
    Status,
)
from tests.engine.builders import Convo, age, sched


def at_schedule(config: EngineConfig) -> Convo:
    return Convo(config).advance_to(Stage.schedule).expect(AskField, field=FieldName.schedule)


class TestWantsHuman:
    @pytest.mark.ac("AC-27")
    def test_wants_human_hands_off(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(wants_human=True)
        c.expect(HandoffToHuman).expect_status(Status.needs_review)
        assert Flag.human_requested in c.state.flags
        assert c.state.needs_review_reasons == [ReviewReason.human_requested]
        assert c.state.drop_off_stage == Stage.schedule


class TestFaq:
    @pytest.mark.ac("AC-28")
    def test_faq_alone_answers_and_repeats_the_ask(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(faq_question=True)
        c.expect(AskField, field=FieldName.schedule).expect_prefaces(AnswerFaq)

    @pytest.mark.ac("AC-28")
    def test_faq_with_an_answer_moves_on(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(sched("morning"), faq_question=True)
        c.expect(AskField, field=FieldName.experience).expect_prefaces(AnswerFaq)


class TestOffTopicAndAbuse:
    def test_off_topic_redirects_without_using_a_reask(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(off_topic=True)
        c.expect(AskField, field=FieldName.schedule).expect_prefaces(Redirect)
        assert c.action.prefaces == [Redirect(reason="off_topic")]
        assert c.reasks(FieldName.schedule) == 0

    @pytest.mark.ac("AC-31")
    def test_first_abuse_redirects_then_closes_for_review(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(abuse=True)
        c.expect(AskField, field=FieldName.schedule)
        assert c.action.prefaces == [Redirect(reason="abuse")]
        c.say(abuse=True).expect(CloseNeedsReview, reasons=[ReviewReason.abuse])
        c.expect_status(Status.needs_review)
        assert Flag.abuse in c.state.flags

    def test_prefaces_come_in_a_fixed_order(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(faq_question=True, off_topic=True, abuse=True)
        c.expect_prefaces(Redirect, Redirect, AnswerFaq)


class TestExtractionFailures:
    @pytest.mark.ac("AC-31")
    def test_repeated_failures_go_to_review(self, config: EngineConfig) -> None:
        c = at_schedule(config)
        for _ in range(config.thresholds.max_consecutive_extraction_failures - 1):
            c.say(extraction_failed=True).expect(
                ReaskField, field=FieldName.schedule, reason=ReaskReason.extraction_failed
            )
        c.say(extraction_failed=True)
        c.expect(CloseNeedsReview, reasons=[ReviewReason.system_failure])
        c.expect_status(Status.needs_review)
        assert Flag.system_failure in c.state.flags
        assert c.reasks(FieldName.schedule) == 0

    def test_a_readable_turn_resets_the_failure_count(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(extraction_failed=True).say(extraction_failed=True)
        c.say(faq_question=True).say(extraction_failed=True).expect(ReaskField)
        c.expect_status(Status.in_progress)


class TestPrecedence:
    """FR-10: opt_out > abuse > proposals + hard rules > wants_human > faq > next ask."""

    def test_opt_out_beats_abuse_and_disqualification(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(age(17), opt_out=True, abuse=True)
        c.expect(CloseOptedOut).expect_status(Status.opted_out)

    def test_abuse_close_beats_disqualification(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(abuse=True).say(age(17), abuse=True)
        c.expect(CloseNeedsReview, reasons=[ReviewReason.abuse])

    def test_disqualification_beats_wants_human(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(age(17), wants_human=True)
        c.expect(CloseDisqualified, reason="under_age")

    def test_wants_human_beats_faq(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(wants_human=True, faq_question=True)
        c.expect(HandoffToHuman)

    def test_correction_is_acknowledged(self, config: EngineConfig) -> None:
        c = at_schedule(config).say(age(30), correction=True)
        c.expect(AskField, field=FieldName.schedule).expect_prefaces(AckCorrection)
        assert c.action.prefaces == [AckCorrection(fields=[FieldName.age])]

    def test_correction_without_a_change_is_not_acknowledged(self, config: EngineConfig) -> None:
        at_schedule(config).say(correction=True).expect_prefaces()
