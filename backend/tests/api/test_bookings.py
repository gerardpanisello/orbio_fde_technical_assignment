"""Spec 010 T2: bookings with a capacity check, and the slot-taken path (FR-3, AC-2)."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from sazon_screening.api import repo
from sazon_screening.api.db import Sessions
from sazon_screening.api.models import Conversation, InterviewBooking
from sazon_screening.api.service import ScreeningService
from sazon_screening.vocab import Status
from tests.api.conftest import HAPPY_PATH

pytestmark = pytest.mark.anyio

# Málaga has capacity 1 per slot in the shipped interview_slots.yaml.
MALAGA_PATH = [*HAPPY_PATH[:5], "vivo en Teatinos, Málaga", *HAPPY_PATH[6:11]]


async def at_the_offer(service: ScreeningService, path: list[str] = MALAGA_PATH) -> str:
    conversation_id = await service.start_conversation()
    for text in path:
        outcome = await service.send_message(conversation_id, text)
    assert outcome.result.trace.action is not None
    assert outcome.result.trace.action.primary.type == "offer_slots"
    return conversation_id


async def bookings(sessions: Sessions) -> list[InterviewBooking]:
    async with sessions() as session:
        return list((await session.scalars(select(InterviewBooking))).all())


async def test_picking_a_slot_stores_a_booking(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await at_the_offer(service)
    outcome = await service.send_message(conversation_id, "1")
    assert outcome.status is Status.interview_scheduled
    [booking] = await bookings(sessions)
    assert booking.conversation_id == conversation_id
    assert booking.slot_id == "malaga:2026-10-13T10:00"
    assert booking.starts_at == datetime(2026, 10, 13, 8, 0, tzinfo=UTC)  # 10:00 CEST
    assert (booking.status, booking.seat, booking.duration_min) == ("booked", 0, 30)
    assert "malaga" in booking.place
    reply = outcome.result.reply
    assert reply is not None
    assert booking.place in reply.text


@pytest.mark.ac("010:AC-2")
async def test_two_candidates_racing_for_the_last_seat(
    service: ScreeningService, sessions: Sessions
) -> None:
    """Capacity 1, two conversations confirm the same slot at the same time."""
    first, second = await at_the_offer(service), await at_the_offer(service)
    outcomes = await asyncio.gather(
        service.send_message(first, "1"), service.send_message(second, "1")
    )
    statuses = sorted(o.status for o in outcomes)
    assert statuses == [Status.in_progress, Status.interview_scheduled]
    booked = [b for b in await bookings(sessions) if b.status == "booked"]
    assert [b.slot_id for b in booked] == ["malaga:2026-10-13T10:00"]
    loser = next(o for o in outcomes if o.status is Status.in_progress)
    action = loser.result.trace.action
    assert action is not None
    assert action.primary.type == "offer_slots"
    assert getattr(action.primary, "reason", None) == "slot_taken"
    assert "malaga:2026-10-13T10:00" not in getattr(action.primary, "slot_ids", [])
    assert loser.result.reply is not None
    assert "ocupar" in loser.result.reply.text


@pytest.mark.ac("010:AC-2")
async def test_a_stale_seat_count_is_caught_by_the_database(
    service: ScreeningService, sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard is the unique index, not the count: even if the count read misses the
    other booking (the race window), the insert fails and the retry finds the slot full."""
    first, second = await at_the_offer(service), await at_the_offer(service)
    assert (await service.send_message(first, "1")).status is Status.interview_scheduled
    real = repo.seats_taken
    calls = 0

    async def stale_once(session: object, slot_id: str) -> set[int]:
        nonlocal calls
        calls += 1
        return set() if calls == 1 else await real(session, slot_id)  # type: ignore[arg-type]

    monkeypatch.setattr(repo, "seats_taken", stale_once)
    outcome = await service.send_message(second, "1")
    assert calls >= 2  # the first attempt hit the index and was retried
    assert outcome.status is Status.in_progress
    booked = [b for b in await bookings(sessions) if b.status == "booked"]
    assert [b.conversation_id for b in booked] == [first]


@pytest.mark.ac("010:AC-2")
async def test_the_seat_index_refuses_a_second_booking(sessions: Sessions) -> None:
    now = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    async with sessions.begin() as session:
        for cid in ("a", "b"):
            repo.add(session, _conversation(cid, now))

    async def book_both() -> None:
        async with sessions.begin() as session:
            for cid in ("a", "b"):
                repo.add(session, _booking(cid, "malaga:2026-10-13T10:00", now))

    with pytest.raises(IntegrityError):
        await book_both()
    async with sessions.begin() as session:  # a cancelled booking does not hold the seat
        repo.add(session, _booking("a", "malaga:2026-10-13T10:00", now, status="cancelled"))
        repo.add(session, _booking("b", "malaga:2026-10-13T10:00", now))


async def test_capacity_above_one_books_both(service: ScreeningService, sessions: Sessions) -> None:
    first, second = (
        await at_the_offer(service, HAPPY_PATH[:11]),
        await at_the_offer(service, HAPPY_PATH[:11]),
    )  # Madrid: capacity 3
    outcomes = await asyncio.gather(
        service.send_message(first, "1"), service.send_message(second, "1")
    )
    assert {o.status for o in outcomes} == {Status.interview_scheduled}
    seats = sorted(b.seat for b in await bookings(sessions))
    assert seats == [0, 1]


async def test_slot_taken_with_nothing_left_is_qualified_unscheduled(
    service: ScreeningService, sessions: Sessions
) -> None:
    first, second = await at_the_offer(service), await at_the_offer(service)
    async with sessions.begin() as session:  # every other Málaga slot fills up meanwhile
        for index, slot_id in enumerate(
            [
                "malaga:2026-10-13T17:00",
                "malaga:2026-10-14T10:00",
                "malaga:2026-10-14T17:00",
                "malaga:2026-10-15T10:00",
                "malaga:2026-10-15T17:00",
            ]
        ):
            other = f"other-{index}"
            now = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
            repo.add(session, _conversation(other, now))
            repo.add(session, _booking(other, slot_id, now))
    await service.send_message(first, "1")
    outcome = await service.send_message(second, "1")
    assert outcome.status is Status.qualified_unscheduled
    async with sessions() as session:
        assert await repo.active_booking(session, second) is None


def _conversation(cid: str, now: datetime) -> Conversation:
    return Conversation(
        id=cid,
        created_at=now,
        updated_at=now,
        status="in_progress",
        stage="consent",
        language="es",
        state_json={},
        record_json={},
        flags_json=[],
    )


def _booking(cid: str, slot_id: str, now: datetime, *, status: str = "booked") -> InterviewBooking:
    return InterviewBooking(
        conversation_id=cid,
        slot_id=slot_id,
        city="malaga",
        starts_at=datetime(2026, 10, 13, 8, 0, tzinfo=UTC),
        duration_min=30,
        place="x",
        seat=0,
        status=status,
        created_at=now,
        updated_at=now,
    )
