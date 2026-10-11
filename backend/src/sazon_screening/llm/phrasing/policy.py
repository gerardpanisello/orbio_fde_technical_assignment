"""Message rules that both the templates and the guard enforce (spec 001 §7, FR-12, FR-15).

One place, so a template can never break the rule the guard checks the model against.
"""

from sazon_screening.engine import AnswerFaq, EngineAction
from sazon_screening.llm.settings import LengthCaps

# Primary actions that ask the candidate something: exactly one question mark.
ASKING = frozenset(
    {
        "ask_field",
        "reask_field",
        "confirm_ambiguous",
        "confirm_value",
        "ask_correction_field",
        "show_recap",
        "offer_slots",
    }
)
# Lists need room (spec decision 5): the recap and the slot list may use the long cap.
LONG = frozenset({"show_recap", "offer_slots"})
# Closing a door on someone is never cheerful (spec 001 §7).
NO_EMOJI = frozenset({"close_disqualified"})


def expects_question(action: EngineAction) -> bool:
    return action.primary.type in ASKING


def length_cap(action: EngineAction, caps: LengthCaps, *, faq_answer: str | None) -> int:
    """The long cap for lists and for answering the candidate's own question (FR-12)."""
    answers_faq = faq_answer is not None and any(isinstance(p, AnswerFaq) for p in action.prefaces)
    return caps.long if action.primary.type in LONG or answers_faq else caps.default
