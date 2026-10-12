"""Hypothesis strategies: random conversations made of valid, invalid and unclear input."""

from datetime import date

from hypothesis import strategies as st

from sazon_screening.engine.inputs import (
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
    Proposal,
    ScheduleProposal,
    Signals,
    SilenceExpired,
    SlotSelected,
    StartDateProposal,
    TurnContext,
    TurnInput,
    VehicleProposal,
)
from sazon_screening.vocab import (
    Availability,
    Country,
    FieldName,
    Language,
    ScheduleSlot,
    VehicleType,
    Weekday,
)
from tests.engine.builders import canonical_turns

unclear = st.just(UNCLEAR)
SLOT_IDS = ["s1", "s2", "s3"]
PLACES = [
    "Coyoacán",
    "Cuyoacán",
    "CDMX",
    "Madrid",
    "Centro",
    "El Carmen",
    "Vallecas, Madrid",
    "Coyoacán, CDMX",
    "Zaragoza",
    "xjkq",
    "BCN",
]
OPTION_IDS = ["mty-el-carmen", "val-el-carmen", "madrid", "mad-centro", "nope"]


def _age() -> st.SearchStrategy[AgeAnswer]:
    return st.one_of(
        st.builds(AgeAnswer, age=st.integers(-5, 200)),
        st.builds(AgeAnswer, is_adult=st.booleans()),
        st.builds(AgeAnswer, is_adult=st.booleans(), age=st.integers(0, 120)),
        st.builds(AgeAnswer, birth_year=st.integers(1890, 2030)),  # incl. boundary years
        st.builds(AgeAnswer, birth_year=st.integers(1990, 2015), age=st.integers(10, 40)),
    )


def _start_date() -> st.SearchStrategy[object]:
    return st.one_of(
        st.just(Asap()),
        st.builds(AbsoluteDate, on=st.dates(date(2020, 1, 1), date(2030, 12, 31))),
        st.builds(
            Offset,
            amount=st.integers(-30, 10**9),
            unit=st.sampled_from(["days", "weeks"]),
        ),
        st.builds(NextWeekday, weekday=st.sampled_from(list(Weekday))),
        # valid, impossible (31/02, month 13) and leap-day values
        st.builds(DayMonth, day=st.integers(-1, 32), month=st.integers(0, 13)),
    )


def proposals() -> st.SearchStrategy[Proposal]:
    """One proposal for any field, with valid, invalid and UNCLEAR values."""
    return st.one_of(
        st.builds(ConsentProposal, value=st.booleans() | unclear),
        st.builds(
            NameProposal,
            value=st.sampled_from(["Ana López", "Ana", "Ana2 López", "", "María-José O'Neill"])
            | st.text(max_size=20)
            | unclear,
        ),
        st.builds(AgeProposal, value=_age() | unclear),
        st.builds(VehicleProposal, value=st.sampled_from(list(VehicleType)) | unclear),
        st.builds(LicenseProposal, value=st.booleans() | unclear),
        st.builds(
            LocationProposal,
            value=st.builds(
                LocationAnswer,
                text=st.sampled_from(PLACES) | st.text(max_size=15),
                is_known_place=st.booleans(),
            )
            | unclear,
        ),
        st.builds(
            AvailabilityProposal,
            value=st.lists(st.sampled_from(list(Availability)), max_size=4) | unclear,
        ),
        st.builds(
            ScheduleProposal,
            value=st.lists(st.sampled_from(list(ScheduleSlot)), max_size=5) | unclear,
        ),
        st.builds(
            ExperienceProposal,
            value=st.builds(
                ExperienceAnswer,
                years=st.integers(-3, 80) | st.just("none") | st.none(),
                platforms=st.lists(
                    st.sampled_from(["Glovo", "uber", "Rappi Turbo", ""]) | st.text(max_size=8),
                    max_size=3,
                ),
            )
            | unclear,
        ),
        st.builds(StartDateProposal, value=_start_date() | unclear),
        st.builds(ConfirmationProposal, value=st.booleans() | unclear),
        st.builds(ChoiceProposal, value=st.sampled_from(OPTION_IDS) | unclear),
        st.builds(CorrectionFieldProposal, value=st.sampled_from(list(FieldName))),
    )


def _rare() -> st.SearchStrategy[bool]:
    """Mostly False: signals that end a conversation should not end every example."""
    return st.sampled_from([False, False, False, False, False, True])


def signals() -> st.SearchStrategy[Signals]:
    return st.builds(
        Signals,
        opt_out=st.sampled_from([False] * 15 + [True]),
        wants_human=_rare(),
        correction=st.booleans(),
        faq_question=_rare(),
        off_topic=_rare(),
        abuse=_rare(),
        extraction_failed=_rare(),
        language=st.none() | st.sampled_from(list(Language)),
    )


def contexts() -> st.SearchStrategy[TurnContext]:
    return st.builds(
        TurnContext,
        country_hint=st.none() | st.sampled_from(list(Country)),
        offered_slots=st.none() | st.lists(st.sampled_from(SLOT_IDS), max_size=3),
        zone_full=st.booleans(),  # spec 015: the area may be full at any turn
    )


def candidate_turns() -> st.SearchStrategy[CandidateTurn]:
    return st.builds(
        CandidateTurn,
        proposals=st.lists(proposals(), max_size=4),
        signals=signals(),
        context=contexts(),
    )


def events() -> st.SearchStrategy[TurnInput]:
    return st.one_of(
        st.just(SilenceExpired()),
        st.builds(SlotSelected, slot_id=st.sampled_from([*SLOT_IDS, "s9"])),
        st.just(NoSlotFits()),
    )


def turn_inputs() -> st.SearchStrategy[TurnInput]:
    candidate: st.SearchStrategy[TurnInput] = candidate_turns()
    return st.one_of(candidate, candidate, candidate, candidate, events())


@st.composite
def conversations(draw: st.DrawFn) -> list[TurnInput]:
    """A valid prefix of random length (to reach every stage), then random turns."""
    canonical: list[TurnInput] = list(canonical_turns())
    prefix = draw(st.integers(0, len(canonical)))
    return canonical[:prefix] + draw(st.lists(turn_inputs(), max_size=40))
