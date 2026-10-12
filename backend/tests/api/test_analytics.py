"""T6: funnel analytics (AC-8)."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from sazon_screening.api.service import ScreeningService
from sazon_screening.engine import SilenceExpired
from tests.api.conftest import HAPPY_PATH
from tests.api.test_candidates import UNDER_AGE, converse


@pytest.mark.anyio
@pytest.mark.ac("004:AC-8")
async def test_empty_database(client: AsyncClient) -> None:
    analytics = (await client.get("/api/analytics")).json()
    assert analytics["total"] == 0
    assert analytics["completion_rate"] == 0.0
    assert analytics["median_duration_s"] is None


@pytest.mark.anyio
@pytest.mark.ac("004:AC-8")
async def test_counts_rates_and_drop_off(client: AsyncClient, app: FastAPI) -> None:
    service: ScreeningService = app.state.service
    await converse(client, HAPPY_PATH)
    await converse(client, UNDER_AGE)
    abandoned = await converse(client, ["sí", "Me llamo Eva Gil"])
    await service.send_event(abandoned, SilenceExpired())
    await converse(client, ["sí"], country_hint="MX")  # still in progress

    analytics = (await client.get("/api/analytics")).json()
    assert analytics["total"] == 4
    assert sum(analytics["by_status"].values()) == analytics["total"]
    assert analytics["by_status"] == {
        "interview_scheduled": 1,
        "disqualified": 1,
        "abandoned": 1,
        "in_progress": 1,
    }
    assert analytics["finished"] == 2
    assert analytics["completion_rate"] == 0.5
    assert analytics["drop_off_by_stage"] == {"age": 1}
    assert analytics["disqualification_reasons"] == {"under_age": 1}
    assert analytics["median_duration_s"] > 0
    assert analytics["fallback_rate"] == 0.0
    assert analytics["agent_turns"] > 0
    assert analytics["avg_cost_usd"] == 0.0  # the fake costs nothing
    assert analytics["by_country"] == {
        "ES": {"interview_scheduled": 1},
        "MX": {"in_progress": 1},  # from the phone prefix
        "unknown": {"disqualified": 1, "abandoned": 1},  # stopped before the location
    }


@pytest.mark.anyio
@pytest.mark.ac("009:AC-7")
async def test_faq_questions_and_the_unanswered_rate(client: AsyncClient) -> None:
    await converse(client, ["sí", "Me llamo Eva Gil", "¿cuánto se paga?"], country_hint="ES")
    await converse(
        client, ["sí", "Me llamo Leo Ruiz", "¿cuánto cobra un repartidor?"], country_hint="ES"
    )
    await converse(client, ["sí", "Me llamo Ana Paz", "¿cuánto se paga?"], country_hint="MX")
    await converse(client, ["sí", "Me llamo Iker Sol", "¿se cobra en bitcoin?"])

    faq = (await client.get("/api/analytics")).json()["faq"]
    assert (faq["asked"], faq["answered"]) == (4, 3)
    assert faq["unanswered_rate"] == 0.25
    assert faq["top_questions"] == [
        {"entry_id": "pay-es", "question": "¿Cuánto se paga?", "count": 2},
        {"entry_id": "pay-mx", "question": "¿Cuánto se paga?", "count": 1},
        {"entry_id": None, "question": "¿se cobra en bitcoin?", "count": 1},
    ]


@pytest.mark.anyio
@pytest.mark.ac("009:AC-7")
async def test_no_questions_yet(client: AsyncClient) -> None:
    await converse(client, HAPPY_PATH)
    faq = (await client.get("/api/analytics")).json()["faq"]
    assert faq == {"asked": 0, "answered": 0, "unanswered_rate": 0.0, "top_questions": []}


@pytest.mark.anyio
@pytest.mark.ac("009:AC-3")
async def test_the_candidate_detail_shows_the_faq_trace(client: AsyncClient) -> None:
    conversation_id = await converse(client, ["sí", "Me llamo Iker Sol", "¿se cobra en bitcoin?"])
    detail = (await client.get(f"/api/candidates/{conversation_id}")).json()
    flagged = [t for t in detail["traces"] if t["faq"] is not None]
    assert [t["faq"] for t in flagged] == ["unanswered"]
    faq = flagged[0]["trace"]["faq"]
    assert faq["question"] == "¿se cobra en bitcoin?"
    assert faq["entry_ids"] == []
    assert all({"entry_id", "score"} == set(hit) for hit in faq["hits"])
    reply = next(m for m in detail["transcript"] if m["id"] == flagged[0]["message_id"])
    assert reply["text"].startswith("Buena pregunta: lo consulto con el equipo.")
