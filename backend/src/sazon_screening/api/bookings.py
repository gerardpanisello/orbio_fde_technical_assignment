"""Storing interview bookings from the engine's `selected_slot_id` (spec 010 FR-3, FR-4).

The engine decides the flow; this module keeps the `interview_bookings` table in step
with it, inside the turn's own transaction, so the state and the booking always agree:
- the selected slot changed to a new id -> book a seat in it (moving the old booking,
  if any, to `rescheduled`);
- it changed to None (cancel, opt-out) -> the live booking is `cancelled`;
- unchanged -> nothing.

Capacity is enforced by the database (see `InterviewBooking`): we pick the first free
seat and insert it; a concurrent insert of the same seat fails on the unique index and
the caller retries the whole transaction, which then re-counts. A slot with no free
seat (or already started) raises `SlotUnavailable`: the caller tells the engine
(`slot_taken`) and stores that turn instead, so nobody is ever booked over capacity.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api import repo
from sazon_screening.api.models import InterviewBooking
from sazon_screening.api.slots import SlotProvider
from sazon_screening.scheduling import parse_slot_id


class SlotUnavailable(Exception):  # noqa: N818 - reads as the condition, like ConversationNotFound
    """The slot the candidate picked has no free seat (or is no longer in the future)."""

    def __init__(self, slot_id: str) -> None:
        super().__init__(slot_id)
        self.slot_id = slot_id


async def sync_booking(
    session: AsyncSession,
    slots: SlotProvider,
    conversation_id: str,
    *,
    before: str | None,
    after: str | None,
    now: datetime,
) -> InterviewBooking | None:
    """Apply the change of `selected_slot_id`; returns the new booking, if one was made."""
    if after == before:
        return None
    active = await repo.active_booking(session, conversation_id)
    if after is None:
        if active is not None:
            active.status = "cancelled"
            active.updated_at = now
        return None
    if active is not None and active.slot_id == after:
        return None  # already stored (e.g. a retried turn)
    booking = await _new_booking(session, slots, conversation_id, after, now)
    if active is not None:
        active.status = "rescheduled"
        active.updated_at = now
        await session.flush()  # free the old row from the one-live-booking index first
    repo.add(session, booking)
    await session.flush()  # the unique seat index fires here, inside the transaction
    return booking


async def _new_booking(
    session: AsyncSession, slots: SlotProvider, conversation_id: str, slot_id: str, now: datetime
) -> InterviewBooking:
    slot = parse_slot_id(slot_id)
    availability = await repo.get_availability(session, slot.city) if slot else None
    starts_at = slots.starts_at(slot) if slot else None
    if slot is None or availability is None or starts_at is None or starts_at <= now:
        raise SlotUnavailable(slot_id)
    taken = await repo.seats_taken(session, slot_id)
    seat = next((n for n in range(availability.capacity) if n not in taken), None)
    if seat is None:
        raise SlotUnavailable(slot_id)
    return InterviewBooking(
        conversation_id=conversation_id,
        slot_id=slot_id,
        city=slot.city,
        starts_at=starts_at,
        duration_min=availability.duration_min,
        place=availability.place,
        seat=seat,
        status="booked",
        created_at=now,
        updated_at=now,
    )
