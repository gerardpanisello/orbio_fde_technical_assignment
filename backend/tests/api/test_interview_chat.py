"""Spec 010 T3: move or cancel the interview by chat, end to end (offline agent)."""

import pytest

from sazon_screening.api import repo
from sazon_screening.api.db import Sessions
from sazon_screening.api.service import ScreeningService, TurnOutcome
from sazon_screening.vocab import Flag, Status
from tests.api.conftest import HAPPY_PATH
from tests.api.test_bookings import MALAGA_PATH

pytestmark = pytest.mark.anyio


async def booked(service: ScreeningService, path: list[str] = HAPPY_PATH) -> str:
    conversation_id = await service.start_conversation()
    for text in path:
        outcome = await service.send_message(conversation_id, text)
    assert outcome.status is Status.interview_scheduled
    return conversation_id


def primary(outcome: TurnOutcome) -> dict[str, object]:
    action = outcome.result.trace.action
    assert action is not None
    return action.primary.model_dump(mode="json")


@pytest.mark.ac("010:AC-3")
async def test_reschedule_moves_the_booking_and_frees_the_old_seat(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await booked(service)  # Madrid, Tue 13/10 10:00
    asked = await service.send_message(conversation_id, "¿Puedo cambiar la entrevista?")
    offer = primary(asked)
    assert offer["type"] == "offer_slots"
    assert offer["reason"] == "reschedule"
    assert "madrid:2026-10-13T10:00" not in offer["slot_ids"]  # type: ignore[operator]
    assert asked.status is Status.in_progress
    reply = asked.result.reply
    assert reply is not None
    assert "sigue en pie" in reply.text
    assert reply.quick_replies  # the new times as buttons
    picked = await service.send_message(conversation_id, "2")
    assert picked.status is Status.interview_scheduled
    async with sessions() as session:
        history = await repo.bookings_for(session, conversation_id)
        row = await repo.get_conversation(session, conversation_id)
    assert [b.status for b in history] == ["rescheduled", "booked"]
    assert history[0].slot_id == "madrid:2026-10-13T10:00"
    assert history[1].slot_id == offer["slot_ids"][1]  # type: ignore[index]
    assert row is not None
    assert row.interview_slot == history[1].slot_id
    assert Flag.interview_rescheduled in row.flags_json


@pytest.mark.ac("010:AC-3")
async def test_none_fits_keeps_the_old_booking(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await booked(service)
    await service.send_message(conversation_id, "quiero cambiar la cita a otro día")
    kept = await service.send_message(conversation_id, "ninguna me va bien")
    assert primary(kept) == {"type": "keep_interview", "slot_id": "madrid:2026-10-13T10:00"}
    assert kept.status is Status.interview_scheduled
    async with sessions() as session:
        history = await repo.bookings_for(session, conversation_id)
    assert [(b.slot_id, b.status) for b in history] == [("madrid:2026-10-13T10:00", "booked")]


@pytest.mark.ac("010:AC-4")
async def test_cancel_releases_the_slot_for_someone_else(
    service: ScreeningService, sessions: Sessions
) -> None:
    first = await booked(service, [*MALAGA_PATH, "1"])  # Málaga: one seat per slot
    other = await service.start_conversation()
    for text in MALAGA_PATH:
        before = await service.send_message(other, text)
    assert "malaga:2026-10-13T10:00" not in primary(before)["slot_ids"]  # type: ignore[operator]

    cancelled = await service.send_message(first, "Cancela la cita, por favor")
    assert primary(cancelled) == {"type": "close_interview_cancelled"}
    assert cancelled.status is Status.qualified_unscheduled
    async with sessions() as session:
        [booking] = await repo.bookings_for(session, first)
        row = await repo.get_conversation(session, first)
    assert booking.status == "cancelled"
    assert row is not None
    assert row.interview_slot is None
    assert Flag.interview_cancelled in row.flags_json

    asks_again = await service.send_message(other, "¿hay otras horas?")
    assert "malaga:2026-10-13T10:00" in primary(asks_again)["slot_ids"]  # type: ignore[operator]


@pytest.mark.ac("010:AC-4")
async def test_opt_out_after_booking_cancels_it(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await booked(service)
    out = await service.send_message(conversation_id, "no me interesa, dame de baja")
    assert out.status is Status.opted_out
    async with sessions() as session:
        [booking] = await repo.bookings_for(session, conversation_id)
    assert booking.status == "cancelled"


async def test_a_cancelled_candidate_can_book_again(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await booked(service)
    await service.send_message(conversation_id, "cancela la entrevista")
    offered = await service.send_message(conversation_id, "quiero una cita")
    assert primary(offered)["type"] == "offer_slots"
    rebooked = await service.send_message(conversation_id, "1")
    assert rebooked.status is Status.interview_scheduled
    async with sessions() as session:
        statuses = [b.status for b in await repo.bookings_for(session, conversation_id)]
    assert statuses == ["cancelled", "booked"]
