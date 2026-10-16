"""T3: turn orchestration: state in the DB, one turn at a time, summary after the close."""

from typing import Any

import anyio
import pytest

from sazon_screening.api import repo
from sazon_screening.api.db import Sessions
from sazon_screening.api.service import ConversationNotFound, ScreeningService
from sazon_screening.engine import SilenceExpired
from sazon_screening.llm.pipeline import ScreeningAgent
from sazon_screening.vocab import Status
from tests.api.conftest import HAPPY_PATH


@pytest.mark.anyio
@pytest.mark.ac("004:AC-1")
async def test_start_stores_the_greeting_and_an_in_progress_row(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await service.start_conversation()
    async with sessions() as session:
        row = await repo.get_conversation(session, conversation_id)
        messages = await repo.list_messages(session, conversation_id)
    assert row is not None
    assert row.status == "in_progress"
    assert [m.role for m in messages] == ["agent"]
    assert "Sofi" in messages[0].text
    assert [q["label"] for q in messages[0].quick_replies_json] == ["Sí", "No"]


@pytest.mark.anyio
@pytest.mark.ac("004:AC-2")
async def test_happy_path_books_an_interview_from_the_slot_provider(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await service.start_conversation()
    for text in HAPPY_PATH:
        outcome = await service.send_message(conversation_id, text)
    assert outcome.status is Status.interview_scheduled
    async with sessions() as session:
        row = await repo.get_conversation(session, conversation_id)
    assert row is not None
    assert row.interview_slot == "madrid:2026-10-13T10:00"  # first slot: the next working day
    assert row.city == "madrid"
    assert row.full_name == "Lucía Martín"
    assert row.bucket is not None


@pytest.mark.anyio
@pytest.mark.ac("004:AC-3")
async def test_concurrent_messages_are_processed_one_at_a_time(
    service: ScreeningService,
    sessions: Sessions,
    agent: ScreeningAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow agent: without the lock both turns would read the same state (lost update)."""
    real = agent.handle_message

    async def slow(*args: Any, **kwargs: Any) -> Any:
        await anyio.sleep(0.05)
        return await real(*args, **kwargs)

    monkeypatch.setattr(agent, "handle_message", slow)
    conversation_id = await service.start_conversation()
    async with anyio.create_task_group() as group:
        group.start_soon(service.send_message, conversation_id, "sí")
        await anyio.sleep(0.01)
        group.start_soon(service.send_message, conversation_id, "Me llamo Lucía Martín")
    async with sessions() as session:
        row = await repo.get_conversation(session, conversation_id)
        messages = await repo.list_messages(session, conversation_id)
    assert row is not None
    assert row.state_json["consent"] is True  # the first turn was not overwritten
    assert row.full_name == "Lucía Martín"
    assert [m.role for m in messages] == ["agent", "candidate", "agent", "candidate", "agent"]


@pytest.mark.anyio
@pytest.mark.ac("004:AC-4")
async def test_unknown_conversation_raises_not_found(service: ScreeningService) -> None:
    with pytest.raises(ConversationNotFound):
        await service.send_message("nope", "hola")


@pytest.mark.anyio
@pytest.mark.ac("004:AC-2")
async def test_summary_is_stored_after_the_close_and_dropped_when_status_changes(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await service.start_conversation()
    await service.send_message(conversation_id, "sí")
    outcome = await service.send_event(conversation_id, SilenceExpired())
    assert outcome.status is Status.abandoned
    assert outcome.result.summary_due
    await service.write_summary(conversation_id)
    async with sessions() as session:
        assert await repo.get_summary(session, conversation_id, "es") is not None
    await service.send_message(conversation_id, "Me llamo Lucía Martín")  # resumes: in_progress
    async with sessions() as session:
        assert await repo.get_summary(session, conversation_id, "es") is None


@pytest.mark.anyio
@pytest.mark.ac("004:AC-10")
async def test_opt_out_redacts_the_stored_transcript(
    service: ScreeningService, sessions: Sessions
) -> None:
    conversation_id = await service.start_conversation()
    for text in ["sí", "Me llamo Iván Mora", "no me interesa, dame de baja"]:
        outcome = await service.send_message(conversation_id, text)
    assert outcome.status is Status.opted_out
    async with sessions() as session:
        row = await repo.get_conversation(session, conversation_id)
        messages = await repo.list_messages(session, conversation_id)
    assert row is not None
    assert row.full_name is None
    assert "Iván" not in str(row.state_json) + str(row.record_json)
    assert {m.text for m in messages} == {repo.REDACTED}
    assert all(m.trace_json is None for m in messages)
