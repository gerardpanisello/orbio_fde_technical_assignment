"""Fixtures for the API tests: a temp SQLite file and the offline (rules) agent.

Nothing here reads the environment or `.env`: settings are built explicitly with
`llm_mode="fake"`, so a real key on the machine can never be used by a test (NFR-2).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from sazon_screening.api.app import create_app
from sazon_screening.api.db import Sessions, create_tables, make_engine, make_sessions
from sazon_screening.api.service import ScreeningService
from sazon_screening.api.settings import AppSettings
from sazon_screening.api.slots import load_slot_provider
from sazon_screening.config import EngineConfig, ZoneStaffingConfig, load_config, load_zone_staffing
from sazon_screening.faq import load_faq
from sazon_screening.llm.client.fake import FakeLLMClient
from sazon_screening.llm.phrasing.catalog import load_catalog
from sazon_screening.llm.pipeline import ScreeningAgent
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import Settings, load_llm_config
from sazon_screening.reengagement import ReengagementConfig, load_reengagement
from tests.paths import SHIPPED_CONFIG_DIR

START = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)  # a Monday

# A Spanish candidate in Madrid, from consent to a booked interview (shipped config).
HAPPY_PATH = [
    "sí",
    "Me llamo Lucía Martín",
    "tengo 27",
    "moto",
    "sí",
    "vivo en Chamberí, Madrid",
    "tiempo completo",
    "tardes",
    "3 años en Glovo",
    "el lunes",
    "sí",
    "1",
]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class TickingClock:
    """Each reading is one second after the last: timestamps are distinct and ordered."""

    def __init__(self, start: datetime = START) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def clock() -> TickingClock:
    return TickingClock()


@pytest.fixture(scope="session")
def shipped_config() -> EngineConfig:
    return load_config(SHIPPED_CONFIG_DIR)


@pytest.fixture(scope="session")
def staffing_seed(shipped_config: EngineConfig) -> ZoneStaffingConfig:
    return load_zone_staffing(SHIPPED_CONFIG_DIR, shipped_config.service_areas)


@pytest.fixture(scope="session")
def reengagement(shipped_config: EngineConfig) -> ReengagementConfig:
    """Spec 008: the shipped schedule (2 h, 23 h, 72 h; abandon 24 h after the last)."""
    return load_reengagement(SHIPPED_CONFIG_DIR, shipped_config.service_areas)


@pytest.fixture
def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        llm=Settings(llm_mode="fake", config_dir=SHIPPED_CONFIG_DIR),
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        app_env="dev",
    )


@pytest.fixture
async def sessions(settings: AppSettings) -> AsyncIterator[Sessions]:
    engine = make_engine(settings.database_url)
    await create_tables(engine)
    yield make_sessions(engine)
    await engine.dispose()


@pytest.fixture
def fake_client(shipped_config: EngineConfig) -> FakeLLMClient:
    """Rules mode: keyword extraction, template phrasing; `.calls` records every request."""
    return FakeLLMClient(mode="rules", engine_config=shipped_config)


@pytest.fixture
def agent(fake_client: FakeLLMClient, shipped_config: EngineConfig) -> ScreeningAgent:
    return ScreeningAgent(
        client=fake_client,
        engine_config=shipped_config,
        llm_config=load_llm_config(SHIPPED_CONFIG_DIR),
        catalog=load_catalog(SHIPPED_CONFIG_DIR / "messages"),
        prompts=PromptRegistry(),
        faq=load_faq(SHIPPED_CONFIG_DIR),
    )


@pytest.fixture
async def service(
    agent: ScreeningAgent,
    sessions: Sessions,
    clock: TickingClock,
    staffing_seed: ZoneStaffingConfig,
    reengagement: ReengagementConfig,
) -> ScreeningService:
    service = ScreeningService(
        agent,
        sessions,
        load_slot_provider(SHIPPED_CONFIG_DIR, agent.engine_config.service_areas),
        clock,
        staffing_seed,
        reengagement,
    )
    await service.init_zone_staffing()  # as the app does at startup
    await service.init_interview_availability()
    return service


@pytest.fixture
async def app(
    settings: AppSettings, agent: ScreeningAgent, clock: TickingClock
) -> AsyncIterator[FastAPI]:
    app = create_app(settings, agent=agent, clock=clock)
    async with app.router.lifespan_context(app):  # ASGITransport does not run the lifespan
        yield app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
