"""Choosing the next question (plan §4.1): classify the attempt, re-ask or move on.

What to ask next is always `next_missing_field`, so out-of-order answers need no special
case. The re-ask policy (FR-23/24) lives here: at most `max_reasks` re-asks per field,
then the field is stored `unclear` and the conversation continues.
"""

from dataclasses import dataclass
from typing import Literal

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AskCorrectionField,
    AskField,
    ConfirmAmbiguous,
    ConfirmValue,
    OfferSlots,
    PrimaryAction,
    ReaskField,
)
from sazon_screening.engine.apply import Applied, answers_pending, set_pending
from sazon_screening.engine.closing import (
    close_needs_review,
    close_qualified_unscheduled,
    enter_scheduling,
    recap_action,
    show_recap,
)
from sazon_screening.engine.flow import next_missing_field
from sazon_screening.engine.inputs import CandidateTurn, CorrectionFieldProposal
from sazon_screening.engine.rules import review_reasons
from sazon_screening.engine.state import ConversationState, add_flag
from sazon_screening.vocab import (
    Availability,
    FieldName,
    FieldStatus,
    Flag,
    PendingKind,
    ReaskReason,
    ScheduleSlot,
    Stage,
    VehicleType,
)


@dataclass(frozen=True)
class Attempt:
    """How this turn counts for the field we asked about (FR-23)."""

    kind: Literal["answered", "failed", "neutral"]
    reason: ReaskReason = ReaskReason.unclear
    options: tuple[str, ...] = ()


def classify_attempt(
    s: ConversationState, turn: CandidateTurn, applied: Applied, *, neutral: bool
) -> Attempt:
    """answered / failed / neutral for the pending field (FR-23, AC-20).

    Only a rejected answer for the asked field, or an empty turn, consumes a re-ask.
    FAQ, off-topic, a language switch or other fields filled are neutral.
    """
    if applied.pending_outcome is not None:
        outcome = applied.pending_outcome
        return Attempt("failed", outcome.reason, outcome.options)
    if any(answers_pending(name, s.pending.field) for name in applied.accepted):
        return Attempt("answered")
    if not turn.proposals and not neutral:
        return Attempt("failed", _empty_turn_reason(s))
    return Attempt("neutral")


def _empty_turn_reason(s: ConversationState) -> ReaskReason:
    if s.pending.field is FieldName.consent:
        return ReaskReason.consent_required
    return ReaskReason.unclear


def on_field_answer(s: ConversationState, attempt: Attempt, cfg: EngineConfig) -> PrimaryAction:
    """Handler for `ask`, `confirm_value` and `confirm_ambiguous`."""
    name = s.pending.field
    if attempt.kind == "failed" and name is not None:
        options = attempt.options or default_options(name, s, cfg)
        reask = reask_or_exhaust(s, name, attempt.reason, options, cfg)
        if reask is not None:
            return reask
    if attempt.kind == "neutral" and s.pending.kind is not PendingKind.ask:
        return pending_action(s)  # e.g. a FAQ while confirming: ask the same question again
    return next_action(s, cfg)


def next_action(s: ConversationState, cfg: EngineConfig) -> PrimaryAction:
    """Ask the first missing field; when none is left, review or recap."""
    if (field_name := next_missing_field(s, cfg)) is not None:
        set_pending(s, PendingKind.ask, field_name)
        return AskField(field=field_name)
    if reasons := review_reasons(s.profile, cfg):  # hard field unclear: never disqualify
        s.stage = Stage.recap
        return close_needs_review(s, *reasons)
    return show_recap(s, cfg)


def on_recap(
    s: ConversationState, t: CandidateTurn, applied: Applied, attempt: Attempt, cfg: EngineConfig
) -> PrimaryAction:
    """Handler for `recap` and `correction_field` (FR-25)."""
    if applied.accepted:  # a correction: ask what became missing, or show the recap again
        return next_action(s, cfg)
    if (target := applied.correction_target) is not None:  # "la zona está mal": ask it
        set_pending(s, PendingKind.ask, target)
        return AskField(field=target)
    if applied.confirmation is True:
        return enter_scheduling(s, t)
    if applied.confirmation is False and s.pending.kind is PendingKind.recap:
        set_pending(s, PendingKind.correction_field)
        return AskCorrectionField()
    if attempt.kind == "neutral" and not _says_anything(t):
        return pending_action(s)  # e.g. a FAQ: same question again, not a new round
    return show_recap(s, cfg)


def _says_anything(t: CandidateTurn) -> bool:
    """Proposals other than an ignored field name (e.g. "consent is wrong") at the recap."""
    return any(not isinstance(p, CorrectionFieldProposal) for p in t.proposals)


def on_slot_answer(
    s: ConversationState, t: CandidateTurn, applied: Applied, attempt: Attempt, cfg: EngineConfig
) -> PrimaryAction:
    """A candidate message while slots are offered (the pick itself is a `slot_selected` event)."""
    if applied.accepted:  # plan OQ-7: a correction re-opens the recap, then slots again
        return next_action(s, cfg)
    if attempt.kind == "failed":
        offered = tuple(s.offered_slot_ids)
        reask = reask_or_exhaust(s, FieldName.slot, attempt.reason, offered, cfg)
        return reask or close_qualified_unscheduled(s)
    return pending_action(s)


def reask_or_exhaust(
    s: ConversationState,
    name: FieldName,
    reason: ReaskReason,
    options: tuple[str, ...],
    cfg: EngineConfig,
) -> PrimaryAction | None:
    """Re-ask up to `max_reasks` times (FR-23); after that give up on the field (FR-24).

    Returns None when the field is exhausted: the caller moves on with `next_action`.
    """
    limit = cfg.thresholds.max_reasks
    used = s.reasks.get(name, 0) + 1
    if name is FieldName.consent:
        # Plan OQ-1: never assume consent and never close; silence (008) ends it.
        s.reasks[name] = min(used, limit + 1)
        return ReaskField(field=name, reason=ReaskReason.consent_required)
    s.reasks[name] = used
    if used > limit:
        exhaust(s, name)
        return None
    if s.pending.kind is PendingKind.confirm_value:
        set_pending(s, PendingKind.ask, name)  # "no, not 45": ask for the years again
    return ReaskField(field=name, reason=reason, options=list(options))


def exhaust(s: ConversationState, name: FieldName) -> None:
    """Out of re-asks: store `unclear` and move on (never disqualify on ambiguity).

    A field that is already valid was being corrected from the recap (AC-40): a failed
    correction keeps the old value, so valid data is never downgraded to `unclear`. The
    flag tells the recruiter, and `next_action` goes back to the recap.
    """
    if name is FieldName.slot:
        return  # not a screening field; the caller closes as qualified_unscheduled
    stored = getattr(s.profile, (FieldName.location if name is FieldName.zone else name).value)
    if stored.status is FieldStatus.valid and stored.value is not None:
        add_flag(s, Flag.correction_unclear)
        return
    if name is FieldName.full_name:
        add_flag(s, Flag.name_unclear)  # required but not qualifying (FR-16)
    if name is FieldName.zone:
        name = FieldName.location  # the partial city is kept for the recruiter
    getattr(s.profile, name.value).status = FieldStatus.unclear


def repeat_pending(s: ConversationState, reason: ReaskReason, cfg: EngineConfig) -> PrimaryAction:
    """Ask the pending question again without using a re-ask (e.g. extraction failed)."""
    name = s.pending.field
    if s.pending.kind is PendingKind.ask and name is not None:
        return ReaskField(field=name, reason=reason, options=list(default_options(name, s, cfg)))
    return pending_action(s)


def pending_action(s: ConversationState) -> PrimaryAction:
    """The action that asks what `s.pending` waits for."""
    pending = s.pending
    name = pending.field or FieldName.consent
    if pending.kind is PendingKind.confirm_value and pending.candidate_value is not None:
        return ConfirmValue(field=name, value=pending.candidate_value)
    if pending.kind is PendingKind.confirm_ambiguous:
        return ConfirmAmbiguous(field=name, options=list(pending.options))
    if pending.kind is PendingKind.recap:
        return recap_action(s)
    if pending.kind is PendingKind.correction_field:
        return AskCorrectionField()
    if pending.kind is PendingKind.slot:
        return OfferSlots(slot_ids=list(s.offered_slot_ids))
    return AskField(field=name)


def default_options(name: FieldName, s: ConversationState, cfg: EngineConfig) -> tuple[str, ...]:
    """Choices to offer when re-asking a closed question (IDs; 003 phrases them)."""
    index = cfg.location_index
    location = s.profile.location.value
    if s.pending.kind is PendingKind.confirm_ambiguous:
        return tuple(ref.id for ref in s.pending.options)
    match name:
        case FieldName.vehicle_type:
            return tuple(option.value for option in VehicleType)
        case FieldName.availability:
            return tuple(option.value for option in Availability)
        case FieldName.schedule:
            return tuple(option.value for option in ScheduleSlot)
        case FieldName.location:
            return index.served_city_ids()
        case FieldName.zone if location is not None and location.city is not None:
            return tuple(ref.id for ref in index.zones_by_city.get(location.city, ()))
    return ()  # slot re-asks pass the offered ids explicitly
