"""T4: the candidate chat over HTTP (AC-1..AC-4)."""

import json
from typing import Any

import anyio
import jsonschema
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from sazon_screening.api import repo
from sazon_screening.api.service import ScreeningService
from sazon_screening.llm.pipeline import ScreeningAgent
from tests.api.conftest import HAPPY_PATH
from tests.paths import BACKEND_DIR

RECORD_SCHEMA = json.loads(
    (BACKEND_DIR.parent / "docs/specs/002-screening-engine/candidate-record.schema.json").read_text(
        encoding="utf-8"
    )
)


async def start(client: AsyncClient, **body: Any) -> dict[str, Any]:
    response = await client.post("/api/conversations", json=body)
    assert response.status_code == 201
    created: dict[str, Any] = response.json()
    return created


async def say(client: AsyncClient, conversation_id: str, text: str) -> dict[str, Any]:
    response = await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": text}
    )
    assert response.status_code == 200, response.text
    turn: dict[str, Any] = response.json()
    return turn


@pytest.mark.anyio
@pytest.mark.ac("004:AC-1")
async def test_create_returns_the_greeting_with_yes_no_buttons(client: AsyncClient) -> None:
    created = await start(client)
    assert created["status"] == "in_progress"
    assert created["language"] == "es"
    [greeting] = created["messages"]
    assert greeting["role"] == "agent"
    assert "Sofi" in greeting["text"]
    assert [q["label"] for q in greeting["quick_replies"]] == ["Sí", "No"]


@pytest.mark.anyio
@pytest.mark.ac("004:AC-1")
async def test_create_in_english_for_a_mexican_phone(client: AsyncClient) -> None:
    created = await start(client, language="en", country_hint="MX")
    assert created["language"] == "en"
    assert [q["label"] for q in created["messages"][0]["quick_replies"]] == ["Yes", "No"]


@pytest.mark.anyio
@pytest.mark.ac("004:AC-2")
async def test_happy_path_over_http(client: AsyncClient, app: FastAPI) -> None:
    conversation_id = (await start(client))["id"]
    for text in HAPPY_PATH:
        turn = await say(client, conversation_id, text)
    assert turn["status"] == "interview_scheduled"
    assert turn["reply"]["text"]

    reloaded = (await client.get(f"/api/conversations/{conversation_id}")).json()
    messages = reloaded["messages"]
    assert reloaded["status"] == "interview_scheduled"
    assert [m["role"] for m in messages] == ["agent"] + ["candidate", "agent"] * len(HAPPY_PATH)
    assert [m["text"] for m in messages if m["role"] == "candidate"] == HAPPY_PATH
    assert [m["id"] for m in messages] == sorted(m["id"] for m in messages)

    async with app.state.sessions() as session:
        row = await repo.get_conversation(session, conversation_id)
        summary = await repo.get_summary(session, conversation_id, "es")  # background task ran
    assert row is not None
    jsonschema.validate(row.record_json, RECORD_SCHEMA)
    assert summary is not None
    assert summary.json["status"] == "interview_scheduled"


@pytest.mark.anyio
@pytest.mark.ac("004:AC-3")
async def test_two_concurrent_posts_are_both_applied(
    client: AsyncClient, agent: ScreeningAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = agent.handle_message

    async def slow(*args: Any, **kwargs: Any) -> Any:
        await anyio.sleep(0.05)
        return await real(*args, **kwargs)

    monkeypatch.setattr(agent, "handle_message", slow)
    conversation_id = (await start(client))["id"]
    async with anyio.create_task_group() as group:
        group.start_soon(say, client, conversation_id, "sí")
        await anyio.sleep(0.01)
        group.start_soon(say, client, conversation_id, "Me llamo Lucía Martín")
    messages = (await client.get(f"/api/conversations/{conversation_id}")).json()["messages"]
    assert [m["text"] for m in messages if m["role"] == "candidate"] == [
        "sí",
        "Me llamo Lucía Martín",
    ]
    assert "años" in messages[-1]["text"]  # both turns applied: Sofi now asks for the age


@pytest.mark.anyio
@pytest.mark.ac("004:AC-4")
async def test_unknown_id_is_404(client: AsyncClient) -> None:
    assert (await client.get("/api/conversations/nope")).status_code == 404
    response = await client.post("/api/conversations/nope/messages", json={"text": "hola"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found"}


@pytest.mark.anyio
@pytest.mark.ac("004:AC-4")
@pytest.mark.parametrize("body", [{}, {"text": ""}, {"text": "   "}, {"text": "hi", "x": 1}])
async def test_invalid_body_is_422(client: AsyncClient, body: dict[str, Any]) -> None:
    conversation_id = (await start(client))["id"]
    response = await client.post(f"/api/conversations/{conversation_id}/messages", json=body)
    assert response.status_code == 422


@pytest.mark.anyio
@pytest.mark.ac("004:AC-4")
async def test_a_closed_conversation_still_answers(client: AsyncClient) -> None:
    conversation_id = (await start(client))["id"]
    for text in ["sí", "Me llamo Hugo Sanz", "tengo 16"]:
        turn = await say(client, conversation_id, text)
    assert turn["status"] == "disqualified"
    after = await say(client, conversation_id, "vale, gracias")
    assert after["status"] == "disqualified"
    assert after["reply"]["text"]


@pytest.mark.anyio
@pytest.mark.ac("004:AC-4")
async def test_unexpected_error_is_a_500_without_a_stack_trace(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation_id = (await start(client))["id"]
    service: ScreeningService = app.state.service

    async def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("database on fire")

    monkeypatch.setattr(service, "send_message", broken)
    response = await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": "hola"}
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
