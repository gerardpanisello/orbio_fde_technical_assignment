"""T7: demo seed and dev routes (AC-8 on seeded data, AC-9)."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from sazon_screening.api import repo
from sazon_screening.api.app import create_app
from sazon_screening.api.db import create_tables, make_engine, make_sessions
from sazon_screening.api.seed import PERSONAS, seed
from sazon_screening.api.service import ScreeningService
from sazon_screening.api.settings import AppSettings
from sazon_screening.api.slots import load_slot_provider
from sazon_screening.config import EngineConfig, ZoneStaffingConfig
from sazon_screening.llm.client.fake import FakeLLMClient
from sazon_screening.llm.phrasing.catalog import load_catalog
from sazon_screening.llm.pipeline import ScreeningAgent
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import load_llm_config
from sazon_screening.reengagement import ReengagementConfig
from tests.api.conftest import START, TickingClock
from tests.paths import SHIPPED_CONFIG_DIR

EXPECTED_STATUS = {
    "booked_es": "interview_scheduled",
    "booked_mx": "interview_scheduled",
    "booked_en": "interview_scheduled",
    "unscheduled": "qualified_unscheduled",
    "unscheduled_silent": "qualified_unscheduled",
    "waitlisted": "waitlisted",
    "under_age": "disqualified",
    "no_license": "disqualified",
    "out_of_area_es": "disqualified",
    "out_of_area_mx": "disqualified",
    "abandoned_at_consent": "abandoned",
    "abandoned_at_vehicle": "abandoned",
    "abandoned_at_availability": "abandoned",
    "abandoned_at_start_date": "abandoned",
    "needs_review": "needs_review",
    "opted_out": "opted_out",
    "reactivated_after_1": "interview_scheduled",
    "reactivated_after_2": "interview_scheduled",
    "nudged_waiting": "in_progress",
    "booked_soon_es": "interview_scheduled",  # spec 010
    "booked_soon_mx": "interview_scheduled",
    "rescheduled": "interview_scheduled",
    "interview_cancelled": "qualified_unscheduled",
}

Seeder = Callable[[int, int], Awaitable[list[tuple[Any, ...]]]]


@pytest.fixture
async def seeded_snapshot(
    tmp_path: Path,
    agent: ScreeningAgent,
    staffing_seed: ZoneStaffingConfig,
    reengagement: ReengagementConfig,
) -> AsyncIterator[Seeder]:
    """Seed a fresh database and return what the dashboard would see, oldest first."""
    engines = []

    async def run(n: int, seed_value: int) -> list[tuple[Any, ...]]:
        url = f"sqlite+aiosqlite:///{(tmp_path / f'seed{len(engines)}.db').as_posix()}"
        engine = make_engine(url)
        engines.append(engine)
        await create_tables(engine)
        sessions = make_sessions(engine)
        service = ScreeningService(
            agent,
            sessions,
            load_slot_provider(SHIPPED_CONFIG_DIR, agent.engine_config.service_areas),
            TickingClock(),
            staffing_seed,
            reengagement,
        )
        ids = await seed(service, n, seed=seed_value, now=START)
        snapshot = []
        async with sessions() as session:
            for conversation_id in ids:
                row = await repo.get_conversation(session, conversation_id)
                assert row is not None
                texts = [m.text for m in await repo.list_messages(session, conversation_id)]
                summary = await repo.get_summary(session, conversation_id, "es")
                snapshot.append(
                    (
                        row.created_at,
                        row.status,
                        row.full_name,
                        row.city,
                        texts,
                        summary is None,
                        row.reactivated_after_step,
                    )
                )
        return snapshot

    yield run
    for engine in engines:
        await engine.dispose()


@pytest.mark.anyio
@pytest.mark.ac("004:AC-9")
async def test_every_persona_reaches_its_outcome(seeded_snapshot: Seeder) -> None:
    snapshot = await seeded_snapshot(len(PERSONAS), 1)
    assert {p.key: s[1] for p, s in zip(PERSONAS, snapshot, strict=True)} == EXPECTED_STATUS
    finished = [s for s in snapshot if s[1] != "in_progress"]
    assert all(not s[5] for s in finished)  # every finished one has its summary
    assert any("Hello" in " ".join(s[4]) or "Hi" in " ".join(s[4]) for s in snapshot)  # EN
    times = [s[0] for s in snapshot]
    assert all(START - timedelta(days=14) <= t < START for t in times)


@pytest.mark.anyio
@pytest.mark.ac("004:AC-9")
async def test_same_seed_same_data(seeded_snapshot: Seeder) -> None:
    first = await seeded_snapshot(18, 7)  # every persona, then a few weighted repeats
    assert await seeded_snapshot(18, 7) == first
    assert await seeded_snapshot(18, 8) != first


@pytest.mark.anyio
@pytest.mark.ac("004:AC-9")
async def test_dev_routes_refuse_outside_dev(settings: AppSettings, agent: ScreeningAgent) -> None:
    app = create_app(settings.model_copy(update={"app_env": "prod"}), agent=agent)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.post("/api/dev/seed")).status_code == 403
            silence = await client.post("/api/dev/conversations/x/silence")
            assert silence.status_code == 403
            assert (await client.get("/api/candidates")).json() == []


@pytest.mark.anyio
@pytest.mark.ac("004:AC-8")
async def test_analytics_on_seeded_data_add_up(client: AsyncClient) -> None:
    response = await client.post("/api/dev/seed", params={"n": 30, "seed": 3})
    assert response.status_code == 201
    assert response.json()["created"] == 30
    analytics = (await client.get("/api/analytics")).json()
    by_status = analytics["by_status"]
    assert analytics["total"] == 30
    assert sum(by_status.values()) == 30
    assert sum(sum(c.values()) for c in analytics["by_country"].values()) == 30
    assert sum(analytics["drop_off_by_stage"].values()) == by_status["abandoned"]
    assert sum(analytics["disqualification_reasons"].values()) == by_status["disqualified"]
    finished = sum(
        by_status.get(s, 0)
        for s in (
            "interview_scheduled",
            "qualified_unscheduled",
            "waitlisted",
            "disqualified",
            "needs_review",
        )
    )
    assert analytics["finished"] == finished
    assert analytics["completion_rate"] == round(finished / 30, 4)
    assert analytics["median_duration_s"] > 0
    reengagement = analytics["reengagement"]  # spec 008: the seed nudges and reactivates
    assert reengagement["follow_ups_sent"] > reengagement["reactivated"] > 0
    assert sum(s["sent"] for s in reengagement["by_step"]) == reengagement["follow_ups_sent"]
    assert sum(s["reactivated"] for s in reengagement["by_step"]) == reengagement["reactivated"]
    rows = (await client.get("/api/candidates")).json()
    assert len(rows) == 30


@pytest.mark.anyio
@pytest.mark.ac("004:AC-4")
async def test_silence_route_abandons_and_summarises(client: AsyncClient) -> None:
    created = (await client.post("/api/conversations", json={})).json()
    response = await client.post(f"/api/dev/conversations/{created['id']}/silence")
    assert response.status_code == 200
    assert response.json() == {"reply": None, "status": "abandoned"}
    summary = await client.get(f"/api/candidates/{created['id']}/summary")
    assert summary.json()["status"] == "abandoned"
    assert (await client.post("/api/dev/conversations/nope/silence")).status_code == 404


@pytest.mark.anyio
@pytest.mark.ac("004:AC-9")
async def test_seed_uses_the_server_agent_unless_mode_fake(
    settings: AppSettings, shipped_config: EngineConfig, clock: TickingClock
) -> None:
    """The seed runs on the server's agent (the real model with `--env-file ../.env`);
    `?mode=fake` seeds offline with the rules agent and never touches the server's client."""
    server_client = FakeLLMClient(mode="rules", engine_config=shipped_config)
    server_client.name = "server-model"  # stands in for the real model
    server_agent = ScreeningAgent(
        client=server_client,
        engine_config=shipped_config,
        llm_config=load_llm_config(SHIPPED_CONFIG_DIR),
        catalog=load_catalog(SHIPPED_CONFIG_DIR / "messages"),
        prompts=PromptRegistry(),
    )
    app = create_app(settings, agent=server_agent, clock=clock)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            fake = await client.post("/api/dev/seed", params={"n": 3, "mode": "fake"})
            assert fake.status_code == 201
            assert server_client.calls == []
            rows = (await client.get("/api/candidates")).json()
            assert len(rows) == 3
            detail = (await client.get(f"/api/candidates/{fake.json()['ids'][0]}")).json()
            assert "fake-rules" in str(detail)

            default = await client.post("/api/dev/seed", params={"n": 1})
            assert default.status_code == 201
            assert server_client.calls != []  # the server's own agent ran the turns
            detail = (await client.get(f"/api/candidates/{default.json()['ids'][0]}")).json()
            assert "server-model" in str(detail)

            assert (await client.post("/api/dev/seed", params={"mode": "x"})).status_code == 422


@pytest.mark.anyio
@pytest.mark.ac("008:AC-8")
async def test_the_seed_has_nudged_reactivated_and_abandoned_candidates(
    seeded_snapshot: Seeder,
) -> None:
    """Spec 008: the analytics card has something to show after a seed."""
    snapshot = await seeded_snapshot(len(PERSONAS), 1)
    by_key = {p.key: s for p, s in zip(PERSONAS, snapshot, strict=True)}
    assert by_key["reactivated_after_1"][6] == 1
    assert by_key["reactivated_after_2"][6] == 2
    assert by_key["nudged_waiting"][6] is None
    assert by_key["abandoned_at_vehicle"][6] is None  # never came back


@pytest.mark.anyio
async def test_the_seed_books_interviews_ahead_and_marks_past_ones(client: AsyncClient) -> None:
    """Spec 010: the Entrevistas page and the show-up rate have something to show."""
    assert (await client.post("/api/dev/seed", params={"n": 40, "seed": 42})).status_code == 201
    interviews = (await client.get("/api/analytics")).json()["interviews"]
    assert interviews["attended"] > 0
    assert interviews["no_show"] > 0
    assert interviews["rescheduled"] >= 1
    assert interviews["cancelled"] >= 1
    upcoming = 0
    for city in ("madrid", "barcelona", "valencia", "sevilla", "malaga", "cdmx", "guadalajara"):
        week = (await client.get("/api/interviews/week", params={"city": city})).json()
        upcoming += sum(
            b["status"] == "booked"
            for day in week["days"]
            for slot in day["slots"]
            if not slot["past"]
            for b in slot["bookings"]
        )
    assert upcoming >= 3
