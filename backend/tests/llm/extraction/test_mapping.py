"""T11/T12: model output -> engine input, one proposal at a time (FR-6..9)."""

from datetime import date

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine import (
    UNCLEAR,
    AbsoluteDate,
    AgeAnswer,
    AgeProposal,
    Asap,
    AvailabilityProposal,
    CandidateTurn,
    ChoiceProposal,
    ConfirmationProposal,
    ConsentProposal,
    CorrectionFieldProposal,
    DayMonth,
    ExperienceAnswer,
    ExperienceProposal,
    LicenseProposal,
    LocationAnswer,
    LocationProposal,
    NameProposal,
    NextWeekday,
    NoSlotFits,
    Offset,
    ScheduleProposal,
    Signals,
    SlotSelected,
    StartDateExpr,
    StartDateProposal,
    TurnContext,
    VehicleProposal,
)
from sazon_screening.llm.extraction.mapping import DroppedProposal, Mapped, to_turn_input
from sazon_screening.vocab import (
    Availability,
    Country,
    FieldName,
    FieldStatus,
    Language,
    PendingKind,
    ScheduleSlot,
    Stage,
    VehicleType,
    Weekday,
)
from tests.engine.builders import Convo, consent, name
from tests.llm.builders import asking, out, pending

AT_AGE = asking(FieldName.age)
AT_START = asking(FieldName.start_date)
AT_SLOT = pending(PendingKind.slot, FieldName.slot, ("s1", "s2"))


def turn_of(mapped: Mapped) -> CandidateTurn:
    assert isinstance(mapped.turn_input, CandidateTurn)
    return mapped.turn_input


class TestLocation:
    @pytest.mark.ac("003:AC-1")
    def test_zone_and_city_compose_and_the_engine_resolves_them(
        self, engine_config: EngineConfig
    ) -> None:
        extracted = out(
            location_zone="Coyoacán",
            location_city="Ciudad de México",
            location_is_real_place=True,
        )
        turn = turn_of(to_turn_input(extracted, AT_AGE, TurnContext()))
        assert turn.proposals == [
            LocationProposal(
                value=LocationAnswer(text="Coyoacán, Ciudad de México", is_known_place=True)
            )
        ]
        c = Convo(engine_config).say(consent(True), name("Ana López")).event(turn)
        location = c.state.profile.location
        assert location.status is FieldStatus.valid
        assert location.value is not None
        assert (location.value.city, location.value.zone) == ("cdmx", "cdmx-coyoacan")

    def test_centro_de_madrid_split_by_the_model_reaches_the_engine_as_two_parts(self) -> None:
        extracted = out(location_zone="Centro", location_city="Madrid", location_is_real_place=True)
        [proposal] = turn_of(to_turn_input(extracted, AT_AGE, TurnContext())).proposals
        assert isinstance(proposal, LocationProposal)
        assert isinstance(proposal.value, LocationAnswer)
        assert proposal.value.text == "Centro, Madrid"

    def test_city_only(self) -> None:
        extracted = out(location_city="Zaragoza", location_is_real_place=True)
        [proposal] = turn_of(to_turn_input(extracted, AT_AGE, TurnContext())).proposals
        assert proposal == LocationProposal(
            value=LocationAnswer(text="Zaragoza", is_known_place=True)
        )

    def test_unknown_reality_is_not_a_known_place(self) -> None:
        # Ambiguity never disqualifies: the engine re-asks instead of closing out_of_area.
        extracted = out(location_city="Xjkq", location_is_real_place=None)
        [proposal] = turn_of(to_turn_input(extracted, AT_AGE, TurnContext())).proposals
        assert isinstance(proposal.value, LocationAnswer)
        assert proposal.value.is_known_place is False

    def test_blank_parts_are_no_location(self) -> None:
        extracted = out(location_city="  ", location_is_real_place=True)
        assert turn_of(to_turn_input(extracted, AT_AGE, TurnContext())).proposals == []


class TestNothingUnderstood:
    @pytest.mark.ac("003:AC-3")
    def test_all_null_output_is_an_empty_turn_not_a_failure(self) -> None:
        mapped = to_turn_input(out(), AT_AGE, TurnContext())
        turn = turn_of(mapped)
        assert turn.proposals == []
        assert turn.signals.extraction_failed is False
        assert mapped.dropped == []

    def test_context_comes_from_the_caller(self) -> None:
        context = TurnContext(country_hint=Country.MX, offered_slots=["s1"])
        assert turn_of(to_turn_input(out(), AT_AGE, context)).context == context


class TestUnclear:
    def test_unclear_field_becomes_unclear(self) -> None:
        turn = turn_of(to_turn_input(out(unclear_fields=["age"]), AT_AGE, TurnContext()))
        assert turn.proposals == [AgeProposal(value=UNCLEAR)]

    def test_a_value_beats_unclear_for_the_same_field(self) -> None:
        extracted = out(unclear_fields=["age"], age=30)
        turn = turn_of(to_turn_input(extracted, AT_AGE, TurnContext()))
        assert turn.proposals == [AgeProposal(value=AgeAnswer(age=30))]

    def test_every_field_key_can_be_unclear(self) -> None:
        keys = [
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
        ]
        turn = turn_of(to_turn_input(out(unclear_fields=keys), AT_AGE, TurnContext()))
        assert [p.field for p in turn.proposals] == keys
        assert all(p.value == UNCLEAR for p in turn.proposals)


class TestKnockOutFields:
    def test_consent_yes_and_no(self) -> None:
        at_consent = asking(FieldName.consent)
        yes = turn_of(to_turn_input(out(consent="yes"), at_consent, TurnContext()))
        no = turn_of(to_turn_input(out(consent="no"), at_consent, TurnContext()))
        assert yes.proposals == [ConsentProposal(value=True)]
        assert no.proposals == [ConsentProposal(value=False)]

    def test_name_is_kept_as_written(self) -> None:
        turn = turn_of(to_turn_input(out(full_name=" Ana López "), AT_AGE, TurnContext()))
        assert turn.proposals == [NameProposal(value="Ana López")]

    @pytest.mark.parametrize(
        ("fields", "answer"),
        [
            ({"age": 25}, AgeAnswer(age=25)),
            ({"birth_year": 2000}, AgeAnswer(birth_year=2000)),
            ({"is_adult": True}, AgeAnswer(is_adult=True)),
            ({"age": 25, "birth_year": 2000}, AgeAnswer(age=25, birth_year=2000)),
        ],
    )
    def test_age_in_any_form(self, fields: dict[str, object], answer: AgeAnswer) -> None:
        turn = turn_of(to_turn_input(out(**fields), AT_AGE, TurnContext()))
        assert turn.proposals == [AgeProposal(value=answer)]

    def test_vehicle_and_license(self) -> None:
        extracted = out(vehicle_type="car", has_license=False)
        turn = turn_of(to_turn_input(extracted, AT_AGE, TurnContext()))
        assert turn.proposals == [
            VehicleProposal(value=VehicleType.car),
            LicenseProposal(value=False),
        ]

    def test_several_fields_in_one_message(self) -> None:
        extracted = out(full_name="Ana López", age=25, location_city="Madrid")
        turn = turn_of(to_turn_input(extracted, AT_AGE, TurnContext()))
        assert [p.field for p in turn.proposals] == ["full_name", "age", "location"]


class TestDroppedProposals:
    def test_blank_name_answering_the_pending_field_becomes_unclear(self) -> None:
        mapped = to_turn_input(out(full_name="   "), asking(FieldName.full_name), TurnContext())
        assert turn_of(mapped).proposals == [NameProposal(value=UNCLEAR)]
        assert mapped.dropped == [DroppedProposal(field="full_name", reason="empty_value")]

    def test_blank_name_for_another_field_is_just_dropped(self) -> None:
        mapped = to_turn_input(out(full_name="   ", age=30), AT_AGE, TurnContext())
        assert turn_of(mapped).proposals == [AgeProposal(value=AgeAnswer(age=30))]
        assert [d.field for d in mapped.dropped] == ["full_name"]


# --- T12: profile fields, dates, confirmations, choices, slots, signals ------------------


class TestStartDate:
    @pytest.mark.ac("003:AC-2")
    @pytest.mark.parametrize(
        ("fields", "expr"),
        [
            (
                {"start_kind": "next_weekday", "start_weekday": "mon"},
                NextWeekday(weekday=Weekday.mon),
            ),
            (
                {"start_kind": "offset", "start_offset_amount": 2, "start_offset_unit": "weeks"},
                Offset(amount=2, unit="weeks"),
            ),
            ({"start_kind": "asap"}, Asap()),
            (
                {"start_kind": "day_month", "start_day": 3, "start_month": 11},
                DayMonth(day=3, month=11),
            ),
            (
                {"start_kind": "absolute", "start_date_iso": "2026-11-02"},
                AbsoluteDate(on=date(2026, 11, 2)),
            ),
        ],
    )
    def test_expression_keeps_its_kind(
        self, fields: dict[str, object], expr: StartDateExpr
    ) -> None:
        turn = turn_of(to_turn_input(out(**fields), AT_START, TurnContext()))
        assert turn.proposals == [StartDateProposal(value=expr)]

    @pytest.mark.ac("003:AC-2")
    def test_the_engine_does_the_calendar_maths(self, engine_config: EngineConfig) -> None:
        extracted = out(start_kind="next_weekday", start_weekday="mon")
        turn = turn_of(to_turn_input(extracted, AT_START, TurnContext()))
        c = Convo(engine_config).advance_to(Stage.start_date).event(turn)
        assert c.state.profile.start_date.value == date(2026, 10, 19)  # today is a Monday

    @pytest.mark.parametrize(
        "fields",
        [
            {"start_kind": "absolute"},
            {"start_kind": "absolute", "start_date_iso": "03-11"},
            {"start_kind": "absolute", "start_date_iso": "2026-02-31"},
            {"start_kind": "day_month", "start_day": 3},
            {"start_kind": "offset", "start_offset_amount": 2},
            {"start_kind": "next_weekday"},
        ],
    )
    def test_incomplete_expression_is_dropped_and_unclear_when_pending(
        self, fields: dict[str, object]
    ) -> None:
        mapped = to_turn_input(out(**fields), AT_START, TurnContext())
        assert turn_of(mapped).proposals == [StartDateProposal(value=UNCLEAR)]
        assert [d.field for d in mapped.dropped] == ["start_date"]

    def test_incomplete_expression_for_another_field_is_only_dropped(self) -> None:
        mapped = to_turn_input(out(start_kind="absolute"), AT_AGE, TurnContext())
        assert turn_of(mapped).proposals == []
        assert mapped.dropped == [DroppedProposal(field="start_date", reason="invalid_date")]


class TestProfileFields:
    def test_availability_and_schedule_lists(self) -> None:
        extracted = out(availability=["part_time", "weekends"], schedule=["evening"])
        turn = turn_of(to_turn_input(extracted, AT_AGE, TurnContext()))
        assert turn.proposals == [
            AvailabilityProposal(value=[Availability.part_time, Availability.weekends]),
            ScheduleProposal(value=[ScheduleSlot.evening]),
        ]

    def test_empty_lists_mean_not_mentioned(self) -> None:
        turn = turn_of(to_turn_input(out(availability=[], schedule=[]), AT_AGE, TurnContext()))
        assert turn.proposals == []

    def test_no_experience(self) -> None:
        turn = turn_of(to_turn_input(out(no_experience=True), AT_AGE, TurnContext()))
        assert turn.proposals == [ExperienceProposal(value=ExperienceAnswer(years="none"))]

    def test_years_and_platforms_as_written(self) -> None:
        extracted = out(experience_years=3, platforms=["Glovo", "Uber Eats"])
        turn = turn_of(to_turn_input(extracted, AT_AGE, TurnContext()))
        answer = ExperienceAnswer(years=3, platforms=["Glovo", "Uber Eats"])
        assert turn.proposals == [ExperienceProposal(value=answer)]

    def test_platforms_without_years_leave_years_unknown(self) -> None:
        # The engine re-asks with `missing_years`; we never guess a number.
        turn = turn_of(to_turn_input(out(platforms=["Rappi"]), AT_AGE, TurnContext()))
        assert turn.proposals == [
            ExperienceProposal(value=ExperienceAnswer(years=None, platforms=["Rappi"]))
        ]


class TestConfirmationsAndChoices:
    @pytest.mark.ac("003:AC-5")
    def test_choice_of_an_offered_option(self) -> None:
        ambiguous = pending(PendingKind.confirm_ambiguous, FieldName.location, ("a", "b"))
        turn = turn_of(to_turn_input(out(chosen_option_id="b"), ambiguous, TurnContext()))
        assert turn.proposals == [ChoiceProposal(value="b")]

    @pytest.mark.ac("003:AC-5")
    def test_yes_at_the_recap_is_a_confirmation(self) -> None:
        recap = pending(PendingKind.recap)
        turn = turn_of(to_turn_input(out(confirmation="yes"), recap, TurnContext()))
        assert turn.proposals == [ConfirmationProposal(value=True)]

    @pytest.mark.parametrize(
        "kind", [PendingKind.confirm_value, PendingKind.recap, PendingKind.correction_field]
    )
    def test_no_is_a_confirmation_where_one_is_expected(self, kind: PendingKind) -> None:
        turn = turn_of(to_turn_input(out(confirmation="no"), pending(kind), TurnContext()))
        assert turn.proposals == [ConfirmationProposal(value=False)]

    def test_confirmation_when_none_was_asked_is_dropped(self) -> None:
        mapped = to_turn_input(out(confirmation="yes"), asking(FieldName.consent), TurnContext())
        assert turn_of(mapped).proposals == []
        assert mapped.dropped == [
            DroppedProposal(field="confirmation", reason="no_confirmation_pending")
        ]

    @pytest.mark.ac("003:AC-4")
    def test_choice_not_offered_is_dropped_and_unclear(self) -> None:
        ambiguous = pending(PendingKind.confirm_ambiguous, FieldName.location, ("a", "b"))
        mapped = to_turn_input(out(chosen_option_id="z"), ambiguous, TurnContext())
        assert turn_of(mapped).proposals == [ChoiceProposal(value=UNCLEAR)]
        assert mapped.dropped == [DroppedProposal(field="choice", reason="choice_not_offered")]

    def test_named_field_to_correct(self) -> None:
        correcting = pending(PendingKind.correction_field)
        extracted = out(correction_target="location")
        turn = turn_of(to_turn_input(extracted, correcting, TurnContext()))
        assert turn.proposals == [CorrectionFieldProposal(value=FieldName.location)]


class TestSlots:
    @pytest.mark.ac("003:AC-6")
    def test_offered_slot_becomes_slot_selected(self) -> None:
        mapped = to_turn_input(out(chosen_option_id="s2", language="es"), AT_SLOT, TurnContext())
        assert mapped.turn_input == SlotSelected(slot_id="s2")

    @pytest.mark.ac("003:AC-6")
    def test_none_fits_becomes_no_slot_fits(self) -> None:
        mapped = to_turn_input(out(no_option_fits=True), AT_SLOT, TurnContext())
        assert mapped.turn_input == NoSlotFits()

    @pytest.mark.ac("003:AC-4")
    def test_slot_not_offered_is_an_empty_turn(self) -> None:
        mapped = to_turn_input(out(chosen_option_id="s9"), AT_SLOT, TurnContext())
        assert turn_of(mapped).proposals == []
        assert mapped.dropped == [DroppedProposal(field="slot", reason="slot_not_offered")]

    def test_slot_with_other_content_lets_the_turn_win(self) -> None:
        # Plan OQ-7: "el martes, y por cierto tengo 26" -> the correction goes first.
        mapped = to_turn_input(out(chosen_option_id="s1", age=26), AT_SLOT, TurnContext())
        assert turn_of(mapped).proposals == [AgeProposal(value=AgeAnswer(age=26))]
        assert mapped.dropped == [
            DroppedProposal(field="slot", reason="slot_pick_with_other_content")
        ]

    def test_slot_with_a_signal_lets_the_turn_win(self) -> None:
        mapped = to_turn_input(out(chosen_option_id="s1", opt_out=True), AT_SLOT, TurnContext())
        assert turn_of(mapped).signals.opt_out is True

    def test_option_id_outside_a_choice_or_slot_is_ignored(self) -> None:
        mapped = to_turn_input(out(chosen_option_id="car"), AT_AGE, TurnContext())
        assert turn_of(mapped).proposals == []


class TestSignals:
    @pytest.mark.ac("003:AC-7")
    def test_faq_text_and_sentiment_stay_out_of_the_engine(self) -> None:
        extracted = out(faq_question="¿Cuánto se cobra por pedido?", sentiment="negative")
        mapped = to_turn_input(extracted, AT_AGE, TurnContext())
        assert turn_of(mapped).signals == Signals(faq_question=True)
        assert mapped.faq_question == "¿Cuánto se cobra por pedido?"
        assert mapped.sentiment == "negative"

    def test_flags_and_language_are_copied(self) -> None:
        extracted = out(
            opt_out=True,
            wants_human=True,
            is_correction=True,
            off_topic=True,
            abuse=True,
            language="en",
        )
        assert turn_of(to_turn_input(extracted, AT_AGE, TurnContext())).signals == Signals(
            opt_out=True,
            wants_human=True,
            correction=True,
            off_topic=True,
            abuse=True,
            language=Language.en,
        )

    def test_blank_faq_text_is_no_question(self) -> None:
        turn = turn_of(to_turn_input(out(faq_question="  "), AT_AGE, TurnContext()))
        assert turn.signals.faq_question is False
        assert to_turn_input(out(faq_question="  "), AT_AGE, TurnContext()).faq_question is None
