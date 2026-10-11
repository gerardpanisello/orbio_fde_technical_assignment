"""T24: opt-out is honoured in every stage and every status, and purges the data (FR-11)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import ClosedAck, CloseOptedOut
from sazon_screening.engine.enums import Country, Flag, Stage, Status
from sazon_screening.engine.state import Profile
from tests.engine.builders import Convo, age, consent, exp, loc, name
from tests.engine.privacy import leaked_record, leaked_state

PENDING_STAGES = list(Stage)
# (status, stages where it can happen): qualified/booked outcomes only exist in scheduling,
# and silence in scheduling never abandons (it yields qualified_unscheduled).
CASES = (
    [(Status.in_progress, stage) for stage in PENDING_STAGES]
    + [(Status.abandoned, stage) for stage in PENDING_STAGES if stage is not Stage.scheduling]
    + [(Status.disqualified, stage) for stage in PENDING_STAGES]
    + [(Status.needs_review, stage) for stage in PENDING_STAGES]
    + [(Status.qualified_unscheduled, Stage.scheduling)]
    + [(Status.interview_scheduled, Stage.scheduling)]
)


@pytest.mark.ac("AC-26")
@pytest.mark.parametrize(("status", "stage"), CASES, ids=lambda v: str(v))
def test_opt_out_everywhere_purges_the_record(
    config: EngineConfig, status: Status, stage: Stage
) -> None:
    c = Convo(config).advance_to_status(status, at=stage)
    assert c.state.stage == stage
    c.say(name("Otra Persona"), age(17), loc("Coyoacán"), opt_out=True)
    c.expect(CloseOptedOut).expect_status(Status.opted_out)
    assert c.state.profile == Profile()
    assert c.state.flags == [Flag.do_not_contact]
    assert c.state.drop_off_stage == stage
    assert c.state.needs_review_reasons == []
    assert c.state.disqualification_reason is None
    assert c.state.selected_slot_id is None
    assert c.state.post_close_corrections == []
    assert leaked_state(c.state) == {}
    assert leaked_record(c.record(), config) == {}


def test_opted_out_conversation_stays_closed(config: EngineConfig) -> None:
    # Plan OQ-4: a new application is a new conversation.
    c = Convo(config).advance_to_status(Status.opted_out, at=Stage.location)
    c.say(loc("Coyoacán")).expect(ClosedAck).expect_status(Status.opted_out)
    assert c.state.profile == Profile()
    c.say(opt_out=True).expect(ClosedAck)
    c.silence().expect_status(Status.opted_out)


class TestNothingCandidateDerivedSurvives:
    """FR-11: the purge covers the whole state, not only the profile."""

    def test_opt_out_while_disambiguating_a_place(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.location).say(loc("El Carmen"))
        assert c.state.pending.raw_text == "El Carmen"
        c.say(opt_out=True, country_hint=Country.MX).expect(CloseOptedOut)
        assert leaked_state(c.state) == {}
        assert leaked_record(c.record(), config) == {}

    def test_opt_out_while_confirming_a_value(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.experience).say(exp(45, "Glovo"))
        assert c.state.pending.candidate_value is not None
        c.say(opt_out=True).expect(CloseOptedOut)
        assert leaked_state(c.state) == {}
        assert leaked_record(c.record(), config) == {}

    def test_opt_out_after_booking(self, config: EngineConfig) -> None:
        c = Convo(config, country_hint=Country.MX).advance_to_status(Status.interview_scheduled)
        c.say(opt_out=True).expect(CloseOptedOut)
        assert leaked_state(c.state) == {}
        assert leaked_record(c.record(), config) == {}


def test_turn_after_opt_out_stores_nothing_new(config: EngineConfig) -> None:
    # Found by the property test: the phone-prefix country was stored after opting out.
    c = Convo(config).say(consent(False))
    c.say(country_hint=Country.MX).expect(ClosedAck)
    assert leaked_state(c.state) == {}
