"""Moving and cancelling a booked interview by chat (spec 010 FR-3/FR-4, ADR 0005 amendment).

The engine stays pure: which slots are still open is the caller's job (it sends only
bookable ids, in `TurnContext.offered_slots` or in the `slot_taken` event), and the
booking itself is stored by the caller from `selected_slot_id`. Here only the flow:

- `reschedule_interview` on a booked conversation -> back to scheduling with fresh slots;
  the booked slot stays `selected_slot_id` until a new one is picked, so "none fits",
  running out of re-asks or going silent keeps it (`keep_interview`). On
  `qualified_unscheduled` (no interview, e.g. after a cancel) it offers slots again: a
  qualified candidate asking for an interview should get one.
- `cancel_interview` on a booked conversation (or one moving its booking) -> the booking
  is released: `qualified_unscheduled`, flag `interview_cancelled`. While choosing a
  first slot, "cancel" means none fits. Anywhere else it changes nothing.
- `slot_taken`: the pick filled up before it was stored -> offer the slots still open.
"""

from sazon_screening.engine.actions import (
    ClosedAck,
    CloseInterviewCancelled,
    CloseQualifiedUnscheduled,
    KeepInterview,
    OfferSlots,
    PrimaryAction,
)
from sazon_screening.engine.apply import set_pending
from sazon_screening.engine.closing import close_qualified_unscheduled, close_unbooked
from sazon_screening.engine.collect import pending_action
from sazon_screening.engine.inputs import CandidateTurn, SlotTaken
from sazon_screening.engine.state import ConversationState, add_flag
from sazon_screening.vocab import FieldName, Flag, PendingKind, Stage, Status


def on_interview_request(s: ConversationState, t: CandidateTurn) -> PrimaryAction | None:
    """The reply to a reschedule or cancel request, or None when it does not apply."""
    signals = t.signals
    if signals.cancel_interview:
        if s.selected_slot_id is not None and (
            s.status is Status.interview_scheduled or _choosing(s)
        ):
            return cancel_interview(s)
        if _choosing(s):  # "cancela" while choosing a first slot: nothing fits
            return close_qualified_unscheduled(s)
        return None
    if signals.reschedule_interview and (
        s.status in (Status.interview_scheduled, Status.qualified_unscheduled) or _choosing(s)
    ):
        return offer_new_slots(s, t)
    return None


def _choosing(s: ConversationState) -> bool:
    return s.status is Status.in_progress and s.pending.kind is PendingKind.slot


def offer_new_slots(
    s: ConversationState, t: CandidateTurn
) -> OfferSlots | KeepInterview | CloseQualifiedUnscheduled:
    """Slots other than the booked one; none open -> keep the booking (or stay unscheduled)."""
    fresh = [slot for slot in t.context.offered_slots or [] if slot != s.selected_slot_id]
    if not fresh:
        return close_unbooked(s)
    s.status = Status.in_progress
    s.stage = Stage.scheduling
    s.drop_off_stage = None
    s.offered_slot_ids = fresh
    # A new offer gets its own re-asks (FR-23 counts per question asked).
    s.reasks = {name: n for name, n in s.reasks.items() if name is not FieldName.slot}
    set_pending(s, PendingKind.slot, FieldName.slot)
    moving = s.selected_slot_id is not None
    return OfferSlots(slot_ids=fresh, reason="reschedule" if moving else None)


def cancel_interview(s: ConversationState) -> CloseInterviewCancelled:
    """Release the booking: still qualified, no interview; a recruiter can see why."""
    s.selected_slot_id = None
    s.status = Status.qualified_unscheduled
    s.stage = Stage.scheduling
    s.drop_off_stage = s.stage
    add_flag(s, Flag.interview_cancelled)
    return CloseInterviewCancelled()


def on_slot_taken(s: ConversationState, event: SlotTaken) -> PrimaryAction:
    """FR-3: the pick filled up meanwhile. Offer what is still open, never the full one."""
    if s.status is not Status.in_progress:
        return ClosedAck()
    if s.pending.kind is not PendingKind.slot:
        return pending_action(s)  # a stale event: ask what we were asking
    taken = {event.slot_id, s.selected_slot_id}
    fresh = [slot for slot in event.slot_ids if slot not in taken]
    if not fresh:
        return close_unbooked(s)
    s.offered_slot_ids = fresh
    set_pending(s, PendingKind.slot, FieldName.slot)
    return OfferSlots(slot_ids=fresh, reason="slot_taken")
