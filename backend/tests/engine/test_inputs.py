"""T7: the turn-input contract parses the plain JSON that 003/008/010 will send (ADR 0005)."""

from datetime import date
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from sazon_screening.engine.inputs import (
    UNCLEAR,
    AbsoluteDate,
    AgeAnswer,
    AgeProposal,
    Asap,
    CandidateTurn,
    ChoiceProposal,
    ConfirmationProposal,
    ConsentProposal,
    ExperienceAnswer,
    LocationAnswer,
    NameProposal,
    NextWeekday,
    NoSlotFits,
    Offset,
    Proposal,
    Signals,
    SilenceExpired,
    SlotSelected,
    StartDateProposal,
    TurnContext,
    TurnInput,
    Unclear,
)
from sazon_screening.vocab import Availability, Country, Language, VehicleType, Weekday

proposals: TypeAdapter[Proposal] = TypeAdapter(Proposal)
turn_inputs: TypeAdapter[TurnInput] = TypeAdapter(TurnInput)


@pytest.mark.parametrize(
    ("raw", "expected_value"),
    [
        ({"field": "consent", "value": True}, True),
        ({"field": "full_name", "value": "Ana López"}, "Ana López"),
        ({"field": "age", "value": {"age": 25}}, AgeAnswer(age=25)),
        ({"field": "age", "value": {"is_adult": True}}, AgeAnswer(is_adult=True)),
        ({"field": "vehicle_type", "value": "e_bike"}, VehicleType.e_bike),
        ({"field": "has_license", "value": False}, False),
        (
            {"field": "location", "value": {"text": "Coyoacán", "is_known_place": True}},
            LocationAnswer(text="Coyoacán", is_known_place=True),
        ),
        (
            {"field": "availability", "value": ["weekends", "full_time"]},
            [Availability.weekends, Availability.full_time],
        ),
        ({"field": "schedule", "value": ["flexible"]}, ["flexible"]),
        (
            {"field": "experience", "value": {"years": 3, "platforms": ["Glovo"]}},
            ExperienceAnswer(years=3, platforms=["Glovo"]),
        ),
        (
            {"field": "experience", "value": {"years": "none"}},
            ExperienceAnswer(years="none"),
        ),
        ({"field": "confirmation", "value": True}, True),
        ({"field": "choice", "value": "monterrey"}, "monterrey"),
    ],
)
def test_each_proposal_parses_from_a_plain_dict(raw: dict[str, Any], expected_value: Any) -> None:
    proposal = proposals.validate_python(raw)
    assert proposal.field == raw["field"]
    assert proposal.value == expected_value


@pytest.mark.parametrize(
    "field",
    [
        "consent",
        "full_name",
        "age",
        "vehicle_type",
        "has_license",
        "location",
        "availability",
        "schedule",
        "experience",
        "start_date",
        "confirmation",
        "choice",
    ],
)
def test_every_proposal_accepts_the_unclear_marker(field: str) -> None:
    proposal = proposals.validate_python({"field": field, "value": {"kind": "unclear"}})
    assert isinstance(proposal.value, Unclear)
    assert proposal.value == UNCLEAR


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"kind": "asap"}, Asap()),
        ({"kind": "absolute", "on": "2026-11-02"}, AbsoluteDate(on=date(2026, 11, 2))),
        ({"kind": "offset", "amount": 2, "unit": "weeks"}, Offset(amount=2, unit="weeks")),
        ({"kind": "next_weekday", "weekday": "mon"}, NextWeekday(weekday=Weekday.mon)),
    ],
)
def test_each_start_date_kind_parses(raw: dict[str, Any], expected: object) -> None:
    proposal = proposals.validate_python({"field": "start_date", "value": raw})
    assert isinstance(proposal, StartDateProposal)
    assert proposal.value == expected


def test_turn_input_json_round_trip() -> None:
    turn = CandidateTurn(
        proposals=[
            ConsentProposal(value=True),
            NameProposal(value="Ana López"),
            AgeProposal(value=UNCLEAR),
            StartDateProposal(value=Offset(amount=3, unit="days")),
            ConfirmationProposal(value=False),
            ChoiceProposal(value="cdmx-coyoacan"),
        ],
        signals=Signals(faq_question=True, language=Language.en),
        context=TurnContext(country_hint=Country.MX, offered_slots=["s1", "s2"]),
    )
    dumped = turn_inputs.dump_json(turn)
    assert turn_inputs.validate_json(dumped) == turn
    assert turn.signals.language == Language.en


@pytest.mark.parametrize(
    "event",
    [SilenceExpired(), SlotSelected(slot_id="s1"), NoSlotFits()],
)
def test_events_round_trip(event: TurnInput) -> None:
    assert turn_inputs.validate_json(turn_inputs.dump_json(event)) == event


def test_candidate_turn_defaults_are_empty() -> None:
    turn = turn_inputs.validate_python({"kind": "turn"})
    assert isinstance(turn, CandidateTurn)
    assert turn.proposals == []
    assert not turn.signals.opt_out
    assert turn.context.country_hint is None


@pytest.mark.parametrize(
    "raw",
    [
        {"field": "salary", "value": 1000},
        {"field": "full_name", "value": "Ana López", "confidence": 0.9},
        {"field": "age", "value": {}},
        {"field": "age", "value": {"age": 20, "approved": True}},
        {"field": "vehicle_type", "value": "scooter"},
        {"field": "start_date", "value": {"kind": "tomorrow"}},
        {"field": "start_date", "value": {"kind": "offset", "amount": 2, "unit": "months"}},
    ],
)
def test_unknown_fields_and_extra_keys_are_rejected(raw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        proposals.validate_python(raw)


def test_unknown_signal_is_rejected() -> None:
    # A prompt-injected "approve" flag must never reach the engine.
    with pytest.raises(ValidationError):
        turn_inputs.validate_python({"kind": "turn", "signals": {"approve": True}})


def test_json_schemas_build_for_structured_output() -> None:
    schema = TypeAdapter(TurnInput).json_schema()
    assert "discriminator" in str(schema)
    assert proposals.json_schema()
