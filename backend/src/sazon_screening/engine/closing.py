"""Closing transitions (plan §4.1): opt-out, review, disqualification, recap and scheduling.

Every close records `drop_off_stage` (where the conversation ended) so 011 can report
funnel drop-off, and only uses ordered-unique helpers for flags and reasons.
"""

from datetime import date

from pydantic_core import to_jsonable_python

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AnswerFaq,
    ClosedAck,
    CloseDisqualified,
    CloseNeedsReview,
    CloseOptedOut,
    CloseQualifiedUnscheduled,
    CloseWaitlisted,
    HandoffToHuman,
    KeepInterview,
    OfferSlots,
    Preface,
    ShowRecap,
)
from sazon_screening.engine.apply import set_pending, validate_proposal
from sazon_screening.engine.inputs import CandidateTurn, Proposal
from sazon_screening.engine.rules import (
    DISQUALIFYING_FIELDS,
    HARD_RULE_FIELDS,
    hard_rule_failure,
    sync_license_requirement,
)
from sazon_screening.engine.state import (
    ConversationState,
    PostCloseCorrection,
    add_flag,
    add_reason,
)
from sazon_screening.engine.validators import Accepted
from sazon_screening.vocab import (
    DisqualificationReason,
    FieldName,
    FieldStatus,
    Flag,
    PendingKind,
    ReviewReason,
    Stage,
    Status,
)


def opt_out(s: ConversationState) -> CloseOptedOut:
    """Forget the candidate; keep only what we need to never contact them again (FR-11).

    The state is rebuilt from an allow-list rather than by clearing known fields, so
    anything candidate-derived (pending payloads, raw text, phone-prefix country,
    counters, slots, corrections) is dropped, including fields added in the future.
    Kept: where it ended, language, the consent answer, do-not-contact, config version
    and the date of the last turn (GDPR / LFPDPPP data minimisation).
    """
    purged = ConversationState(
        status=Status.opted_out,
        stage=s.stage,
        drop_off_stage=s.stage,
        language=s.language,
        consent=s.consent,
        flags=[Flag.do_not_contact],
        config_version=s.config_version,
        last_turn_on=s.last_turn_on,
        last_error=s.last_error,
    )
    for name in ConversationState.model_fields:
        setattr(s, name, getattr(purged, name))
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
    s.drop_off_stage = s.stage
    return CloseQualifiedUnscheduled()


def close_unbooked(s: ConversationState) -> KeepInterview | CloseQualifiedUnscheduled:
    """Scheduling ended without a new pick (none fits, re-asks used up, silence).

    Spec 010: if the candidate was moving an interview they had booked, that booking
    stays (`keep_interview`); otherwise they are qualified without an interview.
    """
    if s.selected_slot_id is not None:
        s.status = Status.interview_scheduled
        s.drop_off_stage = s.stage
        return KeepInterview(slot_id=s.selected_slot_id)
    return close_qualified_unscheduled(s)


def show_recap(s: ConversationState, cfg: EngineConfig) -> ShowRecap | CloseNeedsReview:
    """Show every value for confirmation (FR-25); too many rounds go to a recruiter."""
    s.recap_rounds += 1
    s.stage = Stage.recap
    if s.recap_rounds > cfg.thresholds.max_recap_rounds:
        return close_needs_review(s, ReviewReason.recap_loop)
    set_pending(s, PendingKind.recap)
    return recap_action(s)


def recap_action(s: ConversationState) -> ShowRecap:
    """The recap of what is stored now (a copy: the state keeps changing)."""
    return ShowRecap(
        profile=s.profile.model_copy(deep=True),
        start_date_approximate=Flag.start_date_approximate in s.flags,
    )


def close_waitlisted(s: ConversationState, area_id: str) -> CloseWaitlisted:
    """Qualified, but the area is fully staffed: a waitlist, never a rejection (spec 015)."""
    s.status = Status.waitlisted
    s.drop_off_stage = s.stage
    return CloseWaitlisted(area_id=area_id)


def enter_scheduling(
    s: ConversationState, t: CandidateTurn
) -> OfferSlots | CloseQualifiedUnscheduled | CloseWaitlisted | KeepInterview:
    """Offer the slots 010 sent with this turn (or the ones offered before) (FR-26).

    If the caller says the candidate's area is full (spec 015 FR-4), no slots are offered:
    the candidate is waitlisted. The caller decides "full" from live staffing; the engine
    only acts on the flag, and only here. A candidate who already has an interview
    (moving it, spec 010) is never waitlisted: their booking stands.
    """
    location = s.profile.location.value
    area_id = location.area_id if location is not None else None
    if t.context.zone_full and area_id is not None and s.selected_slot_id is None:
        return close_waitlisted(s, area_id)
    offered = t.context.offered_slots or s.offered_slot_ids
    slots = [slot for slot in offered if slot != s.selected_slot_id]  # moving: a new one
    if not slots:
        return close_unbooked(s)
    s.offered_slot_ids = slots
    set_pending(s, PendingKind.slot, FieldName.slot)
    moving = s.selected_slot_id is not None
    return OfferSlots(slot_ids=list(slots), reason="reschedule" if moving else None)


def handoff(s: ConversationState) -> HandoffToHuman:
    """The candidate asked for a person: pause screening until a recruiter acts (FR-12)."""
    add_flag(s, Flag.human_requested)
    add_reason(s, ReviewReason.human_requested)
    s.status = Status.needs_review
    s.drop_off_stage = s.stage
    return HandoffToHuman()


def on_closed(
    s: ConversationState,
    t: CandidateTurn,
    cfg: EngineConfig,
    today: date,
    prefaces: list[Preface],
) -> CloseNeedsReview | ClosedAck:
    """A message on a closed conversation never changes screening data (FR-15).

    Corrections to hard-rule fields are recorded next to the original, never applied, and
    a recruiter reviews them when they would change the outcome:
    - disqualified: only if every hard rule would now pass (AC-26b); "17 -> 16" stays
      disqualified, so nobody can talk their way past a knock-out rule;
    - booked / qualified / waitlisted: if a hard rule would now fail (AC-26c); "actually
      I'm 16" is never ignored, and never auto-disqualifies either.
    """
    if s.status is Status.disqualified and s.disqualification_reason is not None:
        fields = DISQUALIFYING_FIELDS[s.disqualification_reason]
        corrections = post_close_corrections(s, t, fields, cfg, today)
        _record(s, corrections)
        if corrections and _passes_hard_rules(s, corrections, cfg):
            return _review_correction(s)
    elif s.status in _QUALIFIED:
        corrections = post_close_corrections(s, t, HARD_RULE_FIELDS, cfg, today)
        if corrections and not _passes_hard_rules(s, corrections, cfg):
            _record(s, corrections)
            return _review_correction(s)
    if t.signals.faq_question:
        prefaces.append(AnswerFaq())
    return ClosedAck()


# Closed as qualified: a correction that would fail a hard rule goes to a recruiter.
_QUALIFIED = frozenset(
    {Status.interview_scheduled, Status.qualified_unscheduled, Status.waitlisted}
)

Correction = tuple[PostCloseCorrection, object]  # as stored (JSON-ready), validated value


def post_close_corrections(
    s: ConversationState,
    t: CandidateTurn,
    fields: frozenset[FieldName],
    cfg: EngineConfig,
    today: date,
) -> list[Correction]:
    """Valid values, different from the stored ones, proposed for `fields`."""
    corrections: list[Correction] = []
    latest: dict[str, Proposal] = {p.field: p for p in t.proposals}
    for name in sorted(fields):
        proposal = latest.get(name.value)
        if proposal is None:
            continue
        outcome = validate_proposal(s, proposal, cfg, today)
        original = getattr(s.profile, name.value).value
        if isinstance(outcome, Accepted) and outcome.value != original:
            record = PostCloseCorrection(
                field=name,
                original=to_jsonable_python(original),
                proposed=to_jsonable_python(outcome.value),
            )
            corrections.append((record, outcome.value))
    return corrections


def _record(s: ConversationState, corrections: list[Correction]) -> None:
    new = [record for record, _ in corrections if record not in s.post_close_corrections]
    s.post_close_corrections = [*s.post_close_corrections, *new]


def _review_correction(s: ConversationState) -> CloseNeedsReview:
    add_flag(s, Flag.post_close_correction)
    add_reason(s, ReviewReason.post_close_correction)
    s.status = Status.needs_review
    return CloseNeedsReview(reasons=list(s.needs_review_reasons))


def _passes_hard_rules(
    s: ConversationState, corrections: list[Correction], cfg: EngineConfig
) -> bool:
    """Would the candidate pass every hard rule with the corrected values?

    Every rule, not only the one that disqualified them: under-age AND no license,
    corrected only on age, still fails. Evaluated on a throwaway copy: the real profile
    keeps the original values.
    """
    trial = s.model_copy(deep=True)
    for record, value in corrections:
        slot = getattr(trial.profile, record.field.value)
        slot.value = value
        slot.status = FieldStatus.valid
    sync_license_requirement(trial, cfg)
    return hard_rule_failure(trial, cfg) is None
