"""Fixtures for the API tests: a temp SQLite file and the offline (rules) agent.

Nothing here reads the environment or `.env`: settings are built explicitly with
`llm_mode="fake"`, so a real key on the machine can never be used by a test (NFR-2).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sazon_screening.api.db import Sessions, create_tables, make_engine, make_sessions
from sazon_screening.api.settings import AppSettings
from sazon_screening.config import EngineConfig, load_config
from sazon_screening.llm.settings import Settings
from tests.paths import SHIPPED_CONFIG_DIR

START = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)  # a Monday


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
