"""Closing transitions (plan §4.1): opt-out, review, disqualification, recap and scheduling.

Every close records `drop_off_stage` (where the conversation ended) so 011 can report
funnel drop-off, and only uses ordered-unique helpers for flags and reasons.
"""

from sazon_screening.engine.actions import CloseDisqualified, CloseNeedsReview, CloseOptedOut
from sazon_screening.engine.enums import DisqualificationReason, Flag, ReviewReason, Status
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
