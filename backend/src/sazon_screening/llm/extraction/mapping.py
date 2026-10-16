"""Model output -> engine input (FR-6..9, plan §3.6 "Mapping").

Each field builder (builders.py) runs on its own, so one bad value never sinks the
others (spec decision 4). A value that fails is dropped and listed in the trace; if it
answered the question we asked, the engine gets UNCLEAR for that field instead, so the
normal re-ask policy applies. The engine then validates everything again: nothing here
can approve or reject a candidate (ADR 0002).
"""

import re

from pydantic import BaseModel, ConfigDict, TypeAdapter

from sazon_screening.engine import (
    CandidateTurn,
    NoSlotFits,
    Proposal,
    Signals,
    SlotSelected,
    TurnContext,
)
from sazon_screening.llm.extraction.builders import BUILDERS, DropError
from sazon_screening.llm.extraction.pending import PendingView
from sazon_screening.llm.extraction.schema import ExtractionOutput, Sentiment
from sazon_screening.vocab import FieldName, Language, PendingKind

_PROPOSAL = TypeAdapter[Proposal](Proposal)


class DroppedProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    reason: str  # e.g. "empty_value", "invalid_date", "choice_not_offered"


class Mapped(BaseModel):
    """The engine input for one message, plus what only the trace needs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_input: CandidateTurn | SlotSelected | NoSlotFits
    dropped: list[DroppedProposal] = []
    faq_question: str | None = None  # the text goes to the trace (009); the engine gets a flag
    sentiment: Sentiment = "neutral"  # trace only: a hook for the summary and 007


def to_turn_input(
    out: ExtractionOutput,
    pending: PendingView,
    context: TurnContext,
    *,
    text: str | None = None,
) -> Mapped:
    """`context` comes from the caller (phone prefix, offered slots), never from the model.

    `text` is the candidate's message: when it has no real language content (a name, a
    number, a place, a button), the language signal is dropped and the engine keeps the
    conversation's language, whatever the model said (eval 2026-10-12).
    """
    proposals, dropped = field_proposals(out, pending)
    found = signals(out)
    if (
        text is not None
        and found.language is not None
        and not has_language_content(text, out, pending)
    ):
        found = found.model_copy(update={"language": None})
    turn = CandidateTurn(proposals=proposals, signals=found, context=context)
    slot_pick = _slot_pick(out, pending, turn, dropped)
    faq = out.faq_question.strip() if out.faq_question else None
    return Mapped(
        turn_input=slot_pick or turn,
        dropped=dropped,
        faq_question=faq or None,
        sentiment=out.sentiment,
    )


def field_proposals(
    out: ExtractionOutput, pending: PendingView
) -> tuple[list[Proposal], list[DroppedProposal]]:
    """At most one proposal per field; UNCLEAR only where the model said so (or we asked)."""
    proposals: dict[str, Proposal] = {}
    dropped: list[DroppedProposal] = []
    for key, build in BUILDERS:
        try:
            proposal = build(out, pending)
        except ValueError as error:  # DropError, or pydantic's ValidationError
            reason = error.reason if isinstance(error, DropError) else "invalid_value"
            dropped.append(DroppedProposal(field=key, reason=reason))
            if answers_pending(key, pending):
                proposals[key] = unclear(key)
            continue
        if proposal is not None:
            proposals[key] = proposal
    for key in out.unclear_fields:
        proposals.setdefault(key, unclear(key))  # a readable value always wins
    return [proposals[key] for key, _ in BUILDERS if key in proposals], dropped


def answers_pending(key: str, pending: PendingView) -> bool:
    """Is this the question we asked? A location answers a zone question too."""
    if key == "choice":
        return pending.kind is PendingKind.confirm_ambiguous
    if pending.field is None:
        return False
    return key == pending.field.value or (key == "location" and pending.field is FieldName.zone)


def unclear(key: str) -> Proposal:
    return _PROPOSAL.validate_python({"field": key, "value": {"kind": "unclear"}})


def signals(out: ExtractionOutput) -> Signals:
    """Copied 1:1. The FAQ text and the sentiment stay in the trace, not in the engine."""
    return Signals(
        opt_out=out.opt_out,
        wants_human=out.wants_human,
        correction=out.is_correction,
        faq_question=bool(out.faq_question and out.faq_question.strip()),
        off_topic=out.off_topic,
        abuse=out.abuse,
        language=Language(out.language) if out.language else None,
        reschedule_interview=out.reschedule_interview,
        cancel_interview=out.cancel_interview,
    )


_WORD = re.compile(r"[^\W\d_]+")


def has_language_content(text: str, out: ExtractionOutput, pending: PendingView) -> bool:
    """False when every word is a name, a place, an app or a button label: those read the
    same in any language, so they must not switch it. Digits, emoji and punctuation
    are not words.
    """
    words = _words(text)
    if not words:
        return False
    neutral = [out.full_name, out.location_city, out.location_zone, *(out.platforms or [])]
    neutral_words = {word for value in neutral if value for word in _words(value)}
    neutral_words |= {word for option in pending.options for word in _words(option.label)}
    return not set(words) <= neutral_words


def _words(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


def _slot_pick(
    out: ExtractionOutput,
    pending: PendingView,
    turn: CandidateTurn,
    dropped: list[DroppedProposal],
) -> SlotSelected | NoSlotFits | None:
    """A clean slot answer becomes the engine's slot event (FR-6g, plan §3.6 rule 6).

    Anything else in the same message (a correction, an opt-out...) wins, and the pick
    is asked again (plan OQ-7). An id we did not offer leaves an empty turn, which the
    engine counts as a failed slot attempt.
    """
    if pending.kind is not PendingKind.slot:
        return None
    pick: SlotSelected | NoSlotFits
    if out.no_option_fits:
        pick = NoSlotFits()
    elif out.chosen_option_id is None:
        return None
    elif out.chosen_option_id not in pending.option_ids():
        dropped.append(DroppedProposal(field="slot", reason="slot_not_offered"))
        return None
    else:
        pick = SlotSelected(slot_id=out.chosen_option_id)
    if turn.proposals or turn.signals.model_copy(update={"language": None}) != Signals():
        dropped.append(DroppedProposal(field="slot", reason="slot_pick_with_other_content"))
        return None
    return pick
