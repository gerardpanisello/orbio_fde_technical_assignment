"""Queries: the only module with SQL. Plain functions over an `AsyncSession`.

The caller owns the transaction (`async with sessions.begin()`), so one turn's writes
(state, both messages) commit together or not at all.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from sqlalchemy import ColumnElement, CursorResult, Integer, Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api.models import (
    SEAT_HOLDING,
    Conversation,
    DoNotContact,
    InboundSeen,
    InterviewAvailability,
    InterviewBooking,
    Message,
    RecruiterAction,
    SummaryRow,
    ZoneStaffing,
)

REDACTED = "[deleted: the candidate opted out]"

# --- conversations ---------------------------------------------------------------------


async def get_conversation(session: AsyncSession, conversation_id: str) -> Conversation | None:
    return await session.get(Conversation, conversation_id)


def add(
    session: AsyncSession,
    row: Conversation
    | Message
    | RecruiterAction
    | ZoneStaffing
    | InboundSeen
    | InterviewAvailability
    | InterviewBooking,
) -> None:
    session.add(row)


# --- WhatsApp (spec 016) ---------------------------------------------------------------


async def latest_conversation_for_phone(session: AsyncSession, phone: str) -> Conversation | None:
    """The candidate's most recent conversation on this number (closed ones included: the
    engine answers those with its closed acknowledgement)."""
    query = (
        select(Conversation)
        .where(Conversation.phone == phone)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(1)
    )
    return (await session.scalars(query)).first()


async def is_do_not_contact(session: AsyncSession, phone_hash: str) -> bool:
    return await session.get(DoNotContact, phone_hash) is not None


async def add_do_not_contact(session: AsyncSession, phone_hash: str, at: datetime) -> None:
    await session.merge(DoNotContact(phone_hash=phone_hash, created_at=at))


# --- re-engagement (spec 008) ----------------------------------------------------------


async def waiting_conversations(session: AsyncSession, status: str) -> Sequence[Conversation]:
    """Conversations the scheduler looks at (`in_progress`); the policy decides the rest."""
    return (await session.scalars(select(Conversation).where(Conversation.status == status))).all()


async def claim_follow_up(
    session: AsyncSession,
    conversation_id: str,
    *,
    expected_sent: int,
    expected_last_candidate_at: datetime | None,
    at: datetime,
) -> bool:
    """Compare-and-set: count one more reminder only if nothing changed since we read the
    row (no reminder sent, no candidate message). False: someone else got there first, so
    a step is never sent twice, even by two processes (008 FR-7)."""
    last = Conversation.last_candidate_at
    query = (
        update(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.follow_ups_sent == expected_sent,
            last.is_(None)
            if expected_last_candidate_at is None
            else last == expected_last_candidate_at,
        )
        .values(follow_ups_sent=expected_sent + 1, last_follow_up_at=at)
    )
    result = cast(CursorResult[Any], await session.execute(query))
    return result.rowcount == 1


async def follow_up_steps(session: AsyncSession) -> list[tuple[str, int]]:
    """(conversation id, step) of every reminder sent, for analytics."""
    query = select(Message.conversation_id, Message.follow_up_step).where(
        Message.kind == "follow_up"
    )
    return [(cid, step or 0) for cid, step in await session.execute(query)]


async def reactivation_steps(session: AsyncSession) -> list[int]:
    """`reactivated_after_step` of every conversation whose candidate came back."""
    query = select(Conversation.reactivated_after_step).where(
        Conversation.reactivated_after_step.is_not(None)
    )
    return [step for step in (await session.scalars(query)).all() if step is not None]


# --- messages --------------------------------------------------------------------------


async def list_messages(session: AsyncSession, conversation_id: str) -> Sequence[Message]:
    query = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    return (await session.scalars(query)).all()


async def redact_messages(session: AsyncSession, conversation_id: str) -> None:
    """Opt-out (002 FR-11): the transcript and traces hold PII, so blank them out."""
    await session.execute(
        update(Message)
        .where(Message.conversation_id == conversation_id)
        .values(text=REDACTED, quick_replies_json=[], trace_json=None)
    )


# --- summaries -------------------------------------------------------------------------


async def get_summary(
    session: AsyncSession, conversation_id: str, language: str
) -> SummaryRow | None:
    return await session.get(SummaryRow, (conversation_id, language))


async def save_summary(session: AsyncSession, row: SummaryRow) -> None:
    await session.merge(row)  # insert or replace (same conversation + language)


async def delete_summaries(session: AsyncSession, conversation_id: str) -> None:
    await session.execute(delete(SummaryRow).where(SummaryRow.conversation_id == conversation_id))


# --- recruiter actions -----------------------------------------------------------------


async def list_actions(session: AsyncSession, conversation_id: str) -> Sequence[RecruiterAction]:
    query = (
        select(RecruiterAction)
        .where(RecruiterAction.conversation_id == conversation_id)
        .order_by(RecruiterAction.id)
    )
    return (await session.scalars(query)).all()


async def has_action(session: AsyncSession, conversation_id: str, action: str) -> bool:
    query = select(func.count()).where(
        RecruiterAction.conversation_id == conversation_id, RecruiterAction.action == action
    )
    return bool(await session.scalar(query))


# --- zone staffing (spec 015) ----------------------------------------------------------


async def list_staffing(session: AsyncSession) -> Sequence[ZoneStaffing]:
    return (await session.scalars(select(ZoneStaffing))).all()


async def get_staffing(session: AsyncSession, area_id: str) -> ZoneStaffing | None:
    return await session.get(ZoneStaffing, area_id)


async def staffing_is_empty(session: AsyncSession) -> bool:
    return not await session.scalar(select(func.count()).select_from(ZoneStaffing))


async def count_by_area_and_status(
    session: AsyncSession, statuses: Sequence[str]
) -> list[tuple[str | None, str | None, str, int]]:
    """(city, zone, status, count) for conversations in `statuses`: the pipeline per area."""
    columns = (Conversation.city, Conversation.zone, Conversation.status)
    query = select(*columns, func.count()).where(Conversation.status.in_(statuses))
    rows = await session.execute(query.group_by(*columns))
    return [(city, zone, status, count) for city, zone, status, count in rows]


# --- candidate list (FR-6, FR-10) ------------------------------------------------------

SortKey = Literal["score", "-score", "updated", "-updated", "created", "-created"]


@dataclass(frozen=True)
class CandidateFilters:
    status: str | None = None
    country: str | None = None
    city: str | None = None
    bucket: str | None = None
    recruiter_status: str | None = None
    channel: str | None = None  # spec 016
    q: str | None = None  # part of the name, any case
    sort: SortKey = "-updated"


async def list_candidates(
    session: AsyncSession, filters: CandidateFilters
) -> Sequence[Conversation]:
    query = select(Conversation)
    for column, value in (
        (Conversation.status, filters.status),
        (Conversation.country, filters.country),
        (Conversation.city, filters.city),
        (Conversation.bucket, filters.bucket),
        (Conversation.recruiter_status, filters.recruiter_status),
        (Conversation.channel, filters.channel),
    ):
        if value:
            query = query.where(column == value)
    if filters.q:
        query = query.where(func.lower(Conversation.full_name).contains(filters.q.lower()))
    return (await session.scalars(_sorted(query, filters.sort))).all()


def _sorted(query: Select[Conversation], sort: SortKey) -> Select[Conversation]:
    column = {
        "score": Conversation.score,
        "updated": Conversation.updated_at,
        "created": Conversation.created_at,
    }[sort.lstrip("-")]
    order = column.desc() if sort.startswith("-") else column.asc()
    # Unscored candidates always go last; the id breaks ties so the order is stable.
    return query.order_by(column.is_(None), order, Conversation.id)


# --- analytics (FR-11) -----------------------------------------------------------------


async def count_by(
    session: AsyncSession, column: Any, *where: ColumnElement[bool]
) -> dict[str | None, int]:
    query = select(column, func.count()).where(*where).group_by(column)
    return dict((await session.execute(query)).all())  # Result itself has .keys(): not dict()-able


async def count_by_country_and_status(session: AsyncSession) -> list[tuple[str | None, str, int]]:
    query = select(Conversation.country, Conversation.status, func.count()).group_by(
        Conversation.country, Conversation.status
    )
    return [(country, status, count) for country, status, count in await session.execute(query)]


async def count_by_channel_and_status(session: AsyncSession) -> list[tuple[str, str, int]]:
    query = select(Conversation.channel, Conversation.status, func.count()).group_by(
        Conversation.channel, Conversation.status
    )
    return [(channel, status, count) for channel, status, count in await session.execute(query)]


async def durations(
    session: AsyncSession, statuses: Sequence[str]
) -> list[tuple[datetime, datetime]]:
    query = select(Conversation.created_at, Conversation.updated_at).where(
        Conversation.status.in_(statuses)
    )
    return [(created, updated) for created, updated in await session.execute(query)]


async def faq_traces(session: AsyncSession) -> list[dict[str, Any]]:
    """The FAQ part of every agent turn that had a question (spec 009), oldest first."""
    query = (
        select(Message.trace_json["faq"])
        .where(Message.role == "agent", Message.trace_json.is_not(None))
        .order_by(Message.id)
    )
    return [faq for faq in (await session.scalars(query)).all() if isinstance(faq, dict)]


async def turn_totals(session: AsyncSession) -> tuple[int, int, float]:
    """Agent replies: (turns, fallbacks, total cost in USD incl. summaries)."""
    fallbacks = func.coalesce(func.sum(Message.fallback.cast(Integer)), 0)
    query = select(func.count(), fallbacks).where(Message.role == "agent")
    turn_count, fallback_count = (await session.execute(query)).one()
    cost = await session.scalar(select(func.coalesce(func.sum(Message.cost_usd), 0.0)))
    summary_cost = await session.scalar(select(func.coalesce(func.sum(SummaryRow.cost_usd), 0.0)))
    return int(turn_count), int(fallback_count), float(cost or 0) + float(summary_cost or 0)


# --- interviews (spec 010) -------------------------------------------------------------


async def list_availability(session: AsyncSession) -> Sequence[InterviewAvailability]:
    return (await session.scalars(select(InterviewAvailability))).all()


async def get_availability(session: AsyncSession, city: str) -> InterviewAvailability | None:
    return await session.get(InterviewAvailability, city)


async def seats_taken_by_slot(
    session: AsyncSession, city: str, *, since: datetime
) -> dict[str, int]:
    """slot id -> seats held, for the city's slots starting after `since`."""
    query = (
        select(InterviewBooking.slot_id, func.count())
        .where(
            InterviewBooking.city == city,
            InterviewBooking.status.in_(SEAT_HOLDING),
            InterviewBooking.starts_at > since,
        )
        .group_by(InterviewBooking.slot_id)
    )
    return dict((await session.execute(query)).all())  # Result itself is not dict()-able


async def seats_taken(session: AsyncSession, slot_id: str) -> set[int]:
    query = select(InterviewBooking.seat).where(
        InterviewBooking.slot_id == slot_id, InterviewBooking.status.in_(SEAT_HOLDING)
    )
    return set((await session.scalars(query)).all())


async def active_booking(session: AsyncSession, conversation_id: str) -> InterviewBooking | None:
    """The candidate's live booking (status `booked`), if any."""
    query = select(InterviewBooking).where(
        InterviewBooking.conversation_id == conversation_id, InterviewBooking.status == "booked"
    )
    return (await session.scalars(query)).first()


async def bookings_for(session: AsyncSession, conversation_id: str) -> Sequence[InterviewBooking]:
    """Every booking of a conversation, oldest first (the reschedule / cancel history)."""
    query = (
        select(InterviewBooking)
        .where(InterviewBooking.conversation_id == conversation_id)
        .order_by(InterviewBooking.id)
    )
    return (await session.scalars(query)).all()


async def get_booking(session: AsyncSession, booking_id: int) -> InterviewBooking | None:
    return await session.get(InterviewBooking, booking_id)


async def bookings_between(
    session: AsyncSession, city: str, start: datetime, end: datetime
) -> Sequence[InterviewBooking]:
    """Seat-holding bookings of a city with `start <= starts_at < end` (the week view)."""
    query = (
        select(InterviewBooking)
        .where(
            InterviewBooking.city == city,
            InterviewBooking.status.in_(SEAT_HOLDING),
            InterviewBooking.starts_at >= start,
            InterviewBooking.starts_at < end,
        )
        .order_by(InterviewBooking.starts_at, InterviewBooking.seat)
    )
    return (await session.scalars(query)).all()


async def reminder_candidates(
    session: AsyncSession, *, after: datetime, before: datetime
) -> Sequence[InterviewBooking]:
    """Booked interviews starting in (after, before] whose reminder is not sent yet."""
    query = select(InterviewBooking).where(
        InterviewBooking.status == "booked",
        InterviewBooking.reminder_sent_at.is_(None),
        InterviewBooking.starts_at > after,
        InterviewBooking.starts_at <= before,
    )
    return (await session.scalars(query)).all()


async def claim_reminder(session: AsyncSession, booking_id: int, at: datetime) -> bool:
    """Compare-and-set (FR-6): mark the reminder sent only if nobody did and the booking is
    still live. False: already sent (or moved / cancelled), so it is never sent twice."""
    query = (
        update(InterviewBooking)
        .where(
            InterviewBooking.id == booking_id,
            InterviewBooking.status == "booked",
            InterviewBooking.reminder_sent_at.is_(None),
        )
        .values(reminder_sent_at=at)
    )
    result = cast(CursorResult[Any], await session.execute(query))
    return result.rowcount == 1


async def names_of(session: AsyncSession, conversation_ids: set[str]) -> dict[str, str | None]:
    """conversation id -> candidate name, for the week view."""
    if not conversation_ids:
        return {}
    query = select(Conversation.id, Conversation.full_name).where(
        Conversation.id.in_(conversation_ids)
    )
    return dict((await session.execute(query)).all())  # Result itself is not dict()-able


async def booking_counts(session: AsyncSession) -> dict[str, int]:
    """status -> bookings (analytics)."""
    query = select(InterviewBooking.status, func.count()).group_by(InterviewBooking.status)
    return dict((await session.execute(query)).all())  # Result itself is not dict()-able
