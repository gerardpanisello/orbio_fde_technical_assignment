"""What the engine returns (ADR 0005, plan §3.5): one primary action plus optional prefaces.

Actions are typed intents, never text. Options are IDs (enum values, area ids, slot
ids); the phrasing layer (003) turns them into words in the candidate's language and
register, so the engine stays language-neutral.
"""

import warnings
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from sazon_screening.config.areas import AreaRef
from sazon_screening.engine.state import Experience, Profile
from sazon_screening.vocab import (
    Country,
    DisqualificationReason,
    FieldName,
    Language,
    ReaskReason,
    Register,
    ReviewReason,
)


class _Action(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- primary actions -------------------------------------------------------------------


class AskField(_Action):
    type: Literal["ask_field"] = "ask_field"
    field: FieldName


class ReaskField(_Action):
    type: Literal["reask_field"] = "reask_field"
    field: FieldName
    reason: ReaskReason
    options: list[str] = []


class ConfirmAmbiguous(_Action):
    type: Literal["confirm_ambiguous"] = "confirm_ambiguous"
    field: FieldName
    options: list[AreaRef]


class ConfirmValue(_Action):
    type: Literal["confirm_value"] = "confirm_value"
    field: FieldName
    value: Experience


class AskCorrectionField(_Action):
    type: Literal["ask_correction_field"] = "ask_correction_field"


class ShowRecap(_Action):
    type: Literal["show_recap"] = "show_recap"
    profile: Profile  # pass a copy: the state's profile keeps changing after this turn
    # The start date is month-level ("el mes que viene"): show the month, not the 1st.
    start_date_approximate: bool = False


class OfferSlots(_Action):
    type: Literal["offer_slots"] = "offer_slots"
    slot_ids: list[str]
    # Spec 010: why these slots: the first offer (None), the picked one just filled up
    # ("slot_taken"), or the candidate is moving a booked interview ("reschedule").
    reason: Literal["slot_taken", "reschedule"] | None = None


class ConfirmInterview(_Action):
    type: Literal["confirm_interview"] = "confirm_interview"
    slot_id: str


class KeepInterview(_Action):
    """Spec 010: a reschedule found no new slot (or none fitted): the booked one stays."""

    type: Literal["keep_interview"] = "keep_interview"
    slot_id: str


class CloseInterviewCancelled(_Action):
    """Spec 010: the candidate cancelled their interview; they stay qualified."""

    type: Literal["close_interview_cancelled"] = "close_interview_cancelled"


class CloseDisqualified(_Action):
    type: Literal["close_disqualified"] = "close_disqualified"
    reason: DisqualificationReason


class CloseNeedsReview(_Action):
    type: Literal["close_needs_review"] = "close_needs_review"
    reasons: list[ReviewReason]


class CloseOptedOut(_Action):
    type: Literal["close_opted_out"] = "close_opted_out"


class CloseQualifiedUnscheduled(_Action):
    type: Literal["close_qualified_unscheduled"] = "close_qualified_unscheduled"


class CloseWaitlisted(_Action):
    """Qualified, but the candidate's area is fully staffed: no slots, a waitlist (spec 015)."""

    type: Literal["close_waitlisted"] = "close_waitlisted"
    area_id: str  # zone id, or city id for a city served as a whole


class HandoffToHuman(_Action):
    type: Literal["handoff_to_human"] = "handoff_to_human"


class ClosedAck(_Action):
    """Short acknowledgement on a closed conversation; screening data does not change."""

    type: Literal["closed_ack"] = "closed_ack"


class NoMessage(_Action):
    """Send nothing (e.g. after silence_expired). Explicit so channels never guess (OQ-2)."""

    type: Literal["no_message"] = "no_message"


PrimaryAction = Annotated[
    AskField
    | ReaskField
    | ConfirmAmbiguous
    | ConfirmValue
    | AskCorrectionField
    | ShowRecap
    | OfferSlots
    | ConfirmInterview
    | KeepInterview
    | CloseInterviewCancelled
    | CloseDisqualified
    | CloseNeedsReview
    | CloseOptedOut
    | CloseQualifiedUnscheduled
    | CloseWaitlisted
    | HandoffToHuman
    | ClosedAck
    | NoMessage,
    Field(discriminator="type"),
]


# --- prefaces: said before the primary action ------------------------------------------


class AnswerFaq(_Action):
    type: Literal["answer_faq"] = "answer_faq"


class AckCorrection(_Action):
    type: Literal["ack_correction"] = "ack_correction"
    fields: list[FieldName]


class Redirect(_Action):
    type: Literal["redirect"] = "redirect"
    reason: Literal["off_topic", "abuse"]


Preface = Annotated[AnswerFaq | AckCorrection | Redirect, Field(discriminator="type")]


# `register` is the contract name (ADR 0005). Pydantic warns it shadows `ABCMeta.register`,
# but that method lives on the metaclass: `action.register` still reads the field.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='Field name "register"', category=UserWarning)

    class EngineAction(_Action):
        primary: PrimaryAction
        prefaces: list[Preface] = []  # fixed order: redirect, ack_correction, answer_faq
        language: Language
        register: Register


def register_for(
    language: Language,
    country: Country | None,
    country_hint: Country | None,
    *,
    default_country: Country,
) -> Register:
    """Spanish register follows where the candidate works, else where their phone is from.

    The stored location beats the phone prefix: a Mexican number applying in Madrid is
    talked to in es-ES, because that is where the job (and the recruiter) is.
    """
    if language is Language.en:
        return Register.en
    country = country or country_hint or default_country
    return Register.es_MX if country is Country.MX else Register.es_ES
