"""Deterministic screening engine (spec 002): pure functions, no I/O, no LLM.

    from sazon_screening.config import load_config
    from sazon_screening.engine import start, step, build_record

    config = load_config(Path("config"))
    state, action = start(config, country_hint=Country.MX)
    state, action = step(state, CandidateTurn(...), config, today)
    record = build_record(state, config)

Exports are resolved lazily (PEP 562). `config/models.py` imports engine submodules
(enums, the location index), which runs this file first; eager imports of `step` here
would then import a half-initialised `sazon_screening.config`. Static type checkers
see the real names through the TYPE_CHECKING block.
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    )
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
        StartDateExpr,
        StartDateProposal,
        TurnContext,
        TurnInput,
        Unclear,
        VehicleProposal,
    )
    from sazon_screening.engine.record import (
        CandidateRecord,
        FieldRecord,
        RecordFields,
        build_record,
    )
    from sazon_screening.engine.scoring import ScoreFactor, ScoreResult, score_candidate
    from sazon_screening.engine.state import ConversationState, PostCloseCorrection, Profile
    from sazon_screening.engine.turn import start, step

__all__ = [
    "UNCLEAR",
    "AbsoluteDate",
    "AckCorrection",
    "AgeAnswer",
    "AgeProposal",
    "AnswerFaq",
    "Asap",
    "AskCorrectionField",
    "AskField",
    "AvailabilityProposal",
    "CandidateRecord",
    "CandidateTurn",
    "ChoiceProposal",
    "CloseDisqualified",
    "CloseNeedsReview",
    "CloseOptedOut",
    "CloseQualifiedUnscheduled",
    "ClosedAck",
    "ConfirmAmbiguous",
    "ConfirmInterview",
    "ConfirmValue",
    "ConfirmationProposal",
    "ConsentProposal",
    "ConversationState",
    "EngineAction",
    "ExperienceAnswer",
    "ExperienceProposal",
    "FieldRecord",
    "HandoffToHuman",
    "LicenseProposal",
    "LocationAnswer",
    "LocationProposal",
    "NameProposal",
    "NextWeekday",
    "NoMessage",
    "NoSlotFits",
    "OfferSlots",
    "Offset",
    "PostCloseCorrection",
    "Preface",
    "PrimaryAction",
    "Profile",
    "Proposal",
    "ReaskField",
    "RecordFields",
    "Redirect",
    "ScheduleProposal",
    "ScoreFactor",
    "ScoreResult",
    "ShowRecap",
    "Signals",
    "SilenceExpired",
    "SlotSelected",
    "StartDateExpr",
    "StartDateProposal",
    "TurnContext",
    "TurnInput",
    "Unclear",
    "VehicleProposal",
    "build_record",
    "score_candidate",
    "start",
    "step",
]

# Where the exported names live, searched in this order on first access.
_SOURCES = ("turn", "record", "scoring", "state", "actions", "inputs")


def __getattr__(name: str) -> object:
    if name in __all__:
        for source in _SOURCES:
            module = import_module(f"{__name__}.{source}")
            if hasattr(module, name):
                return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
