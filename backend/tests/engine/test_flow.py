"""Conversation flow through `step()`: consent, out-of-order collection, happy path."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine import turn as turn_module
from sazon_screening.engine.actions import (
    AskField,
    ClosedAck,
    CloseNeedsReview,
    CloseOptedOut,
    ReaskField,
)
from sazon_screening.engine.enums import (
    Availability,
    FieldName,
    FieldStatus,
    Flag,
    Language,
    ReaskReason,
    Register,
    ReviewReason,
    Stage,
    Status,
)
from sazon_screening.engine.inputs import CandidateTurn
from sazon_screening.engine.state import ConversationState, Experience, Profile
from sazon_screening.engine.turn import start, step
from tests.engine.builders import (
    Convo,
    adult,
    avail,
    consent,
    exp,
    license,
    loc,
    name,
    sched,
    vehicle,
)
from tests.engine.conftest import TODAY


class TestStartAndConsent:
    def test_start_asks_for_consent(self, config: EngineConfig) -> None:
        state, action = start(config)
        assert action.primary == AskField(field=FieldName.consent)
        assert (action.language, action.register) == (Language.es, Register.es_ES)
        assert state.status == Status.in_progress
        assert state.config_version == config.version

    @pytest.mark.ac("AC-2")
    def test_declining_consent_opts_out_with_no_data(self, config: EngineConfig) -> None:
        c = Convo(config).say(consent(False), name("Ana López"))
        c.expect(CloseOptedOut).expect_status(Status.opted_out)
        assert c.state.profile == Profile()
        assert c.state.flags == [Flag.do_not_contact]
        assert c.state.drop_off_stage == Stage.consent

    @pytest.mark.ac("AC-3")
    def test_data_without_consent_is_discarded(self, config: EngineConfig) -> None:
        c = Convo(config).say(name("Ana López"))
        c.expect(ReaskField, field=FieldName.consent, reason=ReaskReason.consent_required)
        assert c.state.profile.full_name.status == FieldStatus.not_asked
        assert c.state.consent is None

    @pytest.mark.ac("AC-3")
    def test_data_in_the_same_turn_as_consent_is_kept(self, config: EngineConfig) -> None:
        c = Convo(config).say(consent(True), name("Ana López"))
        c.expect(AskField, field=FieldName.age)
        assert c.state.consent is True
        assert c.state.profile.full_name.value == "Ana López"
        assert c.state.stage == Stage.age

    def test_unclear_consent_keeps_asking_without_closing(self, config: EngineConfig) -> None:
        # Plan OQ-1: no data is stored; silence (008) eventually abandons the conversation.
        c = Convo(config)
        for _ in range(5):
            c.say().expect(ReaskField, field=FieldName.consent).expect_status(Status.in_progress)
        assert c.reasks(FieldName.consent) == config.thresholds.max_reasks + 1

    def test_consent_alone_moves_to_the_name(self, config: EngineConfig) -> None:
        Convo(config).say(consent(True)).expect(AskField, field=FieldName.full_name)


class TestPurity:
    def test_callers_state_is_unchanged(self, config: EngineConfig) -> None:
        state, _ = start(config)
        before = state.model_dump()
        turn = CandidateTurn(proposals=[consent(True), name("Ana López"), adult()])
        new_state, _ = step(state, turn, config, TODAY)
        assert state.model_dump() == before
        assert new_state.profile.full_name.value == "Ana López"

    def test_safety_net_turns_a_bug_into_needs_review(
        self, config: EngineConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(*_: object) -> None:
            raise RuntimeError("bug")

        monkeypatch.setattr(turn_module, "step_unchecked", broken)
        state, _ = start(config)
        new_state, action = step(state, CandidateTurn(), config, TODAY)
        assert action.primary == CloseNeedsReview(reasons=[ReviewReason.engine_error])
        assert new_state.status == Status.needs_review
        assert Flag.engine_error in new_state.flags
        assert state.status == Status.in_progress  # original untouched

    def test_safety_net_keeps_opted_out_closed(
        self, config: EngineConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = ConversationState(status=Status.opted_out)

        def broken(*_: object) -> None:
            raise RuntimeError("bug")

        monkeypatch.setattr(turn_module, "step_unchecked", broken)
        new_state, action = step(state, CandidateTurn(), config, TODAY)
        assert action.primary == ClosedAck()
        assert new_state.status == Status.opted_out


def knockouts_done(c: Convo) -> Convo:
    """Consent, name, age, vehicle and license given, one per turn."""
    return (
        c.say(consent(True))
        .say(name("Ana López"))
        .say(adult())
        .say(vehicle("motorbike"))
        .say(license(True))
    )


class TestOutOfOrder:
    @pytest.mark.ac("AC-4")
    def test_several_fields_in_one_turn_are_all_stored(self, config: EngineConfig) -> None:
        c = Convo(config).say(consent(True)).expect(AskField, field=FieldName.full_name)
        c.say(name("Ana López"), license(True), loc("Coyoacán")).expect(
            AskField, field=FieldName.age
        )
        profile = c.state.profile
        assert profile.full_name.value == "Ana López"
        assert profile.has_license.value is True
        assert profile.location.value is not None
        assert profile.location.value.zone == "cdmx-coyoacan"
        assert profile.location.status == FieldStatus.valid

    @pytest.mark.ac("AC-5")
    def test_early_profile_answer_is_skipped_later(self, config: EngineConfig) -> None:
        c = Convo(config).say(consent(True)).say(name("Ana López"))
        c.say(adult(), avail("weekends")).expect(AskField, field=FieldName.vehicle_type)
        c.say(vehicle("car")).say(license(True)).expect(AskField, field=FieldName.location)
        c.say(loc("Coyoacán")).expect(AskField, field=FieldName.schedule)
        assert c.state.profile.availability.value == [Availability.weekends]

    def test_proposal_order_in_a_turn_does_not_matter(self, config: EngineConfig) -> None:
        in_order = Convo(config).say(consent(True), name("Ana López"), adult(), vehicle("car"))
        reversed_ = Convo(config).say(vehicle("car"), adult(), name("Ana López"), consent(True))
        assert in_order.state == reversed_.state
        assert in_order.action == reversed_.action

    def test_latest_value_in_a_turn_wins(self, config: EngineConfig) -> None:
        c = Convo(config).say(consent(True), name("Ana López"), name("Ana María López"))
        assert c.state.profile.full_name.value == "Ana María López"

    def test_a_later_turn_overwrites_a_stored_value(self, config: EngineConfig) -> None:
        c = knockouts_done(Convo(config)).say(loc("Chamberí"))
        c.say(loc("Salamanca, Madrid")).expect(AskField, field=FieldName.availability)
        assert c.state.profile.location.value is not None
        assert c.state.profile.location.value.zone == "mad-salamanca"

    def test_city_with_zones_asks_for_the_zone(self, config: EngineConfig) -> None:
        c = knockouts_done(Convo(config)).say(loc("Madrid"))
        c.expect(AskField, field=FieldName.zone)
        assert c.state.stage == Stage.location
        assert c.state.profile.location.status == FieldStatus.not_asked
        c.say(loc("Chamberí")).expect(AskField, field=FieldName.availability)
        assert c.state.profile.location.status == FieldStatus.valid

    def test_full_profile_is_collected_in_stage_order(self, config: EngineConfig) -> None:
        c = knockouts_done(Convo(config)).say(loc("Coyoacán"))
        c.expect(AskField, field=FieldName.availability)
        c.say(avail("full_time")).expect(AskField, field=FieldName.schedule)
        c.say(sched("flexible")).expect(AskField, field=FieldName.experience)
        c.say(exp(3, "Glovo")).expect(AskField, field=FieldName.start_date)
        profile = c.state.profile
        assert profile.experience.value == Experience(years=3, platforms=["glovo"])


@pytest.mark.ac("AC-1")
def test_happy_path_follows_the_stage_order(config: EngineConfig) -> None:
    c = Convo(config).advance_to(Stage.scheduling).select_slot("s1")
    assert c.primaries() == [
        "ask_field",  # consent
        "ask_field",  # full_name
        "ask_field",  # age
        "ask_field",  # vehicle_type
        "ask_field",  # has_license
        "ask_field",  # location
        "ask_field",  # availability
        "ask_field",  # schedule
        "ask_field",  # experience
        "ask_field",  # start_date
        "show_recap",
        "offer_slots",
        "confirm_interview",
    ]
    asked = [a.primary.field for a in c.history if isinstance(a.primary, AskField)]
    assert asked == [
        FieldName.consent,
        FieldName.full_name,
        FieldName.age,
        FieldName.vehicle_type,
        FieldName.has_license,
        FieldName.location,
        FieldName.availability,
        FieldName.schedule,
        FieldName.experience,
        FieldName.start_date,
    ]
    c.expect_status(Status.interview_scheduled)
    assert c.state.selected_slot_id == "s1"
    profile = c.state.profile
    for slot_name in Profile.model_fields:
        assert getattr(profile, slot_name).status == FieldStatus.valid, slot_name
