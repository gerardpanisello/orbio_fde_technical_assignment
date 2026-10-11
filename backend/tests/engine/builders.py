"""Test driver: one line per conversation turn (plan §7.2).

c = Convo(config)
c.say(consent(True), name("Ana López")).expect(AskField, field="age")
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Self

from pydantic import TypeAdapter

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import EngineAction
from sazon_screening.engine.enums import (
    Availability,
    Country,
    FieldName,
    Language,
    ScheduleSlot,
    Stage,
    Status,
    VehicleType,
)
from sazon_screening.engine.inputs import (
    AgeAnswer,
    AgeProposal,
    Asap,
    AvailabilityProposal,
    CandidateTurn,
    ChoiceProposal,
    ConfirmationProposal,
    ConsentProposal,
    ExperienceAnswer,
    ExperienceProposal,
    LicenseProposal,
    LocationAnswer,
    LocationProposal,
    NameProposal,
    NoSlotFits,
    Proposal,
    ScheduleProposal,
    Signals,
    SilenceExpired,
    SlotSelected,
    StartDateExpr,
    StartDateProposal,
    TurnContext,
    TurnInput,
    VehicleProposal,
)
from sazon_screening.engine.record import CandidateRecord, build_record
from sazon_screening.engine.step import start, step_unchecked
from tests.engine.conftest import TODAY

# --- proposal factories ---------------------------------------------------------------


def consent(value: bool = True) -> ConsentProposal:
    return ConsentProposal(value=value)


def name(text: str) -> NameProposal:
    return NameProposal(value=text)


def age(years: int) -> AgeProposal:
    return AgeProposal(value=AgeAnswer(age=years))


def adult(is_adult: bool = True) -> AgeProposal:
    return AgeProposal(value=AgeAnswer(is_adult=is_adult))


def vehicle(kind: str) -> VehicleProposal:
    return VehicleProposal(value=VehicleType(kind))


def license(has_one: bool) -> LicenseProposal:
    return LicenseProposal(value=has_one)


def loc(text: str, *, known: bool = True) -> LocationProposal:
    return LocationProposal(value=LocationAnswer(text=text, is_known_place=known))


def avail(*values: str) -> AvailabilityProposal:
    return AvailabilityProposal(value=[Availability(v) for v in values])


def sched(*values: str) -> ScheduleProposal:
    return ScheduleProposal(value=[ScheduleSlot(v) for v in values])


def exp(years: int | str, *platforms: str) -> ExperienceProposal:
    value = ExperienceAnswer.model_validate({"years": years, "platforms": list(platforms)})
    return ExperienceProposal(value=value)


def start_date(expr: StartDateExpr) -> StartDateProposal:
    return StartDateProposal(value=expr)


def yes() -> ConfirmationProposal:
    return ConfirmationProposal(value=True)


def no() -> ConfirmationProposal:
    return ConfirmationProposal(value=False)


def choice(option_id: str) -> ChoiceProposal:
    return ChoiceProposal(value=option_id)


_PROPOSALS: TypeAdapter[Proposal] = TypeAdapter(Proposal)


def unclear(field: str) -> Proposal:
    return _PROPOSALS.validate_python({"field": field, "value": {"kind": "unclear"}})


# --- conversation driver --------------------------------------------------------------


@dataclass(frozen=True)
class _Turn:
    proposals: tuple[Proposal, ...]
    offered_slots: list[str] | None = None


OFFERED_SLOTS = ["s1", "s2"]

# A valid candidate (Coyoacán, CDMX), one field per turn, in stage order (AC-1).
_CANONICAL_TURNS = (
    _Turn((consent(True),)),
    _Turn((name("Ana López"),)),
    _Turn((adult(),)),
    _Turn((vehicle("motorbike"),)),
    _Turn((license(True),)),
    _Turn((loc("Coyoacán"),)),
    _Turn((avail("full_time", "weekends"),)),
    _Turn((sched("flexible"),)),
    _Turn((exp(3, "Glovo"),)),
    _Turn((start_date(Asap()),)),
    _Turn((yes(),), offered_slots=OFFERED_SLOTS),
)


def canonical_turns() -> list[CandidateTurn]:
    """The canonical valid candidate as turn inputs (consent ... recap confirmed)."""
    return [
        CandidateTurn(
            proposals=list(turn.proposals),
            context=TurnContext(offered_slots=turn.offered_slots),
        )
        for turn in _CANONICAL_TURNS
    ]


class Convo:
    """Drives `step_unchecked` (so bugs are not hidden by the safety net) and records actions."""

    def __init__(
        self,
        config: EngineConfig,
        *,
        today: date = TODAY,
        country_hint: Country | None = None,
        language: Language = Language.es,
    ) -> None:
        self.config = config
        self.today = today
        self.state, action = start(config, language=language, country_hint=country_hint)
        self.history: list[EngineAction] = [action]

    @property
    def action(self) -> EngineAction:
        return self.history[-1]

    def event(self, turn: TurnInput) -> Self:
        self.state, action = step_unchecked(self.state, turn, self.config, self.today)
        self.history.append(action)
        return self

    def say(
        self,
        *proposals: Proposal,
        offered_slots: list[str] | None = None,
        country_hint: Country | None = None,
        **signals: Any,
    ) -> Self:
        turn = CandidateTurn(
            proposals=list(proposals),
            signals=Signals(**signals),
            context=TurnContext(country_hint=country_hint, offered_slots=offered_slots),
        )
        return self.event(turn)

    def silence(self) -> Self:
        return self.event(SilenceExpired())

    def select_slot(self, slot_id: str) -> Self:
        return self.event(SlotSelected(slot_id=slot_id))

    def no_slot_fits(self) -> Self:
        return self.event(NoSlotFits())

    def advance_to(self, stage: Stage) -> Self:
        """Answer as the canonical valid candidate until `stage` is the pending one."""
        for turn in _CANONICAL_TURNS:
            if self.state.stage == stage:
                return self
            self.say(*turn.proposals, offered_slots=turn.offered_slots)
        assert self.state.stage == stage, f"could not reach {stage}; at {self.state.stage}"
        return self

    def advance_to_status(self, status: Status, *, at: Stage | None = None) -> Self:
        """Reach `status`, optionally with the conversation pending at stage `at`."""
        match status:
            case Status.in_progress:
                self.advance_to(at or Stage.name)
            case Status.abandoned:
                self.advance_to(at or Stage.vehicle_license).silence()
            case Status.disqualified:
                self.advance_to(at or Stage.age)
                extra = (consent(True),) if self.state.stage is Stage.consent else ()
                self.say(*extra, age(17))
            case Status.needs_review:
                self.advance_to(at or Stage.location).say(wants_human=True)
            case Status.qualified_unscheduled:
                self.advance_to(Stage.scheduling).no_slot_fits()
            case Status.interview_scheduled:
                self.advance_to(Stage.scheduling).select_slot("s1")
            case Status.opted_out:
                self.advance_to(at or Stage.name).say(opt_out=True)
        assert self.state.status == status, f"wanted {status}, got {self.state.status}"
        return self

    # --- assertions -------------------------------------------------------------------

    def expect(self, kind: type, **attrs: Any) -> Self:
        primary = self.action.primary
        assert isinstance(primary, kind), f"expected {kind.__name__}, got {primary!r}"
        for attr, expected in attrs.items():
            actual = getattr(primary, attr)
            assert actual == expected, f"{kind.__name__}.{attr}: {actual!r} != {expected!r}"
        return self

    def expect_status(self, status: Status) -> Self:
        assert self.state.status == status, f"status {self.state.status} != {status}"
        return self

    def expect_prefaces(self, *kinds: type) -> Self:
        actual = [type(preface) for preface in self.action.prefaces]
        assert actual == list(kinds), f"prefaces {actual} != {list(kinds)}"
        return self

    def record(self) -> CandidateRecord:
        return build_record(self.state, self.config)

    def reasks(self, field: FieldName) -> int:
        return self.state.reasks.get(field, 0)

    def primaries(self) -> list[str]:
        """`type` of every primary action so far, e.g. for flow-order assertions (AC-1)."""
        return [action.primary.type for action in self.history]
