"""T3/T4 of spec 008: reminders through the service, the scheduler and the dev endpoint.

The scheduler loop is off in tests (`AppSettings.reengagement_scheduler` defaults to
False): tests call `ReengagementScheduler.tick(now)` or `ScreeningService.reengage`
with explicit times, so nothing depends on the wall clock.
"""

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from sazon_screening.api import repo
from sazon_screening.api.app import create_app
from sazon_screening.api.models import Message
from sazon_screening.api.service import ScreeningService
from sazon_screening.api.settings import AppSettings, load_app_settings
from sazon_screening.llm.pipeline import ScreeningAgent
from sazon_screening.llm.settings import SettingsError
from sazon_screening.reengagement import Abandon, SendFollowUp
from sazon_screening.reengagement.scheduler import ReengagementScheduler
from sazon_screening.vocab import Stage, Status
from tests.api.conftest import START, TickingClock

AGE_QUESTION = "¿Cuántos años tienes?"
VEHICLE_QUESTION = "¿Con qué vehículo repartirías?"
HOUR = timedelta(hours=1)


async def at_age(service: ScreeningService, at: datetime = START) -> str:
    """A candidate who consented and gave their name, then went quiet at `at`."""
    conversation_id = await service.start_conversation(at=at)
    await service.send_message(conversation_id, "sí", at=at)
    await service.send_message(conversation_id, "Me llamo Lucía Martín", at=at)
    return conversation_id


async def messages(service: ScreeningService, conversation_id: str) -> list[Message]:
    async with service._sessions() as session:
        return list(await repo.list_messages(session, conversation_id))


async def follow_ups(service: ScreeningService, conversation_id: str) -> list[Message]:
    return [m for m in await messages(service, conversation_id) if m.kind == "follow_up"]


async def conversation(service: ScreeningService, conversation_id: str) -> repo.Conversation:
    async with service._sessions() as session:
        row = await repo.get_conversation(session, conversation_id)
    assert row is not None
    return row


async def walk(service: ScreeningService, conversation_id: str, steps: int) -> None:
    """Run the next `steps` steps at their scheduled times (follow-ups, then abandon)."""
    for _ in range(steps):
        planned = await service.next_reengagement(conversation_id)
        assert planned is not None
        outcome = await service.reengage(conversation_id, at=planned.at)
        assert outcome.action != "none", outcome


@pytest.fixture
def scheduler(service: ScreeningService) -> ReengagementScheduler:
    return ReengagementScheduler(service, tick_seconds=30)


# --- the scheduler sends what is due, once ------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("008:AC-6")
async def test_the_scheduler_sends_a_due_follow_up_once(
    service: ScreeningService, scheduler: ReengagementScheduler
) -> None:
    conversation_id = await at_age(service)
    assert await scheduler.tick(START + HOUR) == []  # not due yet
    [sent] = await scheduler.tick(START + 2 * HOUR)
    assert (sent.action, sent.step, sent.requires_template) == ("follow_up", 1, False)
    assert await scheduler.tick(START + 2 * HOUR) == []  # idempotent: already sent
    [message] = await follow_ups(service, conversation_id)
    assert (message.role, message.follow_up_step) == ("agent", 1)
    assert message.text.endswith(AGE_QUESTION)
    assert message.created_at == START + 2 * HOUR
    row = await conversation(service, conversation_id)
    assert (row.follow_ups_sent, row.last_follow_up_at) == (1, START + 2 * HOUR)
    assert row.status == Status.in_progress  # a reminder changes nothing in the screening


@pytest.mark.anyio
@pytest.mark.ac("008:AC-6")
async def test_two_concurrent_ticks_send_the_step_once(
    service: ScreeningService, scheduler: ReengagementScheduler
) -> None:
    conversation_id = await at_age(service)
    now = START + 2 * HOUR
    await asyncio.gather(scheduler.tick(now), scheduler.tick(now))
    assert len(await follow_ups(service, conversation_id)) == 1


@pytest.mark.anyio
@pytest.mark.ac("008:AC-6")
async def test_two_processes_send_the_step_once(
    service: ScreeningService, agent: ScreeningAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another service (its own locks, like a second instance): both read the row before
    either writes, and the compare-and-set on the step stops the second reminder."""
    conversation_id = await at_age(service)
    other = service.with_agent(agent)
    both_read = asyncio.Event()
    arrived: list[int] = []
    phrase = agent.follow_up

    async def in_step(*args: object, **kwargs: object) -> object:
        arrived.append(1)
        if len(arrived) == 2:
            both_read.set()
        await both_read.wait()
        return await phrase(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(agent, "follow_up", in_step)
    now = START + 2 * HOUR
    results = await asyncio.gather(
        service.reengage(conversation_id, at=now), other.reengage(conversation_id, at=now)
    )
    assert sorted(r.action for r in results) == ["follow_up", "none"]
    assert {r.reason for r in results} == {None, "already_sent"}
    assert len(await follow_ups(service, conversation_id)) == 1


@pytest.mark.anyio
@pytest.mark.ac("008:AC-6")
@pytest.mark.parametrize(
    ("script", "status"),
    [
        (["sí", "Me llamo Lucía Martín", "tengo 16"], Status.disqualified),
        (["sí", "no me interesa, dame de baja"], Status.opted_out),
        (["sí", "Me llamo Lucía Martín", "quiero hablar con una persona"], Status.needs_review),
    ],
    ids=["disqualified", "opted-out", "needs-review"],
)
async def test_closed_conversations_never_get_follow_ups(
    service: ScreeningService,
    scheduler: ReengagementScheduler,
    script: list[str],
    status: Status,
) -> None:
    conversation_id = await service.start_conversation(at=START)
    for text in script:
        await service.send_message(conversation_id, text, at=START)
    assert (await conversation(service, conversation_id)).status == status
    assert await scheduler.tick(START + 10 * 24 * HOUR) == []
    forced = await service.reengage(conversation_id, force=True)
    assert (forced.action, forced.reason) == ("none", "closed")
    assert await follow_ups(service, conversation_id) == []


@pytest.mark.anyio
@pytest.mark.ac("008:AC-6")
async def test_no_follow_up_while_the_candidate_has_the_last_word(
    service: ScreeningService,
) -> None:
    """E.g. the API stopped between storing their message and the reply."""
    conversation_id = await at_age(service)
    async with service._sessions.begin() as session:
        repo.add(
            session,
            Message(conversation_id=conversation_id, role="candidate", text="…", created_at=START),
        )
    outcome = await service.reengage(conversation_id, force=True)
    assert (outcome.action, outcome.reason) == ("none", "candidate_last")


@pytest.mark.anyio
async def test_without_a_schedule_nothing_happens(
    service: ScreeningService, agent: ScreeningAgent
) -> None:
    conversation_id = await at_age(service)
    disabled = ScreeningService(agent, service._sessions, service._slots)
    assert await disabled.due_for_reengagement(START + 100 * HOUR) == []
    assert (await disabled.reengage(conversation_id, force=True)).reason == "disabled"


@pytest.mark.anyio
async def test_a_failing_conversation_does_not_stop_the_others(
    service: ScreeningService,
    scheduler: ReengagementScheduler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = await at_age(service), await at_age(service)
    real = service.reengage

    async def flaky(conversation_id: str, **kwargs: object) -> object:
        if conversation_id == first:
            raise RuntimeError("boom")
        return await real(conversation_id, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service, "reengage", flaky)
    [sent] = await scheduler.tick(START + 2 * HOUR)
    assert sent.action == "follow_up"
    assert len(await follow_ups(service, second)) == 1


@pytest.mark.anyio
async def test_the_loop_survives_a_failed_tick(service: ScreeningService) -> None:
    ticks: list[int] = []

    async def sleep(_: float) -> None:
        if len(ticks) == 2:
            raise asyncio.CancelledError
        ticks.append(1)

    scheduler = ReengagementScheduler(service, tick_seconds=1, sleep=sleep)

    async def broken(now: datetime | None = None) -> list[object]:
        raise RuntimeError("database down")

    scheduler.tick = broken  # type: ignore[method-assign]
    with pytest.raises(asyncio.CancelledError):
        await scheduler.run()
    assert len(ticks) == 2  # it kept ticking after the failure


# --- AC-4: abandon after the last reminder -------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("008:AC-4")
async def test_after_the_last_follow_up_the_conversation_is_abandoned_silently(
    service: ScreeningService, scheduler: ReengagementScheduler
) -> None:
    conversation_id = await at_age(service)
    await walk(service, conversation_id, 3)
    sent = await follow_ups(service, conversation_id)
    assert [m.follow_up_step for m in sent] == [1, 2, 3]
    assert sent[-1].text.startswith("Último recordatorio")
    planned = await service.next_reengagement(conversation_id)
    assert isinstance(planned, Abandon)
    before = len(await messages(service, conversation_id))
    [outcome] = await scheduler.tick(planned.at)
    assert (outcome.action, outcome.status, outcome.reply) == ("abandon", Status.abandoned, None)
    row = await conversation(service, conversation_id)
    assert (row.status, row.drop_off_stage) == (Status.abandoned, Stage.age)
    assert len(await messages(service, conversation_id)) == before  # no message
    assert await scheduler.tick(planned.at + 100 * HOUR) == []


# --- AC-5: the candidate comes back -------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("008:AC-5")
async def test_a_reply_after_follow_up_2_resumes_and_resets_the_cycle(
    service: ScreeningService, scheduler: ReengagementScheduler
) -> None:
    conversation_id = await at_age(service)
    await walk(service, conversation_id, 2)
    back = START + 30 * HOUR
    outcome = await service.send_message(conversation_id, "tengo 27", at=back)
    reply = outcome.result.reply
    assert reply is not None
    assert reply.text.endswith(VEHICLE_QUESTION)  # the pending age was answered: next ask
    assert outcome.result.state.profile.age.value is not None
    row = await conversation(service, conversation_id)
    assert (row.reactivated_after_step, row.follow_ups_sent) == (2, 0)
    assert (row.last_candidate_at, row.last_follow_up_at) == (back, None)
    # No more reminders until they go quiet again, then the schedule starts over.
    assert await scheduler.tick(back + HOUR) == []
    planned = await service.next_reengagement(conversation_id)
    assert planned == SendFollowUp(
        step=1, kind="nudge", at=back + 2 * HOUR, requires_template=False
    )


@pytest.mark.anyio
@pytest.mark.ac("008:AC-5")
async def test_a_reply_after_abandon_resumes_at_the_pending_question(
    service: ScreeningService,
) -> None:
    conversation_id = await at_age(service)
    await walk(service, conversation_id, 4)  # three reminders and the abandon
    outcome = await service.send_message(conversation_id, "hola, sigo aquí", at=START + 200 * HOUR)
    assert outcome.status is Status.in_progress
    assert outcome.result.reply is not None
    assert outcome.result.reply.text.endswith(AGE_QUESTION)
    assert (await conversation(service, conversation_id)).reactivated_after_step == 3


@pytest.mark.anyio
async def test_a_candidate_who_never_wrote_gets_template_reminders(
    service: ScreeningService,
) -> None:
    conversation_id = await service.start_conversation(at=START)
    outcome = await service.reengage(conversation_id, at=START + 2 * HOUR)
    assert (outcome.action, outcome.requires_template) == ("follow_up", True)
    [message] = await follow_ups(service, conversation_id)
    assert message.trace_json is not None
    assert message.trace_json["follow_up"]["requires_template"] is True
    assert message.trace_json["phrasing"]["outcome"] == "skipped"  # no model past the window


# --- AC-8: the dev endpoint and analytics -------------------------------------------------


async def chat(client: AsyncClient, *texts: str) -> str:
    created = await client.post("/api/conversations", json={})
    conversation_id: str = created.json()["id"]
    for text in texts:
        await client.post(f"/api/conversations/{conversation_id}/messages", json={"text": text})
    return conversation_id


@pytest.mark.anyio
@pytest.mark.ac("008:AC-8")
async def test_advance_runs_exactly_the_next_step(client: AsyncClient) -> None:
    conversation_id = await chat(client, "sí", "Me llamo Lucía Martín")
    url = f"/api/dev/conversations/{conversation_id}/advance"
    for step in (1, 2, 3):
        response = await client.post(url)
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["action"], body["step"], body["status"]) == ("follow_up", step, "in_progress")
        assert body["reply"]["text"].endswith(AGE_QUESTION)
        assert body["next"]["action"] == ("follow_up" if step < 3 else "abandon")
    transcript = (await client.get(f"/api/conversations/{conversation_id}")).json()["messages"]
    reminders = [m for m in transcript if m["kind"] == "follow_up"]
    assert [m["follow_up_step"] for m in reminders] == [1, 2, 3]
    assert all(m["role"] == "agent" for m in reminders)
    assert {m["kind"] for m in transcript} == {"reply", "follow_up"}

    abandoned = await client.post(url)
    assert abandoned.status_code == 200
    assert abandoned.json() | {"next": None} == {
        "action": "abandon",
        "status": "abandoned",
        "step": None,
        "reply": None,
        "requires_template": False,
        "next": None,
    }
    again = await client.post(url)
    assert again.status_code == 409
    assert "closed" in again.json()["detail"]


@pytest.mark.anyio
@pytest.mark.ac("008:AC-8")
async def test_the_candidate_detail_shows_the_reminders(client: AsyncClient) -> None:
    conversation_id = await chat(client, "sí", "Me llamo Lucía Martín")
    await client.post(f"/api/dev/conversations/{conversation_id}/advance")
    detail = (await client.get(f"/api/candidates/{conversation_id}")).json()
    assert detail["reengagement"] | {"last_follow_up_at": None, "next": None} == {
        "follow_ups_sent": 1,
        "waiting_steps": 1,
        "last_follow_up_at": None,
        "reactivated_after_step": None,
        "next": None,
        "total_steps": 3,  # the shipped schedule: 2 h, 23 h, 72 h
    }
    assert detail["reengagement"]["next"]["step"] == 2
    assert detail["transcript"][-1]["kind"] == "follow_up"
    trace = detail["traces"][-1]
    assert (trace["kind"], trace["action"], trace["extraction"]) == (
        "follow_up",
        "follow_up",
        "skipped",
    )
    await client.post(f"/api/conversations/{conversation_id}/messages", json={"text": "tengo 27"})
    detail = (await client.get(f"/api/candidates/{conversation_id}")).json()
    assert detail["reengagement"]["reactivated_after_step"] == 1
    assert detail["reengagement"]["waiting_steps"] == 0


@pytest.mark.anyio
@pytest.mark.ac("008:AC-8")
async def test_reengagement_analytics_add_up(client: AsyncClient) -> None:
    quiet = await chat(client, "sí", "Me llamo Lucía Martín")
    back_after_1 = await chat(client, "sí", "Me llamo Pablo Ruiz")
    back_after_2 = await chat(client, "sí")
    await chat(client, "sí", "Me llamo Marta Gil")  # never nudged
    for conversation_id, steps in ((quiet, 4), (back_after_1, 1), (back_after_2, 2)):
        for _ in range(steps):
            await client.post(f"/api/dev/conversations/{conversation_id}/advance")
    await client.post(f"/api/conversations/{back_after_1}/messages", json={"text": "tengo 30"})
    await client.post(
        f"/api/conversations/{back_after_2}/messages", json={"text": "Me llamo Elena Navarro"}
    )
    analytics = (await client.get("/api/analytics")).json()["reengagement"]
    assert analytics == {
        "follow_ups_sent": 6,
        "conversations_nudged": 3,
        "reactivated": 2,
        "reactivation_rate": round(2 / 3, 4),
        "by_step": [
            {"step": 1, "sent": 3, "reactivated": 1},
            {"step": 2, "sent": 2, "reactivated": 1},
            {"step": 3, "sent": 1, "reactivated": 0},
        ],
    }
    assert sum(s["sent"] for s in analytics["by_step"]) == analytics["follow_ups_sent"]
    assert sum(s["reactivated"] for s in analytics["by_step"]) == analytics["reactivated"]


@pytest.mark.anyio
async def test_silence_still_abandons_at_once(client: AsyncClient) -> None:
    """The 004 route is kept: straight to `abandoned`, skipping the reminders."""
    conversation_id = await chat(client, "sí")
    response = await client.post(f"/api/dev/conversations/{conversation_id}/silence")
    assert response.json()["status"] == "abandoned"


@pytest.mark.anyio
async def test_advance_is_dev_only(settings: AppSettings, agent: ScreeningAgent) -> None:
    from httpx import ASGITransport

    app = create_app(settings.model_copy(update={"app_env": "prod"}), agent=agent)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/dev/conversations/x/advance")
    assert response.status_code == 403


# --- settings and the lifespan -------------------------------------------------------------


def test_scheduler_and_time_scale_come_from_the_environment() -> None:
    settings = load_app_settings({"REENGAGEMENT_TIME_SCALE": "60"})
    assert (settings.reengagement_scheduler, settings.reengagement_time_scale) == (True, 60)
    off = load_app_settings({"REENGAGEMENT_SCHEDULER": "off"})
    assert (off.reengagement_scheduler, off.reengagement_time_scale) == (False, 1)
    assert AppSettings().reengagement_scheduler is False  # tests drive it themselves


@pytest.mark.parametrize(
    "environ",
    [
        {"REENGAGEMENT_TIME_SCALE": "fast"},
        {"REENGAGEMENT_TIME_SCALE": "0"},
        {"REENGAGEMENT_SCHEDULER": "maybe"},
    ],
)
def test_bad_reengagement_settings_fail_at_startup(environ: dict[str, str]) -> None:
    with pytest.raises(SettingsError, match="REENGAGEMENT"):
        load_app_settings(environ)


@pytest.mark.anyio
async def test_the_lifespan_starts_and_stops_the_loop(
    settings: AppSettings, agent: ScreeningAgent
) -> None:
    on = settings.model_copy(
        update={"reengagement_scheduler": True, "reengagement_time_scale": 60.0}
    )
    app: FastAPI = create_app(on, agent=agent, clock=TickingClock())
    async with app.router.lifespan_context(app):
        tasks = [t for t in asyncio.all_tasks() if t.get_name() == "reengagement"]
        assert len(tasks) == 1
        service: ScreeningService = app.state.service
        assert service.reengagement is not None
        assert service.reengagement.follow_ups[0].after == timedelta(minutes=2)  # scaled
    assert tasks[0].done()
