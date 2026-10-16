"""What the engine accepts each turn (ADR 0005, plan §3.3).

The LLM layer (003) turns a candidate's message into a `CandidateTurn`: typed proposals
plus signals. Timers (008) and calendars (010) send events. Nothing here is free text
the engine must interpret, and nothing here can say "approve this candidate": that
decision only exists in the rules.

Types are deliberately permissive (any int age, any int years). Range checks are
business rules and produce re-asks, not validation errors (NFR-5).
"""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sazon_screening.vocab import (
    Availability,
    Country,
    FieldName,
    Language,
    ScheduleSlot,
    VehicleType,
    Weekday,
)


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Unclear(_Input):
    """The extractor saw an answer for this field but could not read a clear value.

    `kind` has no default on purpose: an empty `{}` from the LLM must fail validation
    (-> extraction_failed in 003), not silently count as an unclear answer.
    """

    kind: Literal["unclear"]


UNCLEAR = Unclear(kind="unclear")


# --- start date (FR-22) ----------------------------------------------------------------
# The extractor turns "el lunes" into a structure; the engine does the calendar maths,
# because "which Monday?" is deterministic and easy to get wrong in a prompt.


class Asap(_Input):
    kind: Literal["asap"] = "asap"


class AbsoluteDate(_Input):
    kind: Literal["absolute"] = "absolute"
    on: date


class Offset(_Input):
    """n days, weeks or months from today. Months are month-level: "el mes que viene" is
    the 1st of next month (or today, if that is today), flagged `start_date_approximate`."""

    kind: Literal["offset"] = "offset"
    amount: int
    unit: Literal["days", "weeks", "months"]


class NextWeekday(_Input):
    kind: Literal["next_weekday"] = "next_weekday"
    weekday: Weekday


class DayMonth(_Input):
    """A date without a year ("el 3 de noviembre"). The engine picks the year (spec 003 §8).

    Plain ints, not a `date`: 31/02 must reach the engine and become a re-ask, not fail
    validation and sink the whole turn.
    """

    kind: Literal["day_month"] = "day_month"
    day: int
    month: int


class Month(_Input):
    """A month without a day ("en noviembre"): the 1st of its next occurrence, or today if
    it is the current month. Month-level, so flagged `start_date_approximate`.

    A plain int, like `DayMonth`: month 13 must become a re-ask, not sink the turn.
    """

    kind: Literal["month"] = "month"
    month: int


StartDateExpr = Annotated[
    Asap | AbsoluteDate | Offset | NextWeekday | DayMonth | Month, Field(discriminator="kind")
]
_StartDateOrUnclear = Annotated[
    Asap | AbsoluteDate | Offset | NextWeekday | DayMonth | Month | Unclear,
    Field(discriminator="kind"),
]


# --- structured answers --------------------------------------------------------------


class AgeAnswer(_Input):
    """An explicit age, a birth year, or just "I am over 18".

    Precedence: age > birth_year > is_adult.
    A birth year is kept as said: the engine works out the age from `today` (spec 003 §8),
    because subtracting years is calendar maths the extractor must not do.
    """

    is_adult: bool | None = None
    age: int | None = None
    birth_year: int | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> Self:
        if self.is_adult is None and self.age is None and self.birth_year is None:
            raise ValueError("age answer needs is_adult, age or birth_year")
        return self


class LocationAnswer(_Input):
    text: str
    # Set by the extractor (world knowledge): is this a real place? A real place we do
    # not serve is out of area; unreadable text is re-asked instead (FR-19).
    is_known_place: bool


class ExperienceAnswer(_Input):
    years: int | Literal["none"] | None = None
    platforms: list[str] = []


# --- proposals: one model per field, discriminated on `field` ------------------------


class ConsentProposal(_Input):
    field: Literal["consent"] = "consent"
    value: bool | Unclear


class NameProposal(_Input):
    field: Literal["full_name"] = "full_name"
    value: str | Unclear


class AgeProposal(_Input):
    field: Literal["age"] = "age"
    value: AgeAnswer | Unclear


class VehicleProposal(_Input):
    field: Literal["vehicle_type"] = "vehicle_type"
    value: VehicleType | Unclear


class LicenseProposal(_Input):
    field: Literal["has_license"] = "has_license"
    value: bool | Unclear


class LocationProposal(_Input):
    """Also carries zone answers: one location schema for the extractor."""

    field: Literal["location"] = "location"
    value: LocationAnswer | Unclear


class AvailabilityProposal(_Input):
    field: Literal["availability"] = "availability"
    value: list[Availability] | Unclear


class ScheduleProposal(_Input):
    field: Literal["schedule"] = "schedule"
    value: list[ScheduleSlot] | Unclear


class ExperienceProposal(_Input):
    field: Literal["experience"] = "experience"
    value: ExperienceAnswer | Unclear


class StartDateProposal(_Input):
    field: Literal["start_date"] = "start_date"
    value: _StartDateOrUnclear


class ConfirmationProposal(_Input):
    """Yes/no to the recap or to a value confirmation."""

    field: Literal["confirmation"] = "confirmation"
    value: bool | Unclear


class ChoiceProposal(_Input):
    """The option id picked from a `confirm_ambiguous` list."""

    field: Literal["choice"] = "choice"
    value: str | Unclear


class CorrectionFieldProposal(_Input):
    """The candidate names a field to change, without the new value ("la zona está mal").

    Only used at the recap (spec 003 §8): the engine then asks that field again. A
    field name, not a value, so nothing here can change the profile by itself.
    """

    field: Literal["correction_field"] = "correction_field"
    value: FieldName


Proposal = Annotated[
    ConsentProposal
    | NameProposal
    | AgeProposal
    | VehicleProposal
    | LicenseProposal
    | LocationProposal
    | AvailabilityProposal
    | ScheduleProposal
    | ExperienceProposal
    | StartDateProposal
    | ConfirmationProposal
    | ChoiceProposal
    | CorrectionFieldProposal,
    Field(discriminator="field"),
]


# --- signals, context, turn --------------------------------------------------------


class Signals(_Input):
    """Intent flags the extractor detected besides field values (FR-2)."""

    opt_out: bool = False
    wants_human: bool = False
    correction: bool = False
    faq_question: bool = False
    off_topic: bool = False
    abuse: bool = False
    extraction_failed: bool = False
    language: Language | None = None


class TurnContext(_Input):
    country_hint: Country | None = None  # e.g. from the phone prefix
    offered_slots: list[str] | None = None  # slot ids from 010; read when entering scheduling
    # The candidate's area is at or above its target staffing (spec 015). The caller
    # computes it from live occupancy; the engine reads it only when entering scheduling.
    zone_full: bool = False


class CandidateTurn(_Input):
    kind: Literal["turn"] = "turn"
    proposals: list[Proposal] = []
    signals: Signals = Signals()
    context: TurnContext = TurnContext()


# --- out-of-band events (FR-3) -------------------------------------------------------


class SilenceExpired(_Input):
    kind: Literal["silence_expired"] = "silence_expired"


class SlotSelected(_Input):
    kind: Literal["slot_selected"] = "slot_selected"
    slot_id: str


class NoSlotFits(_Input):
    kind: Literal["no_slot_fits"] = "no_slot_fits"


TurnInput = Annotated[
    CandidateTurn | SilenceExpired | SlotSelected | NoSlotFits, Field(discriminator="kind")
]
