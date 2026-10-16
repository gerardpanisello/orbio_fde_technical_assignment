"""One builder per field: model output -> one engine proposal (plan §3.6 rules 1-5).

Each builder returns a proposal, None (the candidate did not mention it), or raises
`DropError` with a reason for the trace. Builders never compute anything the engine
owns: no dates, no ages, no service-area ids (FR-8).
"""

from collections.abc import Callable
from datetime import date

from sazon_screening.engine import (
    AbsoluteDate,
    AgeAnswer,
    AgeProposal,
    Asap,
    AvailabilityProposal,
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
    Month,
    NameProposal,
    NextWeekday,
    Offset,
    Proposal,
    ScheduleProposal,
    StartDateExpr,
    StartDateProposal,
    VehicleProposal,
)
from sazon_screening.llm.extraction.pending import PendingView
from sazon_screening.llm.extraction.schema import ExtractionOutput
from sazon_screening.vocab import (
    Availability,
    FieldName,
    PendingKind,
    ScheduleSlot,
    VehicleType,
    Weekday,
)

Builder = Callable[[ExtractionOutput, PendingView], Proposal | None]
_CONFIRMING = (PendingKind.confirm_value, PendingKind.recap, PendingKind.correction_field)


class DropError(ValueError):
    """A builder rejects a value the model gave; `reason` ends up in the trace."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- knock-out fields ------------------------------------------------------------------


def consent(out: ExtractionOutput, _: PendingView) -> Proposal | None:
    return None if out.consent is None else ConsentProposal(value=out.consent == "yes")


def full_name(out: ExtractionOutput, _: PendingView) -> Proposal | None:
    if out.full_name is None:
        return None
    if not out.full_name.strip():
        raise DropError("empty_value")
    return NameProposal(value=out.full_name.strip())


def age(out: ExtractionOutput, _: PendingView) -> Proposal | None:
    """As stated: the engine turns a birth year into an age, never the model (FR-8)."""
    if out.age is None and out.birth_year is None and out.is_adult is None:
        return None
    return AgeProposal(
        value=AgeAnswer(age=out.age, birth_year=out.birth_year, is_adult=out.is_adult)
    )


def vehicle_type(out: ExtractionOutput, _: PendingView) -> Proposal | None:
    if out.vehicle_type is None:
        return None
    return VehicleProposal(value=VehicleType(out.vehicle_type))


def has_license(out: ExtractionOutput, _: PendingView) -> Proposal | None:
    return None if out.has_license is None else LicenseProposal(value=out.has_license)


def location(out: ExtractionOutput, _: PendingView) -> Proposal | None:
    """Zone first, then city, joined by a comma: the engine splits on `,` (carry-over 1).

    An unknown `is_real_place` counts as not known: the engine then re-asks instead of
    closing as out of area, because ambiguity never disqualifies.
    """
    parts = [part.strip() for part in (out.location_zone, out.location_city) if part]
    text = ", ".join(part for part in parts if part)
    if not text:
        return None
    answer = LocationAnswer(text=text, is_known_place=out.location_is_real_place is True)
    return LocationProposal(value=answer)


# --- profile fields --------------------------------------------------------------------


def availability(out: ExtractionOutput, _: PendingView) -> Proposal | None:
    if not out.availability:  # an empty list says nothing
        return None
    return AvailabilityProposal(value=[Availability(value) for value in out.availability])


def schedule(out: ExtractionOutput, _: PendingView) -> Proposal | None:
    if not out.schedule:
        return None
    return ScheduleProposal(value=[ScheduleSlot(value) for value in out.schedule])


def experience(out: ExtractionOutput, _: PendingView) -> Proposal | None:
    """Platforms without years keep `years=None`: the engine asks, we never guess."""
    if out.no_experience:
        return ExperienceProposal(value=ExperienceAnswer(years="none"))
    if out.experience_years is None and not out.platforms:
        return None
    answer = ExperienceAnswer(years=out.experience_years, platforms=out.platforms or [])
    return ExperienceProposal(value=answer)


def start_date(out: ExtractionOutput, pending: PendingView) -> Proposal | None:
    """An "asap" volunteered while we ask something else is dropped: "ya quiero empezar"
    is eagerness, not a start date (eval 2026-10-12). Explicit dates are kept.
    """
    if out.start_kind is None:
        return None
    if out.start_kind == "asap" and not _start_date_in_question(pending):
        raise DropError("unsolicited_asap")
    return StartDateProposal(value=_start_expression(out))


def _start_date_in_question(pending: PendingView) -> bool:
    if pending.kind in (PendingKind.recap, PendingKind.correction_field):
        return True
    return pending.kind is PendingKind.ask and pending.field is FieldName.start_date


def _start_expression(out: ExtractionOutput) -> StartDateExpr:
    """Exactly the structure the candidate used; a missing part drops the proposal."""
    match out.start_kind:
        case "asap":
            return Asap()
        case "absolute" if out.start_date_iso is not None:
            return AbsoluteDate(on=_full_date(out.start_date_iso))
        case "day_month" if out.start_day is not None and out.start_month is not None:
            return DayMonth(day=out.start_day, month=out.start_month)
        case "offset" if out.start_offset_amount is not None and out.start_offset_unit:
            return Offset(amount=out.start_offset_amount, unit=out.start_offset_unit)
        case "next_weekday" if out.start_weekday is not None:
            return NextWeekday(weekday=Weekday(out.start_weekday))
        case "month" if out.start_month is not None:
            return Month(month=out.start_month)
    raise DropError("invalid_date")


def _full_date(text: str) -> date:
    """Only YYYY-MM-DD: a date without a year must come as `day_month` instead."""
    try:
        if len(text) != len("YYYY-MM-DD"):
            raise ValueError(text)
        return date.fromisoformat(text)
    except ValueError:
        raise DropError("invalid_date") from None


# --- answers to what the engine asked --------------------------------------------------


def confirmation(out: ExtractionOutput, pending: PendingView) -> Proposal | None:
    """A yes/no only counts where the engine asked to confirm something."""
    if out.confirmation is None:
        return None
    if pending.kind not in _CONFIRMING:
        raise DropError("no_confirmation_pending")
    return ConfirmationProposal(value=out.confirmation == "yes")


def choice(out: ExtractionOutput, pending: PendingView) -> Proposal | None:
    """Only an id we offered: the model must copy it, never invent one."""
    if out.chosen_option_id is None or pending.kind is not PendingKind.confirm_ambiguous:
        return None
    if out.chosen_option_id not in pending.option_ids():
        raise DropError("choice_not_offered")
    return ChoiceProposal(value=out.chosen_option_id)


def correction_field(out: ExtractionOutput, _: PendingView) -> Proposal | None:
    if out.correction_target is None:
        return None
    return CorrectionFieldProposal(value=FieldName(out.correction_target))


# Order = order of the proposals sent to the engine (it applies them in stage order anyway).
BUILDERS: tuple[tuple[str, Builder], ...] = (
    ("consent", consent),
    ("full_name", full_name),
    ("age", age),
    ("vehicle_type", vehicle_type),
    ("has_license", has_license),
    ("location", location),
    ("availability", availability),
    ("schedule", schedule),
    ("experience", experience),
    ("start_date", start_date),
    ("confirmation", confirmation),
    ("choice", choice),
    ("correction_field", correction_field),
)
