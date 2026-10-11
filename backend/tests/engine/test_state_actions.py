"""T8: conversation state and engine actions are typed, serialisable boundary models."""

from datetime import date
from typing import Any, get_args

import pytest
from pydantic import TypeAdapter

from sazon_screening.config.areas import AreaRef
from sazon_screening.engine.actions import (
    AckCorrection,
    AnswerFaq,
    AskCorrectionField,
    AskField,
    ClosedAck,
    CloseDisqualified,
    CloseNeedsReview,
    CloseOptedOut,
    CloseQualifiedUnscheduled,
    ConfirmAmbiguous,
    ConfirmInterview,
    ConfirmValue,
    EngineAction,
    HandoffToHuman,
    NoMessage,
    OfferSlots,
    Preface,
    PrimaryAction,
    ReaskField,
    Redirect,
    ShowRecap,
    register_for,
)
from sazon_screening.engine.inputs import AgeAnswer
from sazon_screening.engine.state import (
    ConversationState,
    Experience,
    LocationValue,
    Slot,
    add_flag,
    add_reason,
)
from sazon_screening.vocab import (
    Country,
    DisqualificationReason,
    FieldName,
    FieldStatus,
    Flag,
    Language,
    PendingKind,
    ReaskReason,
    Register,
    ReviewReason,
    Stage,
    Status,
)

COYOACAN = AreaRef(id="cdmx-coyoacan", country=Country.MX, city="cdmx", zone="cdmx-coyoacan")


def filled_state() -> ConversationState:
    state = ConversationState()
    state.consent = True
    state.profile.full_name = Slot(status=FieldStatus.valid, value="Ana López")
    state.profile.age = Slot(status=FieldStatus.valid, value=AgeAnswer(age=25))
    state.profile.location = Slot(
        status=FieldStatus.valid,
        value=LocationValue(
            raw_text="Coyoacán",
            country=Country.MX,
            city="cdmx",
            zone="cdmx-coyoacan",
            in_service_area=True,
        ),
    )
    state.profile.experience = Slot(
        status=FieldStatus.valid, value=Experience(years=3, platforms=["glovo", "other:X"])
    )
    state.profile.start_date = Slot(status=FieldStatus.valid, value=date(2026, 10, 12))
    state.reasks = {FieldName.age: 1}
    return state


class TestState:
    def test_fresh_state_waits_for_consent(self) -> None:
        state = ConversationState()
        assert state.status == Status.in_progress
        assert state.stage == Stage.consent
        assert state.pending.kind == PendingKind.ask
        assert state.pending.field == FieldName.consent
        assert state.profile.full_name.status == FieldStatus.not_asked

    @pytest.mark.parametrize("state", [ConversationState(), filled_state()])
    def test_json_round_trip(self, state: ConversationState) -> None:
        restored = ConversationState.model_validate_json(state.model_dump_json())
        assert restored == state

    def test_profiles_are_not_shared_between_states(self) -> None:
        first, second = ConversationState(), ConversationState()
        first.profile.full_name = Slot(status=FieldStatus.valid, value="Ana López")
        assert second.profile.full_name.value is None

    def test_add_flag_keeps_flags_sorted_and_unique(self) -> None:
        state = ConversationState()
        for flag in (Flag.surname_missing, Flag.abuse, Flag.surname_missing):
            add_flag(state, flag)
        assert state.flags == [Flag.abuse, Flag.surname_missing]

    def test_add_reason_keeps_first_occurrence_order(self) -> None:
        state = ConversationState()
        for reason in (ReviewReason.location_unclear, ReviewReason.age_unclear) * 2:
            add_reason(state, reason)
        assert state.needs_review_reasons == [
            ReviewReason.location_unclear,
            ReviewReason.age_unclear,
        ]


ALL_PRIMARY: list[Any] = [
    AskField(field=FieldName.age),
    ReaskField(field=FieldName.location, reason=ReaskReason.not_recognised, options=["madrid"]),
    ConfirmAmbiguous(field=FieldName.location, options=[COYOACAN]),
    ConfirmValue(field=FieldName.experience, value=Experience(years=45, platforms=[])),
    AskCorrectionField(),
    ShowRecap(profile=filled_state().profile),
    OfferSlots(slot_ids=["s1", "s2"]),
    ConfirmInterview(slot_id="s1"),
    CloseDisqualified(reason=DisqualificationReason.under_age),
    CloseNeedsReview(reasons=[ReviewReason.location_unclear]),
    CloseOptedOut(),
    CloseQualifiedUnscheduled(),
    HandoffToHuman(),
    ClosedAck(),
    NoMessage(),
]
ALL_PREFACES: list[Any] = [
    AnswerFaq(),
    AckCorrection(fields=[FieldName.location]),
    Redirect(reason="off_topic"),
]


class TestActions:
    def test_primary_action_types_match_the_contract(self) -> None:
        # FR-4 list + no_message (ADR 0005, OQ-2 decision).
        assert {action.type for action in ALL_PRIMARY} == {
            "ask_field",
            "reask_field",
            "confirm_ambiguous",
            "confirm_value",
            "ask_correction_field",
            "show_recap",
            "offer_slots",
            "confirm_interview",
            "close_disqualified",
            "close_needs_review",
            "close_opted_out",
            "close_qualified_unscheduled",
            "handoff_to_human",
            "closed_ack",
            "no_message",
        }
        union_members = get_args(get_args(PrimaryAction)[0])
        assert len(union_members) == len(ALL_PRIMARY)

    @pytest.mark.parametrize("action", ALL_PRIMARY, ids=lambda a: str(a.type))
    def test_primary_action_round_trips_with_type_tag(self, action: Any) -> None:
        adapter: TypeAdapter[PrimaryAction] = TypeAdapter(PrimaryAction)
        dumped = adapter.dump_python(action, mode="json")
        assert dumped["type"] == action.type
        assert adapter.validate_python(dumped) == action

    @pytest.mark.parametrize("preface", ALL_PREFACES, ids=lambda p: str(p.type))
    def test_preface_round_trips_with_type_tag(self, preface: Any) -> None:
        adapter: TypeAdapter[Preface] = TypeAdapter(Preface)
        dumped = adapter.dump_python(preface, mode="json")
        assert dumped["type"] == preface.type
        assert adapter.validate_python(dumped) == preface

    def test_engine_action_round_trip(self) -> None:
        action = EngineAction(
            primary=AskField(field=FieldName.schedule),
            prefaces=[AnswerFaq()],
            language=Language.es,
            register=Register.es_MX,
        )
        dumped = action.model_dump_json()
        assert '"register":"es-MX"' in dumped
        assert EngineAction.model_validate_json(dumped) == action


@pytest.mark.ac("AC-32")
@pytest.mark.parametrize(
    ("language", "country", "hint", "expected"),
    [
        (Language.en, Country.MX, Country.MX, Register.en),
        (Language.es, Country.MX, None, Register.es_MX),
        (Language.es, Country.ES, Country.MX, Register.es_ES),  # stored location wins
        (Language.es, None, Country.MX, Register.es_MX),
        (Language.es, None, None, Register.es_ES),  # default_country = ES
    ],
)
def test_register_for(
    language: Language, country: Country | None, hint: Country | None, expected: Register
) -> None:
    assert register_for(language, country, hint, default_country=Country.ES) == expected
