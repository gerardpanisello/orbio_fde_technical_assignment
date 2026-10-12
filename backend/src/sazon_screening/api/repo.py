"""Queries: the only module with SQL. Plain functions over an `AsyncSession`.

The caller owns the transaction (`async with sessions.begin()`), so one turn's writes
(state, both messages) commit together or not at all.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import ColumnElement, Integer, Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api.models import (
    Conversation,
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
    session: AsyncSession, row: Conversation | Message | RecruiterAction | ZoneStaffing
) -> None:
    session.add(row)


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


async def durations(
    session: AsyncSession, statuses: Sequence[str]
) -> list[tuple[datetime, datetime]]:
    query = select(Conversation.created_at, Conversation.updated_at).where(
        Conversation.status.in_(statuses)
    )
    return [(created, updated) for created, updated in await session.execute(query)]


async def turn_totals(session: AsyncSession) -> tuple[int, int, float]:
    """Agent replies: (turns, fallbacks, total cost in USD incl. summaries)."""
    fallbacks = func.coalesce(func.sum(Message.fallback.cast(Integer)), 0)
    query = select(func.count(), fallbacks).where(Message.role == "agent")
    turn_count, fallback_count = (await session.execute(query)).one()
    cost = await session.scalar(select(func.coalesce(func.sum(Message.cost_usd), 0.0)))
    summary_cost = await session.scalar(select(func.coalesce(func.sum(SummaryRow.cost_usd), 0.0)))
    return int(turn_count), int(fallback_count), float(cost or 0) + float(summary_cost or 0)
