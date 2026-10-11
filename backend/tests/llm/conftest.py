"""Fixtures for the LLM layer tests (plan §7.1)."""

from datetime import date

import pytest

from sazon_screening.config import EngineConfig, load_config
from sazon_screening.llm.client.fake import FakeLLMClient
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import LLMConfig, load_llm_config
from tests.llm.support import FakeClock
from tests.paths import FIXTURE_CONFIG_DIR

# Monday, as in the engine tests: "el lunes" resolves to 2026-10-19.
TODAY = date(2026, 10, 12)


@pytest.fixture
def anyio_backend() -> str:
    """Async tests run on asyncio only: it is what FastAPI (004) uses in production."""
    return "asyncio"


@pytest.fixture(scope="session")
def engine_config() -> EngineConfig:
    """The engine's fixture config: Madrid, Valencia/El Carmen, CDMX/Coyoacán, Monterrey."""
    return load_config(FIXTURE_CONFIG_DIR)


@pytest.fixture
def today() -> date:
    return TODAY


@pytest.fixture(scope="session")
def llm_config() -> LLMConfig:
    """`tests/fixtures/config/llm.yaml`: 15 s budget, 2 attempts, 2000-char messages."""
    return load_llm_config(FIXTURE_CONFIG_DIR)


@pytest.fixture(scope="session")
def prompts() -> PromptRegistry:
    return PromptRegistry()


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def scripted(fake_clock: FakeClock) -> FakeLLMClient:
    """A scripted fake on the fake clock: timeouts and latency move `fake_clock.now`."""
    return FakeLLMClient(mode="scripted", clock=fake_clock)
