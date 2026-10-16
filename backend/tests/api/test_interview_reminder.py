"""Spec 010 T5: the day-before reminder through the scheduler loop (AC-6)."""

from datetime import UTC, datetime, timedelta

import pytest

from sazon_screening.api import repo
from sazon_screening.api.db import Sessions
from sazon_screening.api.service import Outbound, ScreeningService
from sazon_screening.reengagement.scheduler import ReengagementScheduler
from sazon_screening.vocab import Status
from tests.api.conftest import HAPPY_PATH, TickingClock

pytestmark = pytest.mark.anyio

# The clock starts Monday 12/10 09:00 UTC; the happy path books Tue 13/10 10:00 in Madrid
# (08:00 UTC). The reminder is due Monday 18:00 in Madrid (16:00 UTC).
BEFORE = datetime(2026, 10, 12, 15, 59, tzinfo=UTC)
DUE = datetime(2026, 10, 12, 16, 0, tzinfo=UTC)
QUIET = datetime(2026, 10, 12, 21, 30, tzinfo=UTC)  # 23:30 in Madrid


class Recorder:
    def __init__(self) -> None:
        self.sent: list[Outbound] = []

    async def deliver(self, outbound: Outbound) -> None:
        self.sent.append(outbound)


async def book(service: ScreeningService, channel: str = "web") -> str:
    conversation_id = await service.start_conversation(channel=channel)  # type: ignore[arg-type]
    for text in HAPPY_PATH:
        outcome = await service.send_message(conversation_id, text)
    assert outcome.status is Status.interview_scheduled
    return conversation_id


async def reminders(sessions: Sessions, conversation_id: str) -> list[str]:
    async with sessions() as session:
        messages = await repo.list_messages(session, conversation_id)
    return [m.text for m in messages if m.kind == "reminder"]


@pytest.mark.ac("010:AC-6")
async def test_sent_once_the_day_before_at_the_local_hour(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await book(service)
    scheduler = ReengagementScheduler(service, tick_seconds=30)
    await scheduler.tick(BEFORE)
    assert await reminders(sessions, conversation_id) == []
    await scheduler.tick(DUE)
    await scheduler.tick(DUE + timedelta(minutes=1))  # the next tick: already sent
    [text] = await reminders(sessions, conversation_id)
    assert text.startswith("Te recuerdo tu entrevista mañana a las 10:00 en Oficina Grupo Sazón")
    async with sessions() as session:
        booking = await repo.active_booking(session, conversation_id)
    assert booking is not None
    assert booking.reminder_sent_at == DUE
    conversation = (await service.send_message(conversation_id, "gracias")).status
    assert conversation is Status.interview_scheduled  # the reminder changes nothing else


@pytest.mark.ac("010:AC-6")
async def test_not_sent_in_quiet_hours(service: ScreeningService, sessions: Sessions) -> None:
    conversation_id = await book(service)
    assert await service.due_interview_reminders(QUIET) == []
    assert await reminders(sessions, conversation_id) == []
    assert len(await service.due_interview_reminders(QUIET + timedelta(hours=10))) == 1  # 09:30


@pytest.mark.ac("010:AC-6")
async def test_a_whatsapp_candidate_gets_it_on_whatsapp(service: ScreeningService) -> None:
    recorder = Recorder()
    service.register_delivery("whatsapp", recorder)
    web = await book(service)
    whatsapp = await book(service, channel="whatsapp")
    await ReengagementScheduler(service, tick_seconds=30).tick(DUE)
    assert [o.conversation_id for o in recorder.sent] == [whatsapp]  # web pulls instead
    [outbound] = recorder.sent
    assert outbound.kind == "reminder"
    assert outbound.outside_window is False  # they wrote this morning
    assert web != whatsapp


@pytest.mark.ac("010:AC-6")
async def test_outside_the_whatsapp_window_it_is_marked_for_the_template(
    service: ScreeningService, sessions: Sessions
) -> None:
    recorder = Recorder()
    service.register_delivery("whatsapp", recorder)
    conversation_id = await book(service, channel="whatsapp")
    async with sessions.begin() as session:  # they last wrote two days ago
        row = await repo.get_conversation(session, conversation_id)
        assert row is not None
        row.last_candidate_at = DUE - timedelta(days=2)
    assert await service.send_interview_reminder(
        (await service.due_interview_reminders(DUE))[0], at=DUE
    )
    assert recorder.sent[0].outside_window is True


async def test_a_cancelled_or_moved_booking_gets_no_reminder(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await book(service)
    await service.send_message(conversation_id, "cancela la cita")
    assert await service.due_interview_reminders(DUE) == []


async def test_booked_after_the_reminder_time_gets_none(
    service: ScreeningService, clock: TickingClock
) -> None:
    clock.now = datetime(2026, 10, 12, 19, 0, tzinfo=UTC)  # Monday 21:00 in Madrid
    await book(service)  # Tuesday 10:00 is still the first slot
    assert await service.due_interview_reminders(datetime(2026, 10, 13, 7, 0, tzinfo=UTC)) == []
