"""Test driver: one line per conversation turn (plan §7.2).

c = Convo(config)
c.say(consent(True), name("Ana López")).expect(AskField, field="age")
"""

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
    Status,
    VehicleType,
)
from sazon_screening.engine.inputs import (
    AgeAnswer,
    AgeProposal,
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

    def reasks(self, field: FieldName) -> int:
        return self.state.reasks.get(field, 0)

    def primaries(self) -> list[str]:
        """`type` of every primary action so far, e.g. for flow-order assertions (AC-1)."""
        return [action.primary.type for action in self.history]
