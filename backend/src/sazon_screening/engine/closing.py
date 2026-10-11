"""Closing transitions (plan §4.1): opt-out, review, disqualification, recap and scheduling.

Every close records `drop_off_stage` (where the conversation ended) so 011 can report
funnel drop-off, and only uses ordered-unique helpers for flags and reasons.
"""

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    CloseDisqualified,
    CloseNeedsReview,
    CloseOptedOut,
    CloseQualifiedUnscheduled,
    OfferSlots,
    ShowRecap,
)
from sazon_screening.engine.apply import set_pending
from sazon_screening.engine.enums import (
    DisqualificationReason,
    FieldName,
    Flag,
    PendingKind,
    ReviewReason,
    Stage,
    Status,
)
from sazon_screening.engine.inputs import CandidateTurn
from sazon_screening.engine.state import ConversationState, Profile, add_flag, add_reason


def opt_out(s: ConversationState) -> CloseOptedOut:
    """Purge every screening value; keep only what we need to never contact them again.

    FR-11 (GDPR / LFPDPPP data minimisation): status, drop-off stage, language and the
    do-not-contact flag survive. The consent answer is not screening data and is kept.
    """
    s.drop_off_stage = s.stage
    s.profile = Profile()
    s.flags = [Flag.do_not_contact]
    s.needs_review_reasons = []
    s.disqualification_reason = None
    s.post_close_corrections = []
    s.offered_slot_ids = []
    s.selected_slot_id = None
    s.status = Status.opted_out
    return CloseOptedOut()


def close_needs_review(
    s: ConversationState, *reasons: ReviewReason, flag: Flag | None = None
) -> CloseNeedsReview:
    """Hand the candidate to a recruiter with the reasons why (never a rejection)."""
    for reason in reasons:
        add_reason(s, reason)
    if flag is not None:
        add_flag(s, flag)
    s.status = Status.needs_review
    s.drop_off_stage = s.stage
    return CloseNeedsReview(reasons=list(s.needs_review_reasons))


def close_disqualified(s: ConversationState, reason: DisqualificationReason) -> CloseDisqualified:
    """A hard rule failed on a clear, stored value. All collected values are kept (AC-6)."""
    s.status = Status.disqualified
    s.disqualification_reason = reason
    s.drop_off_stage = s.stage
    return CloseDisqualified(reason=reason)


def close_qualified_unscheduled(s: ConversationState) -> CloseQualifiedUnscheduled:
    """Qualified, but no interview booked: a recruiter books it (Spec 001 §6)."""
    s.status = Status.qualified_unscheduled
    return CloseQualifiedUnscheduled()


def show_recap(s: ConversationState, cfg: EngineConfig) -> ShowRecap | CloseNeedsReview:
    """Show every value for confirmation (FR-25); too many rounds go to a recruiter."""
    s.recap_rounds += 1
    s.stage = Stage.recap
    if s.recap_rounds > cfg.thresholds.max_recap_rounds:
        return close_needs_review(s, ReviewReason.recap_loop)
    set_pending(s, PendingKind.recap)
    return ShowRecap(profile=s.profile.model_copy(deep=True))  # the state keeps changing


def enter_scheduling(
    s: ConversationState, t: CandidateTurn
) -> OfferSlots | CloseQualifiedUnscheduled:
    """Offer the slots 010 sent with this turn (or the ones offered before) (FR-26)."""
    slots = t.context.offered_slots or s.offered_slot_ids
    if not slots:
        return close_qualified_unscheduled(s)
    s.offered_slot_ids = list(slots)
    set_pending(s, PendingKind.slot, FieldName.slot)
    return OfferSlots(slot_ids=list(slots))
