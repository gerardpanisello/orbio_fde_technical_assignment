"""Fixtures for the LLM layer tests (plan §7.1)."""

from datetime import date
from typing import TYPE_CHECKING

import pytest

from sazon_screening.config import EngineConfig, load_config
from sazon_screening.llm.client.fake import FakeLLMClient
from sazon_screening.llm.phrasing.catalog import MessageCatalog, load_catalog
from sazon_screening.llm.pipeline import ScreeningAgent
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import LLMConfig, load_llm_config
from tests.llm.support import FakeClock
from tests.paths import FIXTURE_CONFIG_DIR, SHIPPED_CONFIG_DIR

if TYPE_CHECKING:
    from tests.llm.chat import Chat

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


@pytest.fixture(scope="session")
def catalog() -> MessageCatalog:
    """The SHIPPED templates: they are product text, and the ACs are about what ships."""
    return load_catalog(SHIPPED_CONFIG_DIR / "messages")


@pytest.fixture
def chat(
    engine_config: EngineConfig,
    llm_config: LLMConfig,
    catalog: MessageCatalog,
    prompts: PromptRegistry,
) -> "Chat":
    from tests.llm.chat import MEXICAN_PHONE, Chat  # avoids an import cycle

    agent = ScreeningAgent(
        client=FakeLLMClient(mode="rules", engine_config=engine_config),
        engine_config=engine_config,
        llm_config=llm_config,
        catalog=catalog,
        prompts=prompts,
    )
    return Chat(agent=agent, llm_config=llm_config, context=MEXICAN_PHONE)
