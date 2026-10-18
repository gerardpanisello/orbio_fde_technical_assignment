"""Short builders for LLM layer tests (plan §7.1)."""

from typing import Any

from sazon_screening.config import EngineConfig
from sazon_screening.config.areas import AreaRef
from sazon_screening.engine import (
    AskCorrectionField,
    AskField,
    ClosedAck,
    CloseDisqualified,
    CloseInterviewCancelled,
    CloseNeedsReview,
    CloseOptedOut,
    CloseQualifiedUnscheduled,
    CloseWaitlisted,
    ConfirmAmbiguous,
    ConfirmInterview,
    ConfirmValue,
    EngineAction,
    HandoffToHuman,
    KeepInterview,
    OfferSlots,
    Preface,
    PrimaryAction,
    ReaskField,
    ShowRecap,
)
from sazon_screening.engine.state import Experience
from sazon_screening.llm.extraction.pending import OptionView, PendingView
from sazon_screening.llm.extraction.schema import ExtractionOutput
from sazon_screening.llm.phrasing.templates import RenderContext
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.vocab import (
    Country,
    DisqualificationReason,
    FieldName,
    Language,
    PendingKind,
    ReaskReason,
    Register,
    ReviewReason,
    Stage,
)
from tests.engine.builders import Convo


def out(**fields: Any) -> ExtractionOutput:
    """An extraction result with only the given fields set."""
    return ExtractionOutput(**fields)


def pending(
    kind: PendingKind = PendingKind.ask,
    field: FieldName | None = None,
    options: tuple[str, ...] = (),
) -> PendingView:
    """A pending ask; option labels are just their ids."""
    return PendingView(
        kind=kind,
        field=field,
        options=[OptionView(id=option, label=option) for option in options],
        current_values={},
    )


def asking(field: FieldName) -> PendingView:
    return pending(PendingKind.ask, field)


# --- phrasing ----------------------------------------------------------------------------

SLOTS = {
    "s1": SlotDisplay(
        id="s1",
        labels={
            Language.es: "martes 14/10, 10:00",
            Language.en: "Tue 14 Oct, 10am",
            Language.ca: "dimarts 14/10, 10:00",
        },
    ),
    "s2": SlotDisplay(
        id="s2",
        labels={
            Language.es: "miércoles 15/10, 16:00",
            Language.en: "Wed 15 Oct, 4pm",
            Language.ca: "dimecres 15/10, 16:00",
        },
    ),
}
PRIVACY_URL = "https://example.com/privacy"
EL_CARMEN = [
    AreaRef(id="mty-el-carmen", country=Country.MX, city="monterrey", zone="mty-el-carmen"),
    AreaRef(id="val-el-carmen", country=Country.ES, city="valencia", zone="val-el-carmen"),
]


def ctx(**fields: Any) -> RenderContext:
    return RenderContext(**{"privacy_url": PRIVACY_URL, "slots": SLOTS, **fields})


def language_of(register: Register) -> Language:
    return register.language


def action(
    primary: PrimaryAction, *prefaces: Preface, register: Register = Register.es_ES
) -> EngineAction:
    return EngineAction(
        primary=primary,
        prefaces=list(prefaces),
        language=language_of(register),
        register=register,
    )


def sample_primaries(config: EngineConfig) -> list[PrimaryAction]:
    """One of every primary action type except no_message, with realistic payloads."""
    profile = Convo(config).advance_to(Stage.recap).state.profile
    return [
        AskField(field=FieldName.vehicle_type),
        ReaskField(
            field=FieldName.vehicle_type, reason=ReaskReason.unclear, options=["motorbike", "car"]
        ),
        ConfirmAmbiguous(field=FieldName.location, options=EL_CARMEN),
        ConfirmValue(field=FieldName.experience, value=Experience(years=45, platforms=[])),
        AskCorrectionField(),
        ShowRecap(profile=profile),
        OfferSlots(slot_ids=["s1", "s2"]),
        OfferSlots(slot_ids=["s1", "s2"], reason="slot_taken"),  # spec 010
        OfferSlots(slot_ids=["s1", "s2"], reason="reschedule"),
        ConfirmInterview(slot_id="s1"),
        KeepInterview(slot_id="s1"),
        CloseInterviewCancelled(),
        CloseDisqualified(reason=DisqualificationReason.no_license),
        CloseNeedsReview(reasons=[ReviewReason.human_requested]),
        CloseOptedOut(),
        CloseQualifiedUnscheduled(),
        CloseWaitlisted(area_id="mad-salamanca"),
        HandoffToHuman(),
        ClosedAck(),
    ]
