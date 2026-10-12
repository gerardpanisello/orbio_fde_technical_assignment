"""T2: tables and repo functions on a temp SQLite file."""

from datetime import UTC, datetime, timedelta

import pytest

from sazon_screening.api import repo
from sazon_screening.api.db import Sessions
from sazon_screening.api.models import Conversation, Message, SummaryRow

T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def conversation(conversation_id: str, **columns: object) -> Conversation:
    values: dict[str, object] = {
        "created_at": T0,
        "updated_at": T0,
        "status": "in_progress",
        "stage": "consent",
        "language": "es",
        "state_json": {},
        "record_json": {},
        "flags_json": [],
    }
    return Conversation(id=conversation_id, **(values | columns))


def message(conversation_id: str, role: str, text: str) -> Message:
    return Message(conversation_id=conversation_id, role=role, text=text, created_at=T0)


@pytest.mark.anyio
async def test_conversation_round_trip_keeps_utc_and_json(sessions: Sessions) -> None:
    async with sessions.begin() as session:
        repo.add(session, conversation("c1", state_json={"status": "in_progress"}))
    async with sessions() as session:
        row = await repo.get_conversation(session, "c1")
    assert row is not None
    assert row.created_at == T0
    assert row.created_at.tzinfo is UTC
    assert row.state_json == {"status": "in_progress"}
    assert row.recruiter_status == "new"
    assert row.recruiter_override is False


@pytest.mark.anyio
async def test_messages_come_back_in_insertion_order_and_redact(sessions: Sessions) -> None:
    async with sessions.begin() as session:
        repo.add(session, conversation("c1"))
        for n, role in enumerate(["agent", "candidate", "agent"]):
            repo.add(session, message("c1", role, f"m{n}"))
    async with sessions() as session:
        assert [m.text for m in await repo.list_messages(session, "c1")] == ["m0", "m1", "m2"]
    async with sessions.begin() as session:
        await repo.redact_messages(session, "c1")
    async with sessions() as session:
        texts = {m.text for m in await repo.list_messages(session, "c1")}
    assert texts == {repo.REDACTED}


@pytest.mark.anyio
async def test_summary_is_replaced_per_language_and_deleted(sessions: Sessions) -> None:
    async with sessions.begin() as session:
        repo.add(session, conversation("c1"))
        for text in ("old", "new"):
            await repo.save_summary(
                session,
                SummaryRow(conversation_id="c1", language="es", json={"text": text}, created_at=T0),
            )
    async with sessions() as session:
        row = await repo.get_summary(session, "c1", "es")
        assert row is not None
        assert row.json == {"text": "new"}
    async with sessions.begin() as session:
        await repo.delete_summaries(session, "c1")
    async with sessions() as session:
        assert await repo.get_summary(session, "c1", "es") is None


@pytest.mark.anyio
async def test_list_filters_and_sorts_with_unscored_last(sessions: Sessions) -> None:
    async with sessions.begin() as session:
        repo.add(session, conversation("a", full_name="Ana López", score=40, city="madrid"))
        repo.add(session, conversation("b", full_name="Beto Ruiz", score=80, city="cdmx"))
        repo.add(
            session,
            conversation("c", full_name=None, score=None, updated_at=T0 + timedelta(hours=1)),
        )
    async with sessions() as session:
        by_score = await repo.list_candidates(session, repo.CandidateFilters(sort="-score"))
        ascending = await repo.list_candidates(session, repo.CandidateFilters(sort="score"))
        recent = await repo.list_candidates(session, repo.CandidateFilters(sort="-updated"))
        madrid = await repo.list_candidates(session, repo.CandidateFilters(city="madrid"))
        named = await repo.list_candidates(session, repo.CandidateFilters(q="lóp"))
    assert [r.id for r in by_score] == ["b", "a", "c"]
    assert [r.id for r in ascending] == ["a", "b", "c"]
    assert recent[0].id == "c"
    assert [r.id for r in madrid] == ["a"]
    assert [r.id for r in named] == ["a"]
